from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mn_ecrv import PARSER_VERSION
from mn_ecrv.schema import parse_record
from mn_ecrv.store import batch_complete, connect, insert_version, refresh_views


def xml(price):
    return f"""<ecrvForm>
      <headerForm><countyCde>27</countyCde><crvNumberId>123</crvNumberId></headerForm>
      <propertyForm><county>27</county></propertyForm>
      <salesAgreementForm><deedContractDate>2024-01-02</deedContractDate>
      <totPurchaseAmt>{price}</totPurchaseAmt></salesAgreementForm>
      <supplementaryForm />
    </ecrvForm>""".encode()


class StoreTests(unittest.TestCase):
    def test_latest_extract_wins_and_versions_remain(self):
        with tempfile.TemporaryDirectory() as directory:
            database = connect(Path(directory) / "test.sqlite")
            older = parse_record(xml("300000"))
            newer = parse_record(xml("310000"))
            for batch_id, archive_hash, observed, record in (
                ("new:1", "new", "2024-02-01T07:00:00", newer),
                ("old:1", "old", "2024-01-01T07:00:00", older),
            ):
                database.execute(
                    "INSERT INTO ingest_batches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                    [batch_id, archive_hash, batch_id + ".zip", batch_id, observed, 1,
                     PARSER_VERSION, "complete", 1, 1, 0, 0],
                )
                version_id = insert_version(database, record)
                database.execute(
                    "INSERT INTO record_observations VALUES (?,?,?,?,?,?)",
                    [batch_id, 1, "27_123.xml", record.transaction["source_key"],
                     version_id, record.raw_sha256],
                )
            database.commit()
            refresh_views(database)
            self.assertEqual(database.execute(
                "SELECT gross_sale_price FROM current_transactions"
            ).fetchone()[0], "310000")
            self.assertEqual(database.execute("SELECT count(*) FROM record_versions").fetchone()[0], 2)
            self.assertTrue(batch_complete(database, "new"))
            database.close()


if __name__ == "__main__":
    unittest.main()
