from __future__ import annotations

import io
import json
from pathlib import Path

import yaml
from openpyxl import Workbook

from app.discovery import (
    discover_datatables_configuration,
    parse_datatables_page,
    parse_listing,
)
from app.parsing import build_chunks, parse_warning_letter_html

TIANJIN_DETAIL_HTML = """
<html>
  <body>
    <h1>Tianjin Kilo Pharmaceutical Sci-tech Co., Ltd. - 731761 - 08/06/2026</h1>
    <div class="field">
      <div class="field__label">Product</div>
      <div class="field__item">Drugs</div>
    </div>
    <div class="row inset-column">
      <div>
        <dl>
          <dt>Recipient:</dt>
          <dd>Wenjun Liao</dd>
          <dd>General Manager</dd>
          <dd>Tianjin Kilo Pharmaceutical Sci-tech Co., Ltd.</dd>
          <dd>
            <p class="address">
              <span class="address-line1">Room 609, Building 6, no. 6 Ziyuan Road</span><br>
              <span class="dependent-locality">Huayuan High-tech Industrial Park</span><br>
              <span class="administrative-area">Tianjin Shi</span>,
              <span class="postal-code">300384</span><br>
              <span class="country">China</span>
            </p>
          </dd>
        </dl>
      </div>
      <div>
        <dl>
          <dt>Issuing Office:</dt>
          <dd>Center for Drug Evaluation and Research (CDER)</dd>
          <dd><p class="address"><span class="country">United States</span></p></dd>
        </dl>
      </div>
    </div>
    <div class="letter-body">
      <p><strong>FDA Review</strong></p>
      <p>FDA reviewed the firm's records.</p>
      <p><strong>1. Failure to validate the manufacturing process.</strong></p>
      <p><strong>Important:</strong> this mixed paragraph remains body copy.</p>
    </div>
  </body>
</html>
"""


def test_scope_fixture_matrix(fixture_dir: Path) -> None:
    manifest = yaml.safe_load((fixture_dir / "fixture_manifest.yaml").read_text())
    for item in manifest["fixtures"]:
        parsed = parse_warning_letter_html((fixture_dir / item["path"]).read_bytes())
        assert parsed.scope.status.value == item["expected_scope_status"], item["path"]
        assert parsed.scope.normalized_classes == item["expected_product_classes"]
        assert bool(parsed.normalized_text) is item["expected_body_non_empty"]


def test_recipient_country_is_scoped_to_tianjin_recipient_block() -> None:
    parsed = parse_warning_letter_html(TIANJIN_DETAIL_HTML)

    assert parsed.recipient_country == "China"
    assert parsed.recipient_country != "United States"


def test_recipient_country_legacy_address_row_fallback_stops_before_issuing_office() -> None:
    html = TIANJIN_DETAIL_HTML.replace(
        '<span class="country">China</span>',
        "China",
        1,
    )
    parsed = parse_warning_letter_html(html)
    assert parsed.recipient_country == "China"

    html_without_recipient_country = """
    <html><body>
      <div class="field"><div class="field__label">Product</div>
        <div class="field__item">Drugs</div></div>
      <dl><dt>Recipient:</dt><dd>Wenjun Liao</dd></dl>
      <dl><dt>Issuing Office:</dt><dd>CDER</dd>
        <dd><span class="country">United States</span></dd></dl>
      <div class="letter-body"><p>Warning letter body.</p></div>
    </body></html>
    """
    parsed_without_country = parse_warning_letter_html(html_without_recipient_country)
    assert parsed_without_country.recipient_country is None


def test_wholly_bold_paragraph_subtitles_become_safe_jump_headings() -> None:
    parsed = parse_warning_letter_html(TIANJIN_DETAIL_HTML)
    anchors = {anchor["text"]: anchor for anchor in parsed.anchors}
    mixed_text = "Important: this mixed paragraph remains body copy."

    assert anchors["FDA Review"]["kind"] == "heading"
    assert anchors["FDA Review"]["anchor"] == "fda-review"
    assert "display" not in anchors["FDA Review"]
    assert anchors["1. Failure to validate the manufacturing process."]["kind"] == "heading"
    assert anchors[mixed_text]["kind"] == "paragraph"
    assert anchors[mixed_text]["text"] == mixed_text
    assert anchors[mixed_text]["display"] == (
        "**Important:** this mixed paragraph remains body copy."
    )
    assert "### FDA Review" in parsed.normalized_markdown
    assert "**Important:** this mixed paragraph remains body copy." in parsed.normalized_markdown
    assert "<strong>" not in parsed.normalized_markdown
    assert "<strong>" not in str(parsed.anchors)

    chunks = build_chunks(parsed.anchors)
    chunk_text = "\n".join(chunk["content"] for chunk in chunks)
    assert mixed_text in parsed.normalized_text
    assert mixed_text in chunk_text
    assert "**Important:**" not in chunk_text


