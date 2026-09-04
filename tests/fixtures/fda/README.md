# Synthetic FDA parser fixtures

These fixtures mimic supported FDA page structures without copying full official letters. They are deterministic test data, not regulatory evidence and not suitable for user-facing publication.

`fixture_manifest.yaml` records the expected scope status and important parser outcomes. The blocking scope invariant is:

- a canonical Product value containing exact normalized `Drugs` is `IN_SCOPE_DRUGS`;
- parsed Product metadata without `Drugs` is `OUT_OF_SCOPE`;
- missing, empty, or contradictory Product metadata is `AMBIGUOUS` and withheld.

`listing_export.csv` uses the column labels expected from an FDA-compatible listing export and can be opened by spreadsheet software. `warning_letters_listing.html` represents the listing-page/export-link discovery fallback.

