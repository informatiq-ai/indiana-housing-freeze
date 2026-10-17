from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "research"))
from longitudinal import (
    OUTPUT_COLUMNS, classify_core_city, prepare_indiana, prepare_minnesota, regime_for_year,
)


class LongitudinalResearchTests(unittest.TestCase):
    def test_harmonized_contract_excludes_party_data(self):
        forbidden = (
            "buyer_name", "seller_name", "telephone", "phone", "email",
            "mailing_address", "title_company",
        )
        self.assertFalse(any(
            token in column.lower() for column in OUTPUT_COLUMNS for token in forbidden
        ))

    def test_regime_assignment(self):
        self.assertEqual(regime_for_year(2019), "BASELINE")
        self.assertEqual(regime_for_year(2020), "PANDEMIC_LOW_RATE")
        self.assertEqual(regime_for_year(2025), "HIGH_RATE_LOCK_IN")
        self.assertIsNone(regime_for_year(2026))

    def test_indiana_primary_cohort_uses_single_family_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "indiana.csv"
            pd.DataFrame([{
                "source_key": "IN:SDF:C49-2024-1", "source_format": "modern_multifile_v1",
                "source_file": "SALEDISC2024.txt", "sale_date": "2024-01-03",
                "sale_year": 2024, "sale_month": "2024-01", "county": "Marion",
                "county_fips": "18097", "metro": "INDY", "tier_type": "URBAN_CORE",
                "gross_sale_price": 300000, "parcel_count": 1,
                "property_class_codes": "520", "all_parcels_single_family": False,
                "eligible_current_study": True, "eligible_strict_comparable": True,
                "exclusion_reasons_current": "", "exclusion_reasons_strict": "",
                "source_status_conflict": False, "validation_complete": True,
                "valid_for_trending": True, "all_parcels_improved_residential": True,
            }]).to_csv(path, index=False)
            result = prepare_indiana(path, 2015, 2025).iloc[0]
            self.assertFalse(result["single_family"])
            self.assertFalse(result["research_eligible"])
            self.assertEqual(result["exclusion_reasons_research"], "not_single_family")

    def test_minnesota_eligibility_and_adjusted_price(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transaction = {
                "source_key": "MN:ecrv:27:123", "schema_variant": "schema3_flat_2020_11_plus",
                "sale_date": "2024-02-01", "sale_year": 2024, "sale_month": "2024-02",
                "county_name": "Hennepin", "county_fips": "27053", "is_twin_cities": 1,
                "gross_sale_price": "300000.0000", "seller_paid_points": "1000.0000",
                "personal_property_included": 1, "revision_conflict": 0,
                "parse_recovered": 0, "recovery_method": None,
                "first_extract_timestamp": "2024-02-05T07:00:00",
                "extract_timestamp": "2024-02-05T07:00:00", "archive_name": "sample.zip",
                "version_id": "version:1.1.0", "deed_type": "WARRNTY",
                "new_buildings_sale_year": 0,
            }
            transaction.update({flag: 0 for flag in (
                "related", "gift", "government", "legal_action", "name_change",
                "non_market_price", "tax_exempt", "buyer_part_interest", "deed_payoff",
                "like_kind_exchange", "received_in_trade",
            )})
            pd.DataFrame([transaction]).to_csv(root / "ecrv_transactions.csv", index=False)
            pd.DataFrame([{
                "source_key": transaction["source_key"], "use_timing": "before",
                "tier1Cde": "RESID", "tier2Cde": "SINGLEFAM",
                "propertyTypeCode": None, "propertyUseCode": None,
            }]).to_csv(root / "ecrv_uses.csv", index=False)
            pd.DataFrame([{
                "source_key": transaction["source_key"], "parcelId": "01-001"
            }]).to_csv(root / "ecrv_parcels.csv", index=False)
            pd.DataFrame([{
                "source_key": transaction["source_key"], "selected": "true",
                "propertyValue": "5000.0000",
            }]).to_csv(root / "ecrv_personal_property.csv", index=False)
            pd.DataFrame([{
                "source_key": transaction["source_key"], "city": "8800", "zip": "55406-1234",
            }]).to_csv(root / "ecrv_addresses.csv", index=False)

            result = prepare_minnesota(root, 2015, 2025).iloc[0]
            self.assertEqual(result["core_city_status"], "CORE_CITY")
            self.assertTrue(result["single_family"])
            self.assertTrue(result["eligible_current_study"])
            self.assertTrue(result["eligible_strict_comparable"])
            self.assertTrue(result["research_eligible"])
            self.assertEqual(result["adjusted_price"], 294000)
            self.assertEqual(result["tier_type"], "URBAN_CORE")
            self.assertEqual(result["reporting_lag_days"], 4)
            self.assertEqual(result["reporting_maturity_days"], 4)
            self.assertFalse(result["recent_reporting_period"])

            transaction["personal_property_included"] = 0
            pd.DataFrame([transaction]).to_csv(root / "ecrv_transactions.csv", index=False)
            not_included = prepare_minnesota(root, 2015, 2025).iloc[0]
            self.assertEqual(not_included["personal_property_total"], 0)
            self.assertEqual(not_included["adjusted_price"], 299000)

            for stem in (
                "ecrv_transactions", "ecrv_uses", "ecrv_parcels",
                "ecrv_personal_property", "ecrv_addresses",
            ):
                csv_path = root / f"{stem}.csv"
                pd.read_csv(csv_path).to_parquet(root / f"{stem}.parquet", index=False)
                csv_path.unlink()
            parquet_result = prepare_minnesota(root, 2015, 2025).iloc[0]
            self.assertEqual(parquet_result["adjusted_price"], 299000)

    def test_minnesota_unknown_flag_fails_strict_but_not_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transaction = {
                "source_key": "MN:ecrv:02:456", "schema_variant": "legacy_2015_property_codes",
                "sale_date": "2015-06-01", "sale_year": 2015, "sale_month": "2015-06",
                "county_name": "Anoka", "county_fips": "27003", "is_twin_cities": 1,
                "gross_sale_price": "200000", "seller_paid_points": "0",
                "personal_property_included": 0, "revision_conflict": 0,
                "parse_recovered": 1, "recovery_method": "cp1252",
                "first_extract_timestamp": "2015-06-08T07:00:00",
                "extract_timestamp": "2015-06-08T07:00:00", "archive_name": "sample.zip",
                "version_id": "version:1.1.0", "deed_type": None,
                "new_buildings_sale_year": 0, "related": None,
            }
            for flag in (
                "gift", "government", "legal_action", "name_change", "non_market_price",
                "tax_exempt", "buyer_part_interest", "deed_payoff", "like_kind_exchange",
                "received_in_trade",
            ):
                transaction[flag] = 0
            pd.DataFrame([transaction]).to_csv(root / "ecrv_transactions.csv", index=False)
            pd.DataFrame([{
                "source_key": transaction["source_key"], "use_timing": "before",
                "tier1Cde": None, "tier2Cde": None,
                "propertyTypeCode": "RES", "propertyUseCode": "HOUSESGL",
            }]).to_csv(root / "ecrv_uses.csv", index=False)
            pd.DataFrame([{
                "source_key": transaction["source_key"], "parcelId": "parcel"
            }]).to_csv(root / "ecrv_parcels.csv", index=False)
            pd.DataFrame(columns=["source_key", "selected", "propertyValue"]).to_csv(
                root / "ecrv_personal_property.csv", index=False
            )
            pd.DataFrame(columns=["source_key", "city", "zip"]).to_csv(
                root / "ecrv_addresses.csv", index=False
            )

            result = prepare_minnesota(root, 2015, 2025).iloc[0]
            self.assertEqual(result["core_city_status"], "NOT_CORE_COUNTY")
            self.assertTrue(result["eligible_current_study"])
            self.assertFalse(result["eligible_strict_comparable"])
            self.assertFalse(result["strict_eligibility_available"])
            self.assertIn("related_or_unknown", result["exclusion_reasons_strict"])
            self.assertIn("deed_type_unknown", result["exclusion_reasons_strict"])


    def test_core_city_classification(self):
        counties = pd.Series({
            "core": "Hennepin", "balance": "Hennepin", "other_core_code": "Hennepin",
            "mixed": "Ramsey", "blank_ignored": "Ramsey", "no_address": "Ramsey",
            "all_blank": "Hennepin", "collar": "Anoka",
        })
        addresses = pd.DataFrame([
            ("core", "8800"), ("core", "8800"), ("balance", "4100"),
            # St. Paul's code in Hennepin is not a core-city address.
            ("other_core_code", "8900"),
            ("mixed", "8900"), ("mixed", "0400"),
            ("blank_ignored", None), ("blank_ignored", "8900"),
            ("all_blank", None), ("collar", "8800"),
        ], columns=["source_key", "city"])
        status = classify_core_city(addresses, counties)
        self.assertEqual(status.to_dict(), {
            "core": "CORE_CITY", "balance": "COUNTY_BALANCE",
            "other_core_code": "COUNTY_BALANCE", "mixed": "MIXED",
            "blank_ignored": "CORE_CITY", "no_address": "UNKNOWN",
            "all_blank": "UNKNOWN", "collar": "NOT_CORE_COUNTY",
        })


if __name__ == "__main__":
    unittest.main()
