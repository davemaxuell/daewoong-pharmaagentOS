from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.enums import ScopeStatus

TOP_LEVEL_NON_DRUG_CLASSES = {
    "Biologics",
    "Medical Devices",
    "Food & Beverages",
    "Food",
    "Animal & Veterinary",
    "Tobacco",
    "Cosmetics",
    "Radiation-Emitting Products",
}
KNOWN_CANONICAL_VALUES = {item.casefold(): item for item in TOP_LEVEL_NON_DRUG_CLASSES}
KNOWN_CANONICAL_VALUES["drugs"] = "Drugs"
KNOWN_CANONICAL_VALUES["over-the-counter drugs"] = "Over-the-Counter Drugs"

DATE_FORMATS = (
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d %B %Y",
)


def normalize_whitespace(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def normalize_product_class(value: str) -> str:
    cleaned = normalize_whitespace(value).strip(" :;,.\t\r\n")
    return KNOWN_CANONICAL_VALUES.get(cleaned.casefold(), cleaned)


@dataclass(frozen=True)
class ScopeResult:
    raw_values: list[str]
    normalized_classes: list[str]
    status: ScopeStatus
    source_anchor: str | None
    rationale: str


def decide_drug_scope(raw_values: list[str] | None, *, malformed: bool = False) -> ScopeResult:
    raw = [normalize_whitespace(item) for item in (raw_values or []) if normalize_whitespace(item)]
    normalized: list[str] = []
    for item in raw:
        value = normalize_product_class(item)
        if value and value not in normalized:
            normalized.append(value)

    if malformed or not normalized:
        return ScopeResult(
            raw_values=raw,
            normalized_classes=normalized,
            status=ScopeStatus.AMBIGUOUS,
            source_anchor=None,
            rationale="Product metadata is missing or malformed; processing fails closed.",
        )

    contains_drugs = "Drugs" in normalized
    conflicting = contains_drugs and any(item in TOP_LEVEL_NON_DRUG_CLASSES for item in normalized)
    if conflicting:
        return ScopeResult(
            raw_values=raw,
            normalized_classes=normalized,
            status=ScopeStatus.AMBIGUOUS,
            source_anchor="metadata-product",
            rationale="Product metadata contains contradictory top-level product classes.",
        )
    if contains_drugs:
        return ScopeResult(
            raw_values=raw,
            normalized_classes=normalized,
            status=ScopeStatus.IN_SCOPE_DRUGS,
            source_anchor="metadata-product",
            rationale="Canonical Product metadata contains the exact class Drugs.",
        )
    return ScopeResult(
        raw_values=raw,
        normalized_classes=normalized,
        status=ScopeStatus.OUT_OF_SCOPE,
        source_anchor="metadata-product",
        rationale="Canonical Product metadata was parsed and does not contain exact Drugs.",
    )


@dataclass
class ParsedDocument:
    title: str | None
    company_name: str
    metadata: dict[str, list[str]]
    issue_date: date | None
    recipient_country: str | None
    normalized_markdown: str
    normalized_text: str
    canonical_hash: str
    anchors: list[dict[str, Any]]
    source_links: list[dict[str, str]]
    scope: ScopeResult
    warnings: list[str] = field(default_factory=list)


def _label_key(value: str) -> str:
    return normalize_whitespace(value).rstrip(":").casefold()


def _value_parts(node: Tag) -> list[str]:
    candidates = [normalize_whitespace(item) for item in node.stripped_strings]
    return [item for item in candidates if item]


def _extract_metadata(soup: BeautifulSoup) -> tuple[dict[str, list[str]], bool]:
    metadata: dict[str, list[str]] = {}
    product_label_seen = False

    def add(label: str, values: list[str]) -> None:
        nonlocal product_label_seen
        key = _label_key(label)
        if not key:
            return
        if key == "product":
            product_label_seen = True
        cleaned = [normalize_whitespace(value) for value in values if normalize_whitespace(value)]
        if cleaned:
            metadata.setdefault(key, [])
            for value in cleaned:
                if value not in metadata[key]:
                    metadata[key].append(value)

    for field_node in soup.select(".field, [data-fda-field]"):
        label_node = field_node.select_one(
            ".field__label, .field-label, dt, th, [data-field-label]"
        )
        if not label_node:
            continue
        value_nodes = field_node.select(".field__item, .field-item, dd, td, [data-field-value]")
        values: list[str] = []
        for node in value_nodes:
            values.extend(_value_parts(node))
        add(label_node.get_text(" ", strip=True), values)

    for definition_list in soup.find_all("dl"):
        for term in definition_list.find_all("dt", recursive=False):
            value = term.find_next_sibling("dd")
            add(term.get_text(" ", strip=True), _value_parts(value) if value else [])

    for row in soup.select("table tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) >= 2:
            add(cells[0].get_text(" ", strip=True), _value_parts(cells[1]))

    # FDA legacy pages sometimes represent metadata as a label/value sibling pair.
    for label_node in soup.find_all(string=re.compile(r"^\s*Product\s*:\s*$", re.I)):
        parent = label_node.parent if isinstance(label_node.parent, Tag) else None
        if not parent:
            continue
        product_label_seen = True
        sibling = parent.find_next_sibling()
        if isinstance(sibling, Tag):
            add("Product", _value_parts(sibling))

    return metadata, product_label_seen


def _recipient_value_nodes(soup: BeautifulSoup) -> list[Tag]:
    """Return only the consecutive ``dd`` values owned by a Recipient term.

    FDA warning-letter pages may place an Issuing Office address immediately after the
    recipient metadata.  Restricting traversal to siblings of the Recipient ``dt`` and
    stopping at the next ``dt`` prevents its ``.country`` value from leaking into the
    recipient record.
    """

    for term in soup.find_all("dt"):
        if _label_key(term.get_text(" ", strip=True)) != "recipient":
            continue
        values: list[Tag] = []
        for sibling in term.next_siblings:
            if not isinstance(sibling, Tag):
                continue
            if sibling.name == "dt":
                break
            if sibling.name == "dd":
                values.append(sibling)
        if values:
            return values
    return []


def _country_fallback_candidate(value: str) -> str | None:
    candidate = normalize_whitespace(value).strip(" ,;|")
    folded = candidate.casefold()
    if not candidate or len(candidate) > 120:
        return None
    if not any(character.isalpha() for character in candidate):
        return None
    if any(character.isdigit() for character in candidate) or "@" in candidate:
        return None
    if folded.startswith(("tel", "phone", "fax", "email", "mailto", "http")):
        return None
    if any(
        token in folded
        for token in (
            "manager",
            "director",
            "president",
            "officer",
            "pharmaceutical",
            "laboratories",
            "corporation",
            "company",
            "limited",
            " ltd",
            " inc",
            " llc",
        )
    ):
        return None
    return candidate


def _text_rows(node: Tag) -> list[str]:
    return [
        normalized
        for part in node.get_text("\n", strip=True).splitlines()
        if (normalized := normalize_whitespace(part))
    ]


def _extract_recipient_country(soup: BeautifulSoup) -> str | None:
    recipient_values = _recipient_value_nodes(soup)
    if not recipient_values:
        return None

    # Current FDA markup provides the authoritative country as a structured address
    # span.  Search only within Recipient-owned dd nodes, never the full page.
    for value in recipient_values:
        for country_node in value.select(".country"):
            country = normalize_whitespace(country_node.get_text(" ", strip=True))
            if country:
                return country[:120]

    # Legacy pages may have an unstructured final address row.  Prefer explicit
    # address containers, where the last plausible row is conventionally country.
    address_nodes: list[Tag] = []
    for value in recipient_values:
        address_nodes.extend(value.select(".address, address, [itemprop='address']"))
    for address in reversed(address_nodes):
        for row in reversed(_text_rows(address)):
            if country := _country_fallback_candidate(row):
                return country

    # Some older templates split address rows across adjacent dd elements.  Only
    # consider text following a digit-bearing street/postal row, which avoids
    # mistaking the recipient name or job title for a country.
    rows = [row for value in recipient_values for row in _text_rows(value)]
    address_start = max(
        (index for index, row in enumerate(rows) if any(char.isdigit() for char in row)),
        default=-1,
    )
    if address_start >= 0:
        for row in reversed(rows[address_start + 1 :]):
            if country := _country_fallback_candidate(row):
                return country
    return None


def _parse_date(values: list[str] | None) -> date | None:
    if not values:
        return None
    raw = normalize_whitespace(values[0])
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:80] or "section"


def _extract_body(soup: BeautifulSoup) -> Tag:
    explicit = soup.select_one(
        ".letter-body, .field--name-body, article .content, main article, article, main"
    )
    return explicit if isinstance(explicit, Tag) else soup.body or soup


def _is_wholly_bold_paragraph(element: Tag) -> bool:
    if element.name != "p":
        return False
    found_text = False
    for string_node in element.find_all(string=True):
        if not normalize_whitespace(str(string_node)):
            continue
        found_text = True
        parent = string_node.parent
        is_bold = False
        while isinstance(parent, Tag) and parent is not element:
            if parent.name in {"strong", "b"}:
                is_bold = True
                break
            parent = parent.parent
        if not is_bold:
            return False
    return found_text


def _is_bold_text_node(string_node: Any, element: Tag) -> bool:
    parent = string_node.parent
    while isinstance(parent, Tag) and parent is not element:
        if parent.name in {"strong", "b"}:
            return True
        parent = parent.parent
    return False


def _escape_inline_markdown(value: str) -> str:
    """Escape source-controlled Markdown delimiters without emitting raw HTML."""

    return value.replace("\\", "\\\\").replace("*", "\\*")


def _inline_display_markdown(element: Tag) -> str | None:
    """Return safe display-only Markdown when an element has inline bold text.

    The canonical anchor ``text`` remains plain and is still the sole input to
    chunks, hashes, and AI evidence.  This optional representation is only for
    rendering source typography in the Original view.
    """

    runs: list[tuple[bool, list[str]]] = []
    has_bold = False
    for string_node in element.find_all(string=True):
        value = normalize_whitespace(str(string_node))
        if not value:
            continue
        is_bold = _is_bold_text_node(string_node, element)
        has_bold = has_bold or is_bold
        if runs and runs[-1][0] == is_bold:
            runs[-1][1].append(value)
        else:
            runs.append((is_bold, [value]))

    if not has_bold:
        return None

    formatted_runs: list[str] = []
    for is_bold, values in runs:
        escaped = _escape_inline_markdown(" ".join(values))
        formatted_runs.append(f"**{escaped}**" if is_bold else escaped)
    return " ".join(formatted_runs)


def _build_representations(body: Tag) -> tuple[str, str, list[dict[str, Any]]]:
    for node in body.select("script, style, noscript, nav, footer, header, form, iframe, svg"):
        node.decompose()
    for node in body.select(
        ".metadata, .field--name-field-product, .breadcrumb, .region-navigation, "
        ".subscription, .feedback, .social-share"
    ):
        node.decompose()

    anchors: list[dict[str, Any]] = []
    markdown_lines: list[str] = []
    plain_lines: list[str] = []
    used: dict[str, int] = {}
    current_section = "introduction"

    elements = body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"])
    if not elements:
        text = normalize_whitespace(body.get_text(" ", strip=True))
        elements = []
        if text:
            anchor = "introduction"
            anchors.append({"anchor": anchor, "text": text, "kind": "paragraph", "ordinal": 0})
            return text, text, anchors

    for element in elements:
        # Avoid duplicating paragraphs/lists nested inside another selected list item.
        if element.name in {"p", "li"} and element.find_parent(["p", "li"]) is not None:
            continue
        text = normalize_whitespace(element.get_text(" ", strip=True))
        if not text:
            continue
        promoted_subheading = _is_wholly_bold_paragraph(element)
        kind = (
            "heading"
            if element.name.startswith("h") or promoted_subheading
            else ("list_item" if element.name == "li" else "paragraph")
        )
        if kind == "heading":
            base = _slug(text)
            current_section = base
        else:
            base = current_section
            if re.match(r"^(\d+|[A-Za-z])\s*[.)]", text):
                base = f"{current_section}-{_slug(text[:32])}"
        index = used.get(base, 0) + 1
        used[base] = index
        anchor = base if index == 1 else f"{base}-{index}"
        display = _inline_display_markdown(element) if kind != "heading" else None
        if kind == "heading":
            level = 3 if promoted_subheading else int(element.name[1])
            markdown_lines.append(f"{'#' * level} {text}")
        elif kind == "list_item":
            markdown_lines.append(f"- {display or text}")
        else:
            markdown_lines.append(display or text)
        plain_lines.append(text)
        source_anchor = {
            "anchor": anchor,
            "text": text,
            "kind": kind,
            "ordinal": len(anchors),
        }
        if display:
            source_anchor["display"] = display
        anchors.append(source_anchor)
    markdown = "\n\n".join(markdown_lines).strip()
    plain = "\n".join(plain_lines).strip()
    return markdown, plain, anchors


def parse_warning_letter_html(html: bytes | str) -> ParsedDocument:
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")
    metadata, product_label_seen = _extract_metadata(soup)
    recipient_country = _extract_recipient_country(soup)

    product_values = metadata.get("product", [])
    malformed = product_label_seen and (
        not product_values or any(len(value) > 200 for value in product_values)
    )
    scope = decide_drug_scope(product_values, malformed=malformed)

    title_node = soup.select_one("h1")
    title = normalize_whitespace(title_node.get_text(" ", strip=True)) if title_node else None
    company_values = metadata.get("company name") or metadata.get("company") or []
    company = (
        company_values[0] if company_values else (title.split(" - ")[0] if title else "Unknown")
    )
    body = _extract_body(soup)
    markdown, text, anchors = _build_representations(body)
    canonical_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    links: list[dict[str, str]] = []
    for link in body.select("a[href]"):
        label = normalize_whitespace(link.get_text(" ", strip=True))
        href = str(link.get("href", ""))
        if href and not href.lower().startswith(("javascript:", "data:")):
            links.append({"label": label, "url": href})

    warnings: list[str] = []
    if not text:
        warnings.append("empty_body")
    if not product_label_seen:
        warnings.append("missing_product_metadata")
    if scope.status == ScopeStatus.AMBIGUOUS:
        warnings.append("ambiguous_product_metadata")

    return ParsedDocument(
        title=title,
        company_name=company,
        metadata=metadata,
        issue_date=_parse_date(metadata.get("letter issue date") or metadata.get("issue date")),
        recipient_country=recipient_country,
        normalized_markdown=markdown,
        normalized_text=text,
        canonical_hash=canonical_hash,
        anchors=anchors,
        source_links=links,
        scope=scope,
        warnings=warnings,
    )


CITATION_PATTERN = re.compile(
    r"\b(?:21\s*CFR\s*(?:Parts?\s*)?\d+(?:\.\d+)?(?:\([a-z0-9]+\))*|"
    r"section\s+\d+(?:\([a-z0-9]+\))*\s+of\s+the\s+FD&C\s+Act)\b",
    re.IGNORECASE,
)


def extract_regulatory_references(text: str) -> list[str]:
    references: list[str] = []
    for match in CITATION_PATTERN.finditer(text):
        reference = normalize_whitespace(match.group(0))
        if reference not in references:
            references.append(reference)
    return references


def build_chunks(
    anchors: list[dict[str, Any]], *, target_chars: int = 2_400
) -> list[dict[str, Any]]:
    """Build deterministic structure-aware chunks without crossing logical headings."""
    chunks: list[dict[str, Any]] = []
    heading = "introduction"
    pending: list[str] = []
    pending_anchor = "introduction"

    def flush() -> None:
        if not pending:
            return
        content = "\n".join(pending).strip()
        chunks.append(
            {
                "ordinal": len(chunks),
                "source_anchor": pending_anchor,
                "section_path": [heading],
                "content": content,
                "token_estimate": max(1, len(content) // 4),
                "regulatory_references": extract_regulatory_references(content),
            }
        )
        pending.clear()

    for anchor in anchors:
        text = str(anchor.get("text", "")).strip()
        if not text:
            continue
        if anchor.get("kind") == "heading":
            flush()
            heading = str(anchor["anchor"])
            pending_anchor = heading
            pending.append(text)
            continue
        if pending and sum(len(item) for item in pending) + len(text) > target_chars:
            flush()
            pending_anchor = str(anchor["anchor"])
        elif not pending:
            pending_anchor = str(anchor["anchor"])
        pending.append(text)
    flush()
    return chunks
