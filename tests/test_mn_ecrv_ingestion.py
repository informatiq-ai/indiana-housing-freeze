from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mn_ecrv.schema import RecordError, parse_record


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


if __name__ == "__main__":
    unittest.main()
