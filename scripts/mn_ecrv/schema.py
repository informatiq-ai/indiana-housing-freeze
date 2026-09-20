"""Parse Minnesota eCRV XML without retaining buyer or seller data."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import xml.etree.ElementTree as ET

LEGACY_ROOT = "us.mn.state.mdor.ecrv.extract.form.EcrvForm"
MODERN_ROOT = "ecrvForm"
CLASS_PREFIX = "us.mn.state.mdor.ecrv.extract.form."
INVALID_NUMERIC_REF = re.compile(r"&#(?:(?P<dec>\d+)|[xX](?P<hex>[0-9A-Fa-f]+));")


class RecordError(ValueError):
    """A safe, machine-readable record rejection."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ParsedRecord:
    transaction: dict
    parcels: list
    addresses: list
    uses: list
    financing: list
    personal_property: list
    raw_sha256: str
    analytical_hash: str
    encoding: str
    parse_recovered: bool
    recovery_method: str | None
    schema_variant: str


def _xml_char_valid(value):
    return value in (0x9, 0xA, 0xD) or 0x20 <= value <= 0xD7FF or 0xE000 <= value <= 0xFFFD or 0x10000 <= value <= 0x10FFFF


def _repair_invalid_xml_characters(text):
    methods = []

    def replace_reference(match):
        value = int(match.group("dec") or match.group("hex"), 10 if match.group("dec") else 16)
        if _xml_char_valid(value):
            return match.group(0)
        if "invalid_numeric_reference" not in methods:
            methods.append("invalid_numeric_reference")
        return "\ufffd"

    text = INVALID_NUMERIC_REF.sub(replace_reference, text)
    cleaned = "".join(character for character in text if _xml_char_valid(ord(character)))
    if cleaned != text:
        methods.append("invalid_literal_character")
    return cleaned, methods


def decode_and_parse(raw, allow_cp1252=True, repair_invalid_chars=True):
    recovery = []
    try:
        text = raw.decode("utf-8-sig")
        encoding = "utf-8"
    except UnicodeDecodeError:
        if not allow_cp1252:
            raise RecordError("invalid_utf8") from None
        try:
            text = raw.decode("cp1252")
        except UnicodeDecodeError:
            raise RecordError("invalid_character_encoding") from None
        encoding = "cp1252"
        recovery.append("cp1252")
    declaration = re.match(r"\s*<\?xml[^?]*\?>", text)
    if declaration:
        match = re.search(r"encoding\s*=\s*['\"]([^'\"]+)", declaration[0], re.I)
        if match and match[1].lower() not in {"utf-8", "utf8"}:
            raise RecordError("unsupported_declared_encoding")
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise RecordError("unsupported_dtd_or_entity")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        if not repair_invalid_chars:
            raise RecordError("malformed_xml") from None
        repaired, methods = _repair_invalid_xml_characters(text)
        if not methods:
            raise RecordError("malformed_xml") from None
        try:
            root = ET.fromstring(repaired)
        except ET.ParseError:
            raise RecordError("malformed_xml") from None
        recovery.extend(methods)
    if root.tag not in {LEGACY_ROOT, MODERN_ROOT}:
        raise RecordError("unsupported_root")
    return root, encoding, recovery


def _text(root, path):
    value = root.findtext(path)
    return value.strip() if value else None


def _decimal(root, path, required=False):
    value = _text(root, path)
    if value is None:
        if required:
            raise RecordError("missing_required_amount")
        return None
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise RecordError("invalid_amount") from None
    if not result.is_finite():
        raise RecordError("invalid_amount")
    return str(result)


def _boolean(root, path):
    value = _text(root, path)
    if value is None:
        return None
    lowered = value.lower()
    if lowered in {"true", "1", "yes", "y"}:
        return True
    if lowered in {"false", "0", "no", "n"}:
        return False
    return None


def _rows(root, path):
    rows = []
    for container in root.findall(path):
        children = list(container)
        if len(children) == 1 and children[0].tag.startswith(CLASS_PREFIX):
            children = list(children[0])
        rows.append({child.tag: (child.text or "").strip() or None for child in children if not child.tag.startswith(CLASS_PREFIX)})
    return rows


