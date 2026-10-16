from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mn_ecrv.schema import RecordError, parse_record
from mn_ecrv.store import connect, insert_versions, refresh_views


def modern(extra_property="", extra_sales="", extra_supplementary="", party=""):
    return (f'''<?xml version="1.0" encoding="UTF-8"?>
<ecrvForm><headerForm><countyCde>27</countyCde><crvNumberId>123</crvNumberId></headerForm>
<buyersForm><individuals><firstName>{party}</firstName></individuals></buyersForm>
<propertyForm><county>27</county>{extra_property}</propertyForm>
<salesAgreementForm><deedContractDate>2024-01-02T00:00:00-06:00</deedContractDate>
<totPurchaseAmt>300000.0000</totPurchaseAmt><downPmtEquity>60000</downPmtEquity>
<financeType>CONV</financeType>{extra_sales}</salesAgreementForm>
<supplementaryForm>{extra_supplementary}</supplementaryForm></ecrvForm>''').encode()


class SchemaTests(unittest.TestCase):
    crosswalk = {"27": {"name": "Hennepin", "fips": "27053"}}

    def test_modern_record_and_no_party_data(self):
        record = parse_record(modern(
            '<parcels><id>1</id><parcelId>01-001</parcelId><primary>true</primary></parcels>',
            party="DO_NOT_EXPORT"), self.crosswalk)
        self.assertEqual(record.transaction["source_key"], "MN:ecrv:27:123")
        self.assertEqual(record.transaction["gross_sale_price"], "300000.0000")
        self.assertEqual(record.parcels[0]["parcelId"], "01-001")
        self.assertNotIn("DO_NOT_EXPORT", str(record))
        self.assertEqual(record.schema_variant, "schema3_flat_2020_11_plus")

    def test_legacy_wrapper_rows_are_unwrapped(self):
        raw = modern(
            '<usesBeforeSale><us.mn.state.mdor.ecrv.extract.form.PlannedUseForm>'
            '<tier1Cde>RESID</tier1Cde><tier2Cde>SINGLEFAM</tier2Cde>'
            '</us.mn.state.mdor.ecrv.extract.form.PlannedUseForm></usesBeforeSale>',
        ).replace(b'<ecrvForm>', b'<us.mn.state.mdor.ecrv.extract.form.EcrvForm>').replace(
            b'</ecrvForm>', b'</us.mn.state.mdor.ecrv.extract.form.EcrvForm>')
        record = parse_record(raw, self.crosswalk)
        self.assertEqual(record.uses, [{"use_timing": "before", "tier1Cde": "RESID", "tier2Cde": "SINGLEFAM"}])
        self.assertEqual(record.schema_variant, "legacy_tiered_2016_to_2019_08")

    def test_cp1252_and_invalid_numeric_reference_recovery(self):
        raw = modern(extra_property='<legalDescription>PLACE &#11; “NAME”</legalDescription>')
        raw = raw.replace('“'.encode(), b'\x93').replace('”'.encode(), b'\x94')
        record = parse_record(raw, self.crosswalk)
        self.assertTrue(record.parse_recovered)
        self.assertEqual(record.recovery_method, "cp1252+invalid_numeric_reference")

    def test_invalid_literal_control_recovery(self):
        raw = modern().replace(b'</propertyForm>', b'<legalDescription>A\x0bB</legalDescription></propertyForm>')
        record = parse_record(raw, self.crosswalk)
        self.assertEqual(record.recovery_method, "invalid_literal_character")

    def test_undefined_cp1252_byte_is_quarantined(self):
        with self.assertRaisesRegex(RecordError, "invalid_character_encoding"):
            parse_record(modern().replace(b"</propertyForm>", b"<x>\x81</x></propertyForm>"), self.crosswalk)

    def test_structural_damage_is_quarantined(self):
        with self.assertRaisesRegex(RecordError, "malformed_xml"):
            parse_record(modern(extra_property="<bad>&</bad>"), self.crosswalk)

    def test_required_fields_are_validated(self):
        with self.assertRaisesRegex(RecordError, "missing_required_amount"):
            parse_record(modern().replace(b'<totPurchaseAmt>300000.0000</totPurchaseAmt>', b''), self.crosswalk)

    def test_research_flags_remain_nullable(self):
        record = parse_record(modern(extra_supplementary='<nonMarketPriceInd>true</nonMarketPriceInd>'), self.crosswalk)
        self.assertTrue(record.transaction["non_market_price"])
        self.assertIsNone(record.transaction["gift"])

    def test_personal_property_inclusion_flag_is_retained(self):
        record = parse_record(modern(
            extra_sales="<personalPropertyIncludedInTotal>true</personalPropertyIncludedInTotal>"
        ), self.crosswalk)
        self.assertTrue(record.transaction["personal_property_included"])

    def test_batched_store_selects_latest_and_retains_first_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            database = connect(Path(directory) / "ecrv.sqlite")
            first = parse_record(modern(), self.crosswalk)
            revised = parse_record(
                modern().replace(b"300000.0000", b"310000.0000"), self.crosswalk
            )
            version_ids = insert_versions(database, [first, revised])
            for batch_id, archive_hash, observed, version_id, record in (
                ("batch-1", "archive-1", "2024-01-08T07:00:00", version_ids[0], first),
                ("batch-2", "archive-2", "2024-02-05T07:00:00", version_ids[1], revised),
            ):
                database.execute("""INSERT INTO ingest_batches (
                    batch_id, archive_sha256, archive_name, archive_path,
                    extract_timestamp, archive_bytes, parser_version, status,
                    member_count, valid_count, recovered_count, error_count
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", [
                    batch_id, archive_hash, f"{batch_id}.zip", f"/{batch_id}.zip",
                    observed, 100, "1.1.0", "complete", 1, 1, 0, 0,
                ])
                database.execute(
                    "INSERT INTO record_observations VALUES (?,?,?,?,?,?)",
                    [batch_id, 1, "27_123.xml", record.transaction["source_key"],
                     version_id, record.raw_sha256],
                )
            database.commit()
            refresh_views(database)
            row = database.execute("""SELECT gross_sale_price,
                first_extract_timestamp, extract_timestamp
                FROM current_transactions""").fetchone()
            database.close()
            self.assertEqual(row, (
                "310000.0000", "2024-01-08T07:00:00", "2024-02-05T07:00:00"
            ))


if __name__ == "__main__":
    unittest.main()
