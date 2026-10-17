from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mn_squeeze.core_cities import geography_controls, relabel_core_cities
from mn_squeeze.external import extract_redfin, zip_summary
from mn_squeeze.sample import (
    assign_segments, build_sample, classify_uses, fit_segment_breaks, normalize_zip,
    property_zips,
)


def _cpi():
    months = pd.date_range("2015-01-01", "2025-12-01", freq="MS")
    return pd.DataFrame({
        "year": months.year, "month": months.month,
        "cpi": 100.0, "cpi_imputed": False,
    })


class MinnesotaSqueezeSampleTests(unittest.TestCase):
    def test_use_classification(self):
        evidence = pd.Series({
            "house": "RESID:SINGLEFAM", "legacy_house": "RES:HOUSESGL",
            "condo": "RESID:RESCONDO", "both_schemas": "RES:HOUSESGL|RESID:SINGLEFAM",
            "fourplex": "RESID:RESAPT4", "vacant": "RESID:RESVACANT",
            "mixed": "RESID:SINGLEFAM;OFFICE:GENOFFICE", "missing": None,
        })
        flags = classify_uses(evidence)
        self.assertEqual(flags["residential"].to_dict(), {
            "house": True, "legacy_house": True, "condo": True, "both_schemas": True,
            "fourplex": False, "vacant": False, "mixed": False, "missing": False,
        })
        self.assertEqual(flags["single_family"].to_dict(), {
            "house": True, "legacy_house": True, "condo": False, "both_schemas": True,
            "fourplex": False, "vacant": False, "mixed": False, "missing": False,
        })

    def test_zip_rules_match_indiana_pipeline(self):
        self.assertEqual(normalize_zip("55406-1234"), "55406")
        self.assertEqual(normalize_zip("55406.0"), "55406")
        self.assertEqual(normalize_zip(" 5540 "), "05540")
        self.assertIsNone(normalize_zip("00000"))
        self.assertIsNone(normalize_zip(""))
        self.assertIsNone(normalize_zip(None))

    def test_first_valid_zip_by_ordinal(self):
        addresses = pd.DataFrame([
            ("a", 2, "55104"), ("a", 1, None), ("a", 3, "55406"), ("b", 1, "bad"),
        ], columns=["source_key", "ordinal", "zip"])
        zips = property_zips(addresses).set_index("source_key")
        self.assertEqual(zips.loc["a", "zip_code"], "55104")
        self.assertEqual(zips.loc["a", "zip_count"], 2)
        self.assertNotIn("b", zips.index)

    def test_segment_fit_is_deterministic_and_right_closed(self):
        prices = pd.Series(np.repeat([200_000, 600_000, 2_000_000, 8_000_000], 25))
        fit = fit_segment_breaks(prices)
        self.assertEqual(fit, fit_segment_breaks(prices))
        self.assertEqual(fit["breaks"], [400_000.0, 1_300_000.0])
        labels = assign_segments(pd.Series([400_000, 400_001, 1_300_000, 1_300_001]), fit["breaks"])
        self.assertEqual(list(labels), ["entry", "move_up", "move_up", "luxury"])

    def test_build_sample_funnel_and_columns(self):
        rows = []
        for index, (price, evidence, eligible) in enumerate([
            (200_000, "RESID:SINGLEFAM", True), (600_000, "RESID:RESCONDO", True),
            (2_000_000, "RESID:SINGLEFAM", True), (8_000_000, "RESID:SINGLEFAM", True),
            (300_000, "OFFICE:GENOFFICE", True), (300_000, "RESID:SINGLEFAM", False),
            (900_000, "RES:TOWNHOUSE", True),
        ]):
            rows.append({
                "source_key": f"k{index}", "metro": "MSP", "county": "Dakota",
                "tier_type": "SUBURBAN_COLLAR", "core_city_status": "NOT_CORE_COUNTY",
                "sale_date": "2023-05-10", "sale_year": 2023, "sale_month": "2023-05",
                "gross_sale_price": price, "eligible_current_study": eligible,
                "property_type_evidence": evidence,
            })
        # A 2019 sale falls outside the original 2021–2025 study window.
        rows.append({**rows[1], "source_key": "k7", "sale_date": "2019-05-10",
                     "sale_year": 2019, "sale_month": "2019-05"})
        transactions = pd.DataFrame(rows)
        addresses = pd.DataFrame({
            "source_key": transactions["source_key"], "ordinal": 1, "zip": "55124",
        })
        addresses.loc[0, "zip"] = None
        sample, fit, funnel = build_sample(transactions, addresses, _cpi())
        self.assertEqual(funnel["records"].tolist(), [8, 7, 6, 5, 4])
        self.assertEqual(sample["source_key"].tolist(), ["k1", "k2", "k3", "k6"])
        self.assertEqual(
            sample["sale_price_2025"].tolist(), [600_000, 2_000_000, 8_000_000, 900_000]
        )
        self.assertEqual(fit["fit_records"], 4)
        forbidden = ("street", "name", "phone", "email", "mailing", "title")
        self.assertFalse(any(
            token in column.lower() for column in sample.columns for token in forbidden
        ))

    def test_price_basis_selects_fit_price(self):
        rows = [{
            "source_key": f"k{index}", "metro": "MSP", "county": "Dakota",
            "tier_type": "SUBURBAN_COLLAR", "core_city_status": "NOT_CORE_COUNTY",
            "sale_date": "2023-05-10", "sale_year": 2023, "sale_month": "2023-05",
            "gross_sale_price": price, "eligible_current_study": True,
            "property_type_evidence": "RESID:SINGLEFAM",
        } for index, price in enumerate([200_000, 600_000, 2_000_000, 7_000_000])]
        transactions = pd.DataFrame(rows)
        addresses = pd.DataFrame({
            "source_key": transactions["source_key"], "ordinal": 1, "zip": "55124",
        })
        # 2023 CPI at half the 2025 base doubles every real price.
        cpi = _cpi()
        cpi.loc[cpi["year"].eq(2023), "cpi"] = 50.0
        _, nominal, _ = build_sample(transactions, addresses, cpi, price_basis="nominal")
        _, real, _ = build_sample(transactions, addresses, cpi, price_basis="real")
        self.assertEqual(nominal["breaks"], [400_000.0, 1_300_000.0])
        self.assertEqual(real["breaks"], [800_000.0, 2_600_000.0])
        self.assertEqual(nominal["indiana_breaks"], [380_000, 1_050_000])
        self.assertEqual(real["indiana_breaks"], [407_000, 1_097_000])

    def test_core_city_relabel_and_controls(self):
        sample = pd.DataFrame({
            "county": ["Hennepin", "Hennepin", "Ramsey", "Ramsey", "Ramsey", "Dakota"],
            "core_city_status": ["CORE_CITY", "COUNTY_BALANCE", "CORE_CITY",
                                 "COUNTY_BALANCE", "MIXED", "NOT_CORE_COUNTY"],
        })
        self.assertEqual(relabel_core_cities(sample)["county"].tolist(), [
            "Minneapolis", "Hennepin balance", "St. Paul", "Ramsey balance", "Dakota",
        ])
        acs = pd.DataFrame([
            ("Anoka", 98_000, 360_000), ("Carver", 120_000, 100_000),
            ("Dakota", 105_000, 440_000), ("Scott", 120_000, 150_000),
            ("Washington", 114_000, 270_000), ("Hennepin", 96_000, 1_270_000),
            ("Ramsey", 81_000, 540_000), ("Minneapolis", 80_000, 430_000),
            ("St. Paul", 73_000, 310_000),
        ], columns=["area", "median_hhi", "population"])
        stpaul = geography_controls(acs, "stpaul_vs_collar")
        self.assertEqual(stpaul.loc[stpaul.geography.eq("metro"), "county"].tolist(), ["St. Paul"])
        self.assertNotIn("Minneapolis", stpaul["county"].tolist())
        everything = geography_controls(acs, "core_cities_vs_all_suburbs").set_index("county")
        # A county balance keeps the parent median and subtracts the city population.
        self.assertEqual(everything.loc["Hennepin balance", "median_hhi"], 96_000)
        self.assertEqual(everything.loc["Hennepin balance", "population"], 840_000)
        self.assertEqual(everything.loc["Ramsey balance", "population"], 230_000)
        self.assertEqual(everything.loc["Minneapolis", "geography"], "metro")

    def test_redfin_extract_matches_regions_exactly(self):
        import tempfile

        tracker = pd.DataFrame({
            "REGION": ["Hennepin County, MN", "Ramsey County, MN", "Hennepin County, MN",
                       "Anoka County, MN", "Polk County, MN"],
            "STATE_CODE": ["MN", "MN", "NE", "MN", "MN"],
            "PROPERTY_TYPE": "Single Family Residential",
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tracker.tsv000.gz"
            tracker.to_csv(path, sep="\t", index=False, compression="gzip")
            result = extract_redfin(path)
        self.assertEqual(sorted(result["REGION"]), [
            "Anoka County, MN", "Hennepin County, MN", "Ramsey County, MN",
        ])

    def test_zip_summary_threshold_and_affordability(self):
        sample = pd.DataFrame({
            "zip_code": ["55104"] * 10 + ["55406"] * 9,
            "county": ["Ramsey"] * 10 + ["Hennepin"] * 9,
            "sale_price": 300_000, "sale_price_2025": 320_000,
            "price_segment": ["move_up"] * 4 + ["entry"] * 15,
        })
        hhi = pd.DataFrame({"zip_code": ["55104"], "zcta_hhi": [80_000]})
        summary = zip_summary(sample, hhi, price_basis="real")
        self.assertEqual(summary["zip_code"].tolist(), ["55104"])
        row = summary.iloc[0]
        self.assertEqual(row["transactions"], 10)
        self.assertAlmostEqual(row["pct_move_up"], 40.0)
        rate = 0.062 / 12
        payment = 320_000 * 0.8 * rate * (1 + rate) ** 360 / ((1 + rate) ** 360 - 1)
        self.assertAlmostEqual(row["afford_ratio_zip"], payment * 12 / 80_000)


if __name__ == "__main__":
    unittest.main()
