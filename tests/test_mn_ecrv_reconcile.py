from pathlib import Path
import json
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mn_ecrv import PARSER_VERSION
from mn_ecrv.reconcile import reconcile
from mn_ecrv.schema import parse_record
from mn_ecrv.store import connect, insert_version, refresh_views


def xml(ecrv_id, price, county="27"):
    return f"""<ecrvForm>
      <headerForm><countyCde>{county}</countyCde><crvNumberId>{ecrv_id}</crvNumberId></headerForm>
      <propertyForm><county>{county}</county></propertyForm>
      <salesAgreementForm><deedContractDate>2024-01-02</deedContractDate>
      <totPurchaseAmt>{price}</totPurchaseAmt></salesAgreementForm>
      <supplementaryForm />
    </ecrvForm>""".encode()


def add_batch(database, batch_id, timestamp, members, errors=0):
    """Insert one synthetic archive with parsed members and quarantined errors."""
    database.execute(
        "INSERT INTO ingest_batches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
        [batch_id, batch_id, batch_id + ".zip", batch_id, timestamp, 1, PARSER_VERSION,
         "incomplete" if errors else "complete", len(members) + errors, len(members), 0, errors],
    )
    for ordinal, raw in enumerate(members, 1):
        record = parse_record(raw)
        record.transaction.update({
            "county_name": "Hennepin", "county_fips": "27053", "is_twin_cities": True,
        })
        version_id = insert_version(database, record)
        database.execute(
            "INSERT INTO record_observations VALUES (?,?,?,?,?,?)",
            [batch_id, ordinal, "member.xml", record.transaction["source_key"],
             version_id, record.raw_sha256],
        )
    for ordinal in range(errors):
        database.execute(
            "INSERT INTO quality_events VALUES (?,?,?,?,?,?,?,?)",
            [batch_id, batch_id + ".zip", len(members) + ordinal + 1, "bad.xml", "x",
             "nonpositive_sale_price", "error", None],
        )


class ReconcileTests(unittest.TestCase):
    def test_repeats_revisions_gaps_and_member_balance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = connect(root / "store.sqlite")
            add_batch(database, "w1", "2024-01-08T07:00:00",
                      [xml(1, "300000"), xml(2, "200000")], errors=1)
            # Key 1 repeats unchanged; key 2 is republished with a new price.
            add_batch(database, "w2", "2024-01-15T07:00:00",
                      [xml(1, "300000"), xml(2, "150000"), xml(3, "250000")])
            # Twelve days later: the intervening weekly window has no extract.
            add_batch(database, "w3", "2024-01-27T07:00:00", [xml(4, "400000")])
            database.commit()
            refresh_views(database)

            summary = reconcile(database, root / "quality")

            self.assertEqual(summary["distinct_transactions"], 4)
            self.assertEqual(summary["first_seen"], 4)
            self.assertEqual(summary["repeat_identical"], 1)
            self.assertEqual(summary["repeat_revised"], 1)
            self.assertTrue(summary["checks"]["members_balance_every_year"])
            self.assertTrue(summary["checks"]["quarantine_events_match_every_year"])
            self.assertFalse(summary["checks"]["no_probable_missing_weeks"])

            by_year = pd.read_csv(root / "quality/ecrv_reconciliation_by_extract_year.csv")
            row = by_year.iloc[0]
            self.assertEqual(row["members"], 7)
            self.assertEqual(row["quarantined_nonpositive_sale_price"], 1)

            revisions = pd.read_csv(root / "quality/ecrv_revision_summary.csv")
            changed = set(revisions["field"])
            self.assertIn("gross_sale_price", changed)
            self.assertNotIn("sale_date", changed)

            gaps = pd.read_csv(root / "quality/ecrv_extract_gaps.csv")
            self.assertIn("probable_missing_week", set(gaps["gap_class"]))

            saved = json.loads((root / "quality/ecrv_reconciliation_summary.json").read_text())
            self.assertEqual(saved["revised_transactions"], 1)
            database.close()


if __name__ == "__main__":
    unittest.main()