def test_csv_listing_has_stable_schema_and_candidates(fixture_dir: Path) -> None:
    path = fixture_dir / "listing_export.csv"
    listing = parse_listing(
        path.read_bytes(),
        source_url="https://www.fda.gov/warning-letters",
        final_url="https://www.fda.gov/warning-letters",
        content_type="text/csv",
        allowed_hosts=["www.fda.gov", "fda.gov"],
    )
    assert len(listing.candidates) == 6
    assert "canonical_url" in listing.detected_columns
    assert "posted_date" in listing.detected_columns
    assert len(listing.schema_fingerprint) == 64
    assert all(item.canonical_url.startswith("https://www.fda.gov/") for item in listing.candidates)


def test_html_listing_discovers_export(fixture_dir: Path) -> None:
    path = fixture_dir / "warning_letters_listing.html"
    listing = parse_listing(
        path.read_bytes(),
        source_url="https://www.fda.gov/warning-letters",
        content_type="text/html",
        allowed_hosts=["www.fda.gov", "fda.gov"],
    )
    assert listing.export_url is not None
    assert listing.export_url.startswith("https://www.fda.gov/")


def test_xlsx_listing_uses_official_company_cell_hyperlink() -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(
        ["Posted Date", "Letter Issue Date", "Company Name", "Issuing Office", "Subject"]
    )
    worksheet.append(
        [
            "08/30/2026",
            "08/20/2026",
            "Example Drug Company",
            "Center for Drug Evaluation and Research (CDER)",
            "CGMP/Finished Pharmaceuticals/Adulterated",
        ]
    )
    worksheet.cell(
        row=2, column=3
    ).hyperlink = "https://www.fda.gov/warning-letters/example-drug-company-123456"
    stream = io.BytesIO()
    workbook.save(stream)
    workbook.close()

    listing = parse_listing(
        stream.getvalue(),
        source_url="https://www.fda.gov/warning-letters/datatables-data?_format=xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        allowed_hosts=["www.fda.gov", "fda.gov"],
    )
    assert len(listing.candidates) == 1
    assert listing.candidates[0].company_name == "Example Drug Company"
    assert listing.candidates[0].canonical_url.endswith(
        "/warning-letters/example-drug-company-123456"
    )


def test_fda_datatables_configuration_builds_bounded_allowlisted_page_url() -> None:
    settings = {
        "datatables": {
            "stable-table-id": {
                "serverSide": True,
                "deferLoading": 3664,
                "aoColumnHeaders": [
                    {"content": "Posted Date"},
                    {"content": "Letter Issue Date"},
                    {"content": "Company Name"},
                ],
                "ajax": {
                    "url": "/datatables/views/ajax",
                    "data": {
                        "_drupal_ajax": 1,
                        "view_name": "warning_letter_solr_index",
                        "view_dom_id": "stable-table-id",
                        "total_items": 3664,
                    },
                },
            }
        }
    }
    html = f"<html><script>{json.dumps(settings)}</script></html>"
    config = discover_datatables_configuration(
        html,
        page_url="https://www.fda.gov/warning-letters",
        allowed_hosts=["www.fda.gov", "fda.gov"],
    )
    assert config is not None
    assert config.total_items == 3664
    assert config.columns == ["Posted Date", "Letter Issue Date", "Company Name"]
    page_url = config.page_url(
        start=1000,
        length=50_000,
        draw=2,
        allowed_hosts=["www.fda.gov", "fda.gov"],
    )
    assert page_url.startswith("https://www.fda.gov/datatables/views/ajax?")
    assert "length=1000" in page_url
    assert "start=1000" in page_url
    assert "view_name=warning_letter_solr_index" in page_url


def test_fda_datatables_json_preserves_canonical_detail_links() -> None:
    payload = {
        "draw": 1,
        "recordsTotal": 3664,
        "recordsFiltered": 3664,
        "data": [
            [
                '<time datetime="2026-08-04T04:00:00Z">08/04/2026</time>',
                '<time datetime="2026-07-24T04:00:00Z">07/24/2026</time>',
                (
                    '<a href="/inspections-compliance-enforcement-and-criminal-'
                    'investigations/warning-letters/example-pharma-735690-07242026">'
                    "Example Pharma</a>"
                ),
                "Center for Drug Evaluation and Research (CDER)",
                "CGMP/Finished Pharmaceuticals/Adulterated",
                "",
                "",
                "",
            ]
        ],
    }
    listing = parse_datatables_page(
        json.dumps(payload).encode(),
        source_url="https://www.fda.gov/datatables/views/ajax?draw=1&start=0&length=1000",
        columns=[
            "Posted Date",
            "Letter Issue Date",
            "Company Name",
            "Issuing Office",
            "Subject",
            "Response Letter",
            "Closeout Letter",
            "Excerpt",
        ],
        allowed_hosts=["www.fda.gov", "fda.gov"],
    )
    assert len(listing.candidates) == 1
    candidate = listing.candidates[0]
    assert candidate.company_name == "Example Pharma"
    assert candidate.posted_date is not None and candidate.posted_date.isoformat() == "2026-08-04"
    assert candidate.issue_date is not None and candidate.issue_date.isoformat() == "2026-07-24"
    assert candidate.canonical_url.endswith("/example-pharma-735690-07242026")
