from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from indiana_sdf.pipeline import (
    apply_eligibility,
    deduplicate_records,
    detect_sdf_format,
    discover_sources,
    normalize_legacy_frame,
    normalize_modern_frames,
    normalize_zip,
)


def legacy_row(**overrides):
    row = {
        "SDF_ID": "49-2015-1", "County_ID": "49", "Conveyance_Date": "03/17/2015",
        "C6_Sales_Price": "250000", "PropZip": "46202-0001", "Parcel1": "A",
        "Parcel2": None, "Parcel3": None, "P2_6_Prop_Class_Code": "510",
        "P2_16_Valid_Trending": "Y", "P2_17_Validation_Complete": "Y",
        "B3_Vacant_Land_Assessor": "N", "B4_Trade_Assessor": "N",
        "B7_Relationship_Assessor": "N", "B8_Land_Contract_Assessor": "N",
        "B11_Partial_Interest_Assessor": "N", "B14_Charity_Assessor": "N",
        "Foreclosure": None, "Quitclaim": None,
    }
    row.update(overrides)
    return row


def modern_sale(**overrides):
    row = {
        "SDF_ID": "C49-2021-1", "County_ID": "49", "C7_Conveyance_Date": "2021-03-17",
        "E1_Sales_Price": "25000000", "B1_Valuable_Consider": "Y",
        "C1_Sheriff_Sale": "N", "C2_Short_Sale": "N", "C3_Quitclaim": "N",
        "C10_Residential_Property": "Y", "C10_Agricultural_Property": "N",
        "C10_Commercial_Property": "N", "C10_Industrial_Property": "N",
        "P2_16_Valid_Trending": "Y", "P2_17_Validation_Complete": "Y",
        "C8_Market_Days": "12",
    }
    row.update(overrides)
    return row


def modern_parcel(instance="1", zip_code="46202", property_class="510"):
    return {
        "SDF_ID": "C49-2021-1", "Parcel_Instance_No": instance,
        "A1_Parcel_Number": f"parcel-{instance}", "A3_Land": "Y",
        "A4_Improvement": "Y", "A5_ZipCode": zip_code,
        "P2_6_Prop_Class_Code": property_class,
    }


