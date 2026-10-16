from pathlib import Path
import sys
import unittest

import pandas as pd


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from inflation import add_real_price, normalize_monthly_cpi  # noqa: E402


class InflationTests(unittest.TestCase):
    def test_normalize_monthly_cpi_interpolates_only_interior_gap(self):
        months = pd.date_range("2025-01-01", "2025-12-01", freq="MS")
        source = pd.DataFrame(
            {
                "DATE": months.delete(1),
                "CPIAUCSL": [100.0] + [104.0] * 10,
            }
        )
        result = normalize_monthly_cpi(source, 2025, 2025)
        february = result.loc[result["sale_month"].eq("2025-02")].iloc[0]
        self.assertEqual(february["cpi"], 102.0)
        self.assertTrue(february["cpi_imputed"])

    def test_normalize_monthly_cpi_rejects_edge_gaps(self):
        source = pd.DataFrame(
            {"DATE": ["2025-02-01", "2025-12-01"], "CPIAUCSL": [100, 110]}
        )
        with self.assertRaisesRegex(ValueError, "unresolved edge gaps"):
            normalize_monthly_cpi(source, 2025, 2025)

    def test_add_real_price_uses_annual_average_2025_base(self):
        cpi = pd.DataFrame(
            {
                "year": [2024, 2025, 2025],
                "month": [1, 1, 2],
                "cpi": [100.0, 120.0, 140.0],
                "cpi_imputed": [False, False, False],
            }
        )
        sales = pd.DataFrame(
            {"year": [2024, 2025], "month": [1, 1], "sale_price": [100000, 120000]}
        )
        result, base = add_real_price(sales, cpi)
        self.assertEqual(base, 130.0)
        self.assertEqual(result.loc[0, "sale_price_2025"], 130000.0)
        self.assertEqual(result.loc[1, "sale_price_2025"], 130000.0)
        self.assertTrue(result["sale_price"].equals(sales["sale_price"]))


if __name__ == "__main__":
    unittest.main()
