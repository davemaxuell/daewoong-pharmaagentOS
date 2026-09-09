"""Read-only live FDA acquisition check: python -m app.fda_probe.

Never writes to the application database or changes ingestion schedules.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.discovery import (
    ListingDiscoveryError,
    discover_datatables_configuration,
    parse_datatables_page,
    parse_listing,
)
from app.enums import ScopeStatus
from app.fda_client import FdaClient
from app.parsing import build_chunks, parse_warning_letter_html


async def probe(*, pages: int = 2, details: int = 2) -> dict:
    if not 1 <= pages <= 10 or not 0 <= details <= 5:
        raise ValueError("Use 1–10 listing pages and 0–5 detail samples")
    settings = get_settings()
    client = FdaClient(settings)
    fetched = await client.fetch(settings.fda_listing_url)
    listing = parse_listing(
        fetched.content,
        source_url=fetched.requested_url,
        final_url=fetched.final_url,
        content_type=fetched.content_type,
        allowed_hosts=settings.fda_allowed_hosts,
    )
    config = discover_datatables_configuration(
        fetched.content,
        page_url=fetched.final_url,
        allowed_hosts=settings.fda_allowed_hosts,
    )
    candidates = list(listing.candidates)
    report: dict = {
        "read_only": True,
        "server_side_table": bool(config),
        "pages": [],
        "letters": [],
    }
    if config:
        candidates = []
        seen = set()
        start = 0
        for draw in range(1, pages + 1):
            fetched_page = await client.fetch(
                config.page_url(
                    start=start,
                    length=1000,
                    draw=draw,
                    allowed_hosts=settings.fda_allowed_hosts,
                )
            )
            page = parse_datatables_page(
                fetched_page.content,
                source_url=fetched_page.final_url,
                columns=config.columns,
                allowed_hosts=settings.fda_allowed_hosts,
            )
            total = page.total_items if page.total_items is not None else config.total_items
            if not page.candidates or not any(c.canonical_url not in seen for c in page.candidates):
                raise ListingDiscoveryError("FDA pagination did not deliver new canonical letters")
            report["pages"].append({"offset": start, "rows": page.row_count, "total": total})
            for item in page.candidates:
                if item.canonical_url not in seen:
                    candidates.append(item)
                    seen.add(item.canonical_url)
            start += page.row_count or len(page.candidates)
            if start >= total:
                break
    if not candidates:
        raise ListingDiscoveryError("FDA listing did not expose warning letters")
    report["sampled_listing_rows"] = len(candidates)
    for candidate in candidates[:details]:
        detail = await client.fetch(candidate.canonical_url)
        parsed = parse_warning_letter_html(detail.content)
        report["letters"].append(
            {
                "url": candidate.canonical_url,
                "company": candidate.company_name,
                "posted_date": str(candidate.posted_date),
                "scope": parsed.scope.status.value,
                "product": parsed.scope.normalized_classes,
                "searchable_chunks": (
                    len(build_chunks(parsed.anchors))
                    if parsed.scope.status == ScopeStatus.IN_SCOPE_DRUGS
                    else 0
                ),
            }
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=2)
    parser.add_argument("--details", type=int, default=2)
    args = parser.parse_args()
    try:
        result = asyncio.run(probe(pages=args.pages, details=args.details))
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
    print(json.dumps({"ok": True, **result}, indent=2), flush=True)


if __name__ == "__main__":
    main()