class IndianaSdfTests(unittest.TestCase):
    def test_zip_normalization(self):
        self.assertEqual(normalize_zip("46202-0001"), "46202")
        self.assertEqual(normalize_zip("602.0"), "00602")
        self.assertIsNone(normalize_zip("00000"))
        self.assertIsNone(normalize_zip("bad"))

    def test_legacy_units_geography_and_eligibility(self):
        frame = normalize_legacy_frame(pd.DataFrame([legacy_row()]), 2015, "2015.txt")
        result = apply_eligibility(frame).iloc[0]
        self.assertEqual(result["gross_sale_price"], 250000)
        self.assertEqual(result["county"], "Marion")
        self.assertEqual(result["county_fips"], "18097")
        self.assertEqual(result["tier_type"], "URBAN_CORE")
        self.assertTrue(result["eligible_current_study"])
        self.assertTrue(result["eligible_strict_comparable"])

    def test_legacy_invalid_date_and_vacant_class_are_excluded(self):
        frame = normalize_legacy_frame(pd.DataFrame([
            legacy_row(Conveyance_Date="03/17/2016", P2_6_Prop_Class_Code="500")
        ]), 2015, "2015.txt")
        result = apply_eligibility(frame).iloc[0]
        self.assertFalse(result["eligible_current_study"])
        self.assertIn("sale_year_mismatch", result["exclusion_reasons_current"])
        self.assertIn("not_improved_residential", result["exclusion_reasons_current"])

    def test_modern_units_and_multiple_parcels_do_not_multiply_sale(self):
        frame = normalize_modern_frames(
            pd.DataFrame([modern_sale()]),
            pd.DataFrame([modern_parcel("1"), modern_parcel("2", "46203", "511")]),
            2021, "SALEDISC2021.txt",
        )
        result = apply_eligibility(frame).iloc[0]
        self.assertEqual(len(frame), 1)
        self.assertEqual(result["gross_sale_price"], 250000)
        self.assertEqual(result["parcel_count"], 2)
        self.assertEqual(result["property_class_codes"], "510;511")
        self.assertTrue(result["eligible_current_study"])
        self.assertTrue(result["eligible_strict_comparable"])

    def test_modern_mixed_use_passes_neither_policy(self):
        sale = modern_sale(C10_Agricultural_Property="Y")
        frame = normalize_modern_frames(pd.DataFrame([sale]), pd.DataFrame([modern_parcel()]),
                                        2021, "SALEDISC2021.txt")
        result = apply_eligibility(frame).iloc[0]
        self.assertFalse(result["eligible_current_study"])
        self.assertFalse(result["eligible_strict_comparable"])
        self.assertIn("not_residential_only", result["exclusion_reasons_current"])

    def test_modern_current_can_pass_when_strict_fails(self):
        frame = normalize_modern_frames(
            pd.DataFrame([modern_sale(P2_16_Valid_Trending="N")]),
            pd.DataFrame([modern_parcel()]), 2021, "SALEDISC2021.txt",
        )
        result = apply_eligibility(frame).iloc[0]
        self.assertTrue(result["eligible_current_study"])
        self.assertFalse(result["eligible_strict_comparable"])
        self.assertIn("not_valid_for_trending", result["exclusion_reasons_strict"])

    def test_exact_duplicates_collapse_and_conflicts_quarantine(self):
        exact = normalize_legacy_frame(pd.DataFrame([legacy_row(), legacy_row()]), 2015, "2015.txt")
        deduplicated, events, dispositions = deduplicate_records(exact)
        self.assertEqual(len(deduplicated), 1)
        self.assertEqual(events.iloc[0]["issue_code"], "exact_duplicate_collapsed")
        self.assertEqual(dispositions["exact_duplicate_rows_removed"].sum(), 1)

        conflict = normalize_legacy_frame(pd.DataFrame([
            legacy_row(), legacy_row(C6_Sales_Price="260000")
        ]), 2015, "2015.txt")
        deduplicated, events, dispositions = deduplicate_records(conflict)
        self.assertTrue(deduplicated.empty)
        self.assertEqual(events.iloc[0]["issue_code"], "conflicting_duplicate_quarantined")
        self.assertEqual(dispositions["conflicting_rows_quarantined"].sum(), 2)

    def test_invalid_key_is_quarantined(self):
        frame = normalize_legacy_frame(pd.DataFrame([
            legacy_row(SDF_ID="not a valid id")
        ]), 2015, "2015.txt")
        deduplicated, events, dispositions = deduplicate_records(frame)
        self.assertTrue(deduplicated.empty)
        self.assertEqual(events.iloc[0]["issue_code"], "invalid_transaction_key")
        self.assertEqual(dispositions["invalid_key_rows"].sum(), 1)

    def test_missing_modern_parcel_fails_strict_only(self):
        frame = normalize_modern_frames(pd.DataFrame([modern_sale()]),
                                        pd.DataFrame(columns=list(modern_parcel())),
                                        2021, "SALEDISC2021.txt")
        result = apply_eligibility(frame).iloc[0]
        self.assertTrue(result["eligible_current_study"])
        self.assertFalse(result["eligible_strict_comparable"])
        self.assertIn("missing_parcel", result["exclusion_reasons_strict"])

    def test_header_dispatch_and_party_fields_are_not_exported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "2015.txt"
            columns = list(legacy_row()) + ["Buyer1", "Seller1"]
            path.write_text("|".join(columns) + "\n", encoding="cp1252")
            self.assertEqual(detect_sdf_format(path), "legacy_pipe_v1")
        frame = normalize_legacy_frame(pd.DataFrame([legacy_row()]), 2015, "2015.txt")
        self.assertFalse(any("buyer" in column.lower() or "seller" in column.lower()
                             for column in frame.columns))

    def test_modern_discovery_requires_parcel_partner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SALEDISC2026.txt"
            path.write_text("\t".join(sorted({
                "SDF_ID", "County_ID", "C7_Conveyance_Date", "E1_Sales_Price",
                "B1_Valuable_Consider", "C1_Sheriff_Sale", "C2_Short_Sale",
                "C3_Quitclaim", "C10_Residential_Property",
                "C10_Agricultural_Property", "C10_Commercial_Property",
                "C10_Industrial_Property", "P2_16_Valid_Trending",
                "P2_17_Validation_Complete",
            })) + "\n", encoding="utf-16")
            self.assertEqual(detect_sdf_format(path), "modern_multifile_v1")
            with self.assertRaisesRegex(FileNotFoundError, "SALEPARCEL2026.txt"):
                discover_sources(Path(directory))


if __name__ == "__main__":
    unittest.main()