def _schema_variant(root, deed_type):
    if root.tag == MODERN_ROOT:
        return "schema3_flat_2020_11_plus"
    property_use = root.find("propertyForm/usesBeforeSale/" + CLASS_PREFIX + "PlannedUseForm/propertyTypeCode")
    if property_use is not None:
        return "legacy_2015_property_codes"
    if deed_type:
        return "legacy_tiered_with_deed_type_2019_08_to_2020_11"
    return "legacy_tiered_2016_to_2019_08"


def _snake(value):
    return re.sub(r"(?<!^)(?=[A-Z0-9])", "_", value).lower()


def parse_record(raw, county_crosswalk=None, allow_cp1252=True, repair_invalid_chars=True):
    root, encoding, recovery = decode_and_parse(raw, allow_cp1252, repair_invalid_chars)
    county = _text(root, "headerForm/countyCde")
    ecrv_id = _text(root, "headerForm/crvNumberId")
    if not county or not re.fullmatch(r"\d{2}", county) or not 1 <= int(county) <= 87 or not ecrv_id or not ecrv_id.isdigit():
        raise RecordError("invalid_transaction_key")
    property_county = _text(root, "propertyForm/county")
    if property_county and property_county != county:
        raise RecordError("county_mismatch")
    raw_date = _text(root, "salesAgreementForm/deedContractDate")
    try:
        sale_date = date.fromisoformat((raw_date or "")[:10]).isoformat()
    except ValueError:
        raise RecordError("invalid_sale_date") from None
    price = _decimal(root, "salesAgreementForm/totPurchaseAmt", required=True)
    if Decimal(price) <= 0:
        raise RecordError("nonpositive_sale_price")
    crosswalk = (county_crosswalk or {}).get(county, {})
    deed_type = _text(root, "salesAgreementForm/deedTypeCde")
    transaction = {
        "source_key": f"MN:ecrv:{county}:{ecrv_id}", "mn_county_code": county,
        "county_name": crosswalk.get("name"), "county_fips": crosswalk.get("fips"),
        "is_twin_cities": county in (county_crosswalk or {}), "ecrv_id": ecrv_id,
        "sale_date": sale_date, "sale_year": int(sale_date[:4]), "sale_month": sale_date[:7],
        "gross_sale_price": price, "downpayment_equity": _decimal(root, "salesAgreementForm/downPmtEquity"),
        "seller_paid_points": _decimal(root, "salesAgreementForm/sellerPdPts"),
        "special_assessment_amount": _decimal(root, "salesAgreementForm/specialAssesmtAmt"),
        "finance_type": _text(root, "salesAgreementForm/financeType"), "deed_type": deed_type,
        "property_county": property_county, "principal_residence": _boolean(root, "propertyForm/principalResidence"),
        "new_buildings_sale_year": _boolean(root, "propertyForm/newBuildingsOnSaleYear"),
        "what_included": _text(root, "propertyForm/whatIsIncludedInSale"),
    }
    for field in ("relatedInd", "giftInd", "governmentInd", "legalActionInd", "nameChangeInd", "nonMarketPriceInd", "nonListedInd", "taxExemptInd"):
        transaction[_snake(field[:-3])] = _boolean(root, "supplementaryForm/" + field)
    for field in ("buyerPartInterest", "deedPayoff", "agreement2YrsOld", "likeKindExchange", "receivedInTrade"):
        transaction[_snake(field)] = _boolean(root, "salesAgreementForm/" + field)
    parcels = _rows(root, "propertyForm/parcels")
    addresses = _rows(root, "propertyForm/mnPropertyAddresses")
    uses = [{"use_timing": timing, **row} for timing, path in (("before", "propertyForm/usesBeforeSale"), ("planned", "propertyForm/plannedUses")) for row in _rows(root, path)]
    financing = _rows(root, "salesAgreementForm/financeArrangements")
    personal = _rows(root, "salesAgreementForm/personalProperties")
    analytical = {"transaction": transaction, "parcels": parcels, "addresses": addresses, "uses": uses, "financing": financing, "personal_property": personal}
    analytical_hash = hashlib.sha256(json.dumps(analytical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ParsedRecord(transaction, parcels, addresses, uses, financing, personal,
                        hashlib.sha256(raw).hexdigest(), analytical_hash, encoding,
                        bool(recovery), "+".join(recovery) or None, _schema_variant(root, deed_type))
