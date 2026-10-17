"""Privacy audit of locally generated analytical outputs.

These checks read real, gitignored outputs when they exist and skip otherwise,
so they run on a populated workstation without requiring data in CI. They
assert that no party, contact, or mailing field reaches an analytical export
and that retained free text carries no contact details.
"""

from pathlib import Path
import csv
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]

# Party and contact identifiers. Source flags that merely describe a party
# relationship (buyer_part_interest, seller_paid_points, name_change) are
# analytical fields, not identities, and are excluded by the lookarounds; the
# Indiana related_party flag marks a sale type in the same way.
PARTY_COLUMN = re.compile(
    r"(buyer(?!_?part)|seller(?!_?p(ai)?d)|grantor|grantee|purchaser|vendor|"
    r"phone|e_?mail|mailing|title_?company|closing_?agent|preparer|"
    r"first_?name|last_?name|full_?name|^name$|(?<!related_)party|signature|comment)",
    re.IGNORECASE,
)
# Property street detail is allowed only in the Minnesota compatibility export
# of property addresses; research outputs carry geography as county/ZIP codes.
STREET_COLUMN = re.compile(r"(street|address_?line|^address$)", re.IGNORECASE)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"\(?\b\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b")

RESEARCH_OUTPUTS = [
    "data/processed/research/transactions.parquet",
    "data/processed/research/transactions.csv",
    "data/processed/research/transactions_tiered.csv",
    "data/processed/research/county_month_tier.csv",
    "data/processed/research/county_month_tier_quantile.csv",
    "data/processed/research/county_month_market.csv",
    "data/processed/indiana_sdf_history.csv",
    "data/processed/mn/research_extract/ecrv_transactions.parquet",
    "data/processed/mn/research_extract/ecrv_uses.parquet",
    "data/processed/mn/research_extract/ecrv_parcels.parquet",
    "data/processed/mn/research_extract/ecrv_personal_property.parquet",
    "data/processed/mn/research_extract/ecrv_addresses.parquet",
]
COMPATIBILITY_OUTPUTS = [
    "data/processed/mn/ecrv_transactions.csv",
    "data/processed/mn/ecrv_parcels.csv",
    "data/processed/mn/ecrv_uses.csv",
    "data/processed/mn/ecrv_financing.csv",
    "data/processed/mn/ecrv_personal_property.csv",
    "data/processed/mn/ecrv_addresses.csv",
]
PERSONAL_PROPERTY_TEXT = "data/processed/mn/research_extract/ecrv_personal_property.parquet"


def columns(path):
    """Return column names from a CSV header or Parquet schema."""
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        return pq.read_schema(path).names
    with path.open(newline="", encoding="utf-8") as handle:
        return next(csv.reader(handle))


class PrivacyAuditTests(unittest.TestCase):
    def existing(self, relative_paths):
        paths = [ROOT / p for p in relative_paths if (ROOT / p).exists()]
        if not paths:
            self.skipTest("generated outputs are not present locally")
        return paths

    def test_research_outputs_have_no_party_or_street_columns(self):
        for path in self.existing(RESEARCH_OUTPUTS):
            with self.subTest(path=path.relative_to(ROOT)):
                flagged = [c for c in columns(path)
                           if PARTY_COLUMN.search(c) or STREET_COLUMN.search(c)]
                self.assertEqual(flagged, [])

    def test_compatibility_exports_have_no_party_columns(self):
        for path in self.existing(COMPATIBILITY_OUTPUTS):
            with self.subTest(path=path.relative_to(ROOT)):
                flagged = [c for c in columns(path) if PARTY_COLUMN.search(c)]
                self.assertEqual(flagged, [])

    def test_personal_property_text_has_no_contact_details(self):
        (path,) = self.existing([PERSONAL_PROPERTY_TEXT])
        import pyarrow.parquet as pq
        values = pq.read_table(path, columns=["propertyDescription"]).column(0).to_pylist()
        hits = [v for v in values if v and (EMAIL.search(v) or PHONE.search(v))]
        self.assertEqual(len(hits), 0, f"{len(hits)} description(s) contain contact patterns")


class PrivacyPatternTests(unittest.TestCase):
    """Synthetic checks that the column patterns separate flags from identities."""

    def test_patterns(self):
        for allowed in ("seller_paid_points", "buyer_part_interest", "name_change",
                        "county_name", "property_zip", "city", "related_party"):
            self.assertIsNone(PARTY_COLUMN.search(allowed), allowed)
        for blocked in ("buyer_name", "seller_phone", "grantee", "email",
                        "mailing_zip", "title_company", "name", "third_party"):
            self.assertIsNotNone(PARTY_COLUMN.search(blocked), blocked)
        self.assertIsNotNone(STREET_COLUMN.search("street1"))
        self.assertIsNotNone(PHONE.search("call 612-555-0100"))
        self.assertIsNone(PHONE.search("parcel 27-053-1234"))


if __name__ == "__main__":
    unittest.main()
