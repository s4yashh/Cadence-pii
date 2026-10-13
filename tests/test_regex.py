"""Pattern layer: boundaries, formats observed in the supplied artifacts, and non-PII look-alikes."""
from cadence_pii.detect.regex_rules import detect_regex


def found(text, etype=None):
    return sorted({(f.entity_type, f.value) for f in detect_regex(text) if etype in (None, f.entity_type)})


def test_email_basic_and_example_tld():
    assert ("EMAIL", "j.doe@example.com") in found("contact j.doe@example.com today")
    assert ("EMAIL", "a.b@corp.example") in found("a.b@corp.example |")


def test_email_with_ocr_space():
    assert found("x.y @example.com", "EMAIL")


def test_phone_formats():
    vals = {v for _, v in found("+1 (555) 0114 | +1 (212) 555-0147 | (305) 555-0143 | +44 7700 555 0163 "
                                "| +48 512555 0180 | +91 80 4555 0182", "PHONE")}
    for v in ["+1 (555) 0114", "+1 (212) 555-0147", "(305) 555-0143", "+44 7700 555 0163", "+48 512555 0180",
              "+91 80 4555 0182"]:
        assert v in vals, v


def test_phone_does_not_swallow_following_date():
    vals = {v for _, v in found("| +91 80 4555 0182          | 31/08/2026 |", "PHONE")}
    assert vals == {"+91 80 4555 0182"}


def test_phone_split_by_line_break():
    assert ("PHONE", "+1 917\n555-0143") in found("mobile +1 917\n555-0143)")


def test_employee_and_vendor_ids():
    assert {v for _, v in found("(EMP-38104) DIR-0063 MER-IN-4471", "EMPLOYEE_ID")} == {"EMP-38104", "DIR-0063",
                                                                                         "MER-IN-4471"}


def test_context_rule_does_not_match_plain_words():
    assert found("records that contain employee identifiers and national identifiers") == []


def test_government_ids():
    t = "SSN 900-55-2043, passport TK4820913, PAN AQBPR7741L, PESEL 890412xxxxx"
    types = {e for e, _ in found(t)}
    assert {"US_SSN", "PASSPORT", "TAX_ID", "NATIONAL_ID"} <= types


def test_partial_identifiers_need_context():
    t = "card ending 2218 and savings account ending 7741; last four digits of your social security number (8827)"
    f = found(t)
    assert ("FINANCIAL_ACCOUNT", "2218") in f and ("FINANCIAL_ACCOUNT", "7741") in f and ("US_SSN", "8827") in f
    assert found("the 2218 items were reviewed") == []


def test_dob_only_with_context():
    assert ("DATE_OF_BIRTH", "14 July 1991") in found("(EMP-1, DOB 14 July 1991)")
    assert ("DATE_OF_BIRTH", "3 August 1996") in found("and your date of birth, 3 August 1996.")
    assert not found("Effective date: 1 July 2026", "DATE_OF_BIRTH")


def test_address_and_no_false_match_across_lines():
    assert ("ADDRESS", "1180 Ashwood Lane, Apartment 4C, Jersey City, NJ 07302") in found(
        "home address at 1180 Ashwood Lane, Apartment 4C, Jersey City, NJ 07302.")
    assert not found("sample)\n\n2\n\nLeadership Structure", "ADDRESS")


def test_names_with_surface_cues():
    f = found("Miriam T. Achebe and Ms Prieto-Ramos met R. M. Achterberg", "PERSON")
    vals = {v for _, v in f}
    assert {"Miriam T. Achebe", "Ms Prieto-Ramos", "R. M. Achterberg"} <= vals


def test_business_references_are_not_pii():
    from cadence_pii.detect.regex_rules import non_pii_spans
    t = "ISS-2026-0112 GRP-POL-001 INC-2026-0417"
    assert len(non_pii_spans(t)) == 3
