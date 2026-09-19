import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('audit', Path(__file__).resolve().parents[1] / 'scripts/audit_mn_ecrv.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def xml(county='27', crv='123', extra=''):
    return (f'<?xml version="1.0" encoding="UTF-8"?><ecrvForm>'
            f'<headerForm><countyCde>{county}</countyCde><crvNumberId>{crv}</crvNumberId></headerForm>'
            f'<propertyForm><county>{county}</county>{extra}</propertyForm>'
            '<salesAgreementForm><deedContractDate>2020-12-01T00:00:00-06:00</deedContractDate>'
            '</salesAgreementForm></ecrvForm>').encode()


class AuditTests(unittest.TestCase):
    def run_archive(self, entries, recovery=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                for name, data in entries:
                    archive.writestr(name, data)
            return audit.audit_archive(path, recovery)

    def test_grain_and_missing_fields(self):
        result = self.run_archive([('a.xml', xml(extra='<parcels/><parcels/>')), ('b.xml', xml(crv='124'))])
        self.assertEqual(result['parsed_records'], 2)
        self.assertEqual(result['twin_cities_records'], 2)
        self.assertEqual(result['records_with_multiple_children']['parcels'], 1)
        self.assertEqual(next(f for f in result['fields'] if f['path'].endswith('/parcels'))['nonempty_records'], 0)

    def test_legacy_recovery_is_explicit(self):
        raw = xml(extra='<legalDescription>PLACEHOLDER</legalDescription>').replace(b'PLACEHOLDER', b'\x93text\x94')
        self.assertEqual(self.run_archive([('a.xml', raw)])['failed_members'], 1)
        fixed = self.run_archive([('a.xml', raw)], True)
        self.assertEqual(fixed['encoding_counts'], {'cp1252-recovery': 1})

    def test_utf8_is_not_redecoded(self):
        root, encoding = audit.parse_xml(xml(extra='<legalDescription>café</legalDescription>'), True)
        self.assertEqual(encoding, 'utf-8')
        self.assertEqual(root.findtext('propertyForm/legalDescription'), 'café')

    def test_dtd_rejected(self):
        with self.assertRaises(ValueError):
            audit.parse_xml(b'<!DOCTYPE ecrvForm [<!ENTITY x "x">]><ecrvForm>&x;</ecrvForm>')

    def test_malformed_xml_not_repaired(self):
        result = self.run_archive([('a.xml', xml(extra='<bad>&</bad>'))], True)
        self.assertEqual(result['failed_members'], 1)

    def test_namespaces_rejected(self):
        with self.assertRaises(ValueError):
            audit.parse_xml(b'<ecrvForm xmlns="unknown"/>')

    def test_duplicates_and_county_scoped_ids(self):
        result = self.run_archive([('a.xml', xml()), ('b.xml', xml()), ('c.xml', xml(county='02'))])
        self.assertEqual(result['unique_transaction_keys'], 2)
        self.assertEqual(result['duplicate_transaction_keys'], 1)

    def test_no_extraction_or_party_values(self):
        result = self.run_archive([('../../outside.xml', xml(extra='<private>SECRET_VALUE</private>')), ('nested.zip', b'no')])
        self.assertNotIn('SECRET_VALUE', str(result))
        self.assertEqual(result['errors_by_type'], {'non_xml_member': 1})

    def test_size_limit(self):
        old = audit.MAX_MEMBER_BYTES
        try:
            audit.MAX_MEMBER_BYTES = 10
            self.assertEqual(self.run_archive([('a.xml', xml())])['errors_by_type'], {'oversize_member': 1})
        finally:
            audit.MAX_MEMBER_BYTES = old

    def test_invalid_key_and_date(self):
        result = self.run_archive([('a.xml', xml(county='99')), ('b.xml', xml().replace(b'2020-12-01', b'2020-99-01'))])
        self.assertEqual(result['failed_members'], 2)


if __name__ == '__main__':
    unittest.main()
