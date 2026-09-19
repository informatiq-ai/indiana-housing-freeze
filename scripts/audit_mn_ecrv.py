"""Audit local eCRV ZIPs without extracting files or exporting party data.

This is a pre-ingestion audit, not a transaction store or XSD validator.
Windows-1252 recovery is explicit and only used after UTF-8 decoding fails.
"""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

METRO_CODES = {'02', '10', '19', '27', '62', '70', '82'}
MAX_MEMBERS = 100_000
MAX_MEMBER_BYTES = 10 * 1024 * 1024
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024


def parse_xml(raw, allow_cp1252=False):
    encoding = 'utf-8'
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        if not allow_cp1252:
            raise ValueError('invalid UTF-8; explicit legacy recovery required') from None
        text = raw.decode('cp1252')
        encoding = 'cp1252-recovery'
    # Reject alternate encodings, declarations and entities before parsing.
    declaration = re.match(r'\s*<\?xml[^?]*\?>', text)
    if declaration:
        match = re.search(r'encoding\s*=\s*[\'"]([^\'"]+)', declaration[0], re.I)
        if match and match[1].lower() not in {'utf-8', 'utf8'}:
            raise ValueError('unsupported declared encoding')
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('DTD/entity declarations are unsupported')
    root = ET.fromstring(text)
    if root.tag != 'ecrvForm':
        raise ValueError('unsupported root or namespace')
    return root, encoding


def audit_archive(path, allow_cp1252=False):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    fields, filled, counties, years, encodings = (Counter() for _ in range(5))
    repeating = Counter()
    keys, dates, errors = set(), [], Counter()
    parsed = duplicates = mismatches = 0
    with zipfile.ZipFile(path) as archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        total = sum(i.file_size for i in infos)
        if len(infos) > MAX_MEMBERS or total > MAX_ARCHIVE_BYTES:
            raise ValueError('archive exceeds configured audit limits')
        member_names = [i.filename for i in infos]
        duplicate_names = len(member_names) - len(set(member_names))
        for info in infos:
            if not info.filename.lower().endswith('.xml'):
                errors['non_xml_member'] += 1
                continue
            if info.file_size > MAX_MEMBER_BYTES:
                errors['oversize_member'] += 1
                continue
            try:
                with archive.open(info) as stream:
                    raw = stream.read(MAX_MEMBER_BYTES + 1)
                if len(raw) > MAX_MEMBER_BYTES:
                    raise ValueError('oversize_member')
                root, encoding = parse_xml(raw, allow_cp1252)
                county = root.findtext('headerForm/countyCde', '').strip()
                crv = root.findtext('headerForm/crvNumberId', '').strip()
                if not re.fullmatch(r'\d{2}', county) or not 1 <= int(county) <= 87 or not crv.isdigit():
                    raise ValueError('invalid_transaction_key')
                raw_date = root.findtext('salesAgreementForm/deedContractDate', '')
                sale_date = date.fromisoformat(raw_date[:10]).isoformat()
            except (ValueError, ET.ParseError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
                # Error classes only: XML text can contain personal information.
                errors[type(exc).__name__] += 1
                continue
            parsed += 1
            key = (county, crv)
            duplicates += key in keys
            keys.add(key)
            counties[county] += 1
            dates.append(sale_date)
            years[sale_date[:4]] += 1
            encodings[encoding] += 1
            mismatches += root.findtext('propertyForm/county') != county
            present, nonempty = set(), set()

            def visit(element, parent=''):
                node_path = parent + '/' + element.tag
                present.add(node_path)
                if (element.text or '').strip():
                    nonempty.add(node_path)
                for child in element:
                    visit(child, node_path)

            visit(root)
            fields.update(present)
            filled.update(nonempty)
            for name in ('parcels', 'mnPropertyAddresses', 'usesBeforeSale', 'plannedUses'):
                repeating[name] += len(root.findall('propertyForm/' + name)) > 1
    return {
        'archive': path.name, 'sha256': digest, 'compressed_bytes': path.stat().st_size,
        'uncompressed_bytes': total, 'members': len(infos), 'parsed_records': parsed,
        'failed_members': sum(errors.values()), 'errors_by_type': dict(sorted(errors.items())),
        'duplicate_member_names': duplicate_names, 'unique_transaction_keys': len(keys),
        'duplicate_transaction_keys': duplicates, 'county_mismatches': mismatches,
        'encoding_counts': dict(sorted(encodings.items())), 'counties': dict(sorted(counties.items())),
        'twin_cities_records': sum(counties[c] for c in METRO_CODES),
        'sale_date_min': min(dates) if dates else None,
        'sale_date_max': max(dates) if dates else None,
        'sale_year_counts': dict(sorted(years.items())),
        'records_with_multiple_children': dict(sorted(repeating.items())),
        'fields': [{'path': p, 'present_records': fields[p], 'nonempty_records': filled[p]}
                   for p in sorted(fields)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='ZIP file or folder recursively containing ZIPs')
    parser.add_argument('--allow-cp1252', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = ([args.input] if args.input.is_file() else
             sorted(p for p in args.input.rglob('*') if p.is_file() and p.suffix.lower() == '.zip'))
    if not paths:
        parser.error('no ZIP archives found')
    results = []
    for path in paths:
        try:
            results.append(audit_archive(path, args.allow_cp1252))
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            results.append({'archive': path.name, 'archive_error': type(exc).__name__})
    report = {'audit_version': 1, 'allow_cp1252': args.allow_cp1252, 'archives': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    failures = sum(bool(r.get('archive_error') or r.get('failed_members') or
                        r.get('duplicate_member_names') or r.get('duplicate_transaction_keys') or
                        r.get('county_mismatches')) for r in results)
    print(f'Audited {len(results)} archives; {failures} with errors. Report: {args.output}')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
