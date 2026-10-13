"""Deterministic pattern layer. High precision for structured identifiers; context rules for
identifiers that are only meaningful next to a keyword ("card ending 2218", "DOB 14 July 1991").

Each rule: (entity_type, name, compiled_regex, score, group). `group` selects the sensitive part
of the match (0 = whole match), so the keyword itself is left visible for context.
"""
from __future__ import annotations

import re

from ..models import Finding

MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE = (rf"(?:\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH}\.?,?\s+\d{{4}}"
        rf"|{MONTH}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"
        r"|\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})"
        r"|\d{4}-\d{2}-\d{2})")
STREET_SUFFIX = (r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Lane|Ln\.?|Drive|Dr\.?|Boulevard|Blvd\.?|Crescent|"
                 r"Court|Ct\.?|Place|Pl\.?|Way|Terrace|Close|Square|Sq\.?|Parkway|Pkwy\.?|Highway|Hwy\.?)")
NAME_TOKEN = r"[A-Z][a-z]+(?:['’-][A-Z]?[a-z]+)*"

_F = re.IGNORECASE

RULES = [
    # --- contact details -------------------------------------------------------------
    ("EMAIL", "email",
     re.compile(r"(?<![\w.+-])[A-Za-z0-9][A-Za-z0-9._%+-]*\s?@\s?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b"), 0.99, 0),
    # North American with country code, incl. the short fictional form "+1 (555) 0114"
    ("PHONE", "phone_nanp_intl",
     re.compile(r"(?<![\w+])\+\s?1[\s.]*(?:\(\d{3}\)|\d{3})[\s.-]*(?:\d{3}[\s.-]?\d{4}|\d{4})(?![\d/])"), 0.95, 0),
    # Other international numbers: +CC then 2-5 digit groups; a group may not run into a date ("31/08/2026")
    ("PHONE", "phone_intl",
     re.compile(r"(?<![\w+])\+\s?(?!1\b)\d{2,3}(?:[\s.\-–—]{1,3}\(?\d{1,10}\)?(?![/\d])){1,5}"), 0.9, 0),
    ("PHONE", "phone_us_national",
     re.compile(r"(?<![\d-])(?:\(\d{3}\)\s?|\d{3}[-.])\d{3}[-.\s]\d{4}(?![\d-])"), 0.85, 0),
    ("PHONE", "phone_context",
     re.compile(r"\b(?:tel|phone|mobile|mob|cell|ext(?:ension)?)\b\.?[:\s]*((?:\+?\d[\d\s().-]{6,}\d))", _F), 0.8, 1),
    # --- identifiers -----------------------------------------------------------------
    ("EMPLOYEE_ID", "employee_id",
     re.compile(r"\b(?:EMP|DIR|STF|EMPL)[.,]?\s?[-–]?\s?\d{4,6}\b"), 0.95, 0),  # tolerates OCR "EMP.-38104"
    # vendor personnel IDs: MER-IN-4471, "MER- PH-2214"
    ("EMPLOYEE_ID", "vendor_personnel_id",
     re.compile(r"\b[A-Z]{3}-\s?[A-Z]{2}-\d{4}\b"), 0.85, 0),
    ("EMPLOYEE_ID", "employee_id_context",
     re.compile(r"\b(?:employee|staff|personnel)\s*(?:id|no|number)\b\.?[:\s#]*([A-Z0-9][A-Z0-9-]{3,12})\b", _F), 0.8, 1),
    ("US_SSN", "ssn",
     re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])"), 0.9, 0),
    ("US_SSN", "ssn_context_partial",
     re.compile(r"\b(?:SSN|social security(?: number)?)\b[^\d\n]{0,25}\(?(\d{4})\)?(?![\d-])", _F), 0.8, 1),
    ("PASSPORT", "passport_context",
     re.compile(r"\bpassport(?:\s*(?:no\.?|number|#))?[:\s#]*([A-Z]{1,2}\d{6,9})\b", _F), 0.95, 1),
    ("PASSPORT", "passport_shape",
     re.compile(r"\b[A-Z]{2}\d{7}\b"), 0.6, 0),
    ("NATIONAL_ID", "pesel_context",
     re.compile(r"\bPESEL\b[:\s#]*([\dxX*]{6,11})", _F), 0.95, 1),
    ("NATIONAL_ID", "uk_nino",
     re.compile(r"\b(?!BG|GB|NK|KN|TN|NT|ZZ)[A-CEGHJ-PR-TW-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b"), 0.8, 0),
    ("NATIONAL_ID", "national_id_context",
     re.compile(r"\b(?:national (?:id|identifier|identity number)|aadhaar|NINO|NI number)\b[:\s#]*([A-Z0-9][A-Z0-9 -]{5,16}[A-Z0-9])", _F), 0.85, 1),
    ("TAX_ID", "in_pan",
     re.compile(r"\b[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z]\b"), 0.9, 0),
    ("TAX_ID", "tax_context",
     re.compile(r"\b(?:PAN|TIN|EIN|tax (?:id|identifier|number))\b[:\s#]*([A-Z0-9][A-Z0-9-]{6,14})\b", _F), 0.85, 1),
    ("FINANCIAL_ACCOUNT", "account_fragment",
     re.compile(r"\b(?:card|account|acct)\b(?:\s+(?:number|no\.?))?\s+(?:ending(?:\s+in)?|no\.?|number|#)\s*[:#]?\s*(\d{4,19})\b", _F), 0.9, 1),
    ("FINANCIAL_ACCOUNT", "iban",
     re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}(?:\s?[A-Z0-9]{1,3})?\b"), 0.7, 0),
    # --- dates of birth (context-bound; other dates are not personal by default) -----
    ("DATE_OF_BIRTH", "dob_context",
     re.compile(rf"\b(?:DOB|D\.O\.B\.?|date of birth|birth\s?date|born(?:\s+on)?)\b[\s:,]*(?:is\s+|of\s+)?({DATE})", _F), 0.95, 1),
    # --- addresses -------------------------------------------------------------------
    ("ADDRESS", "street_address",
     re.compile(rf"\b\d{{1,5}}[ \t]+(?:{NAME_TOKEN}[ \t]){{1,3}}{STREET_SUFFIX}(?![A-Za-z])"
                r"(?:,?\s*(?:Apartment|Apt\.?|Suite|Ste\.?|Unit|Floor|Fl\.?)\s*[\w-]+)?"
                r"(?:,\s*[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+){0,2})?"
                r"(?:,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)?"), 0.85, 0),
    # --- names with strong surface cues (NER does the rest) ----------------------------
    # middle initial, tolerating OCR noise: "Caleb A, Whitfield", "Yusuf ©. Balogun", "lfeoma C. Adeyemi"
    ("PERSON", "name_middle_initial",
     re.compile(rf"(?:\b{NAME_TOKEN}|(?<![\w])l[a-z]{{3,}})(?:-{NAME_TOKEN})?\s[A-Z©][.,]\s{NAME_TOKEN}(?:-{NAME_TOKEN})?\b"), 0.9, 0),
    # initials + surname: "R. M. Achterberg", "M, T, Achebe", "L.-E. Brannstrom"
    ("PERSON", "name_initials_surname",
     re.compile(rf"(?<![\w.])(?:[A-Z][.,]-?\s?){{1,2}}{NAME_TOKEN}(?:-{NAME_TOKEN})?\b"), 0.6, 0),
    ("PERSON", "name_with_title",
     re.compile(rf"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof)\.?\s+{NAME_TOKEN}(?:[\s-]{NAME_TOKEN}){{0,2}}"), 0.85, 0),
]

# Business identifiers that look like PII patterns but are not personal (document refs, tickets).
NON_PII_PATTERNS = [
    re.compile(r"\b(?:GRP|ISS|INC|LOS|RSK|KRI|KCI|OP|POL)-[\w-]+\b"),
]


def detect_regex(text: str, offset: int = 0) -> list:
    out = []
    for etype, name, rx, score, grp in RULES:
        for m in rx.finditer(text):
            s, e = m.span(grp)
            if s < 0 or e <= s:
                continue
            val = text[s:e]
            # trim trailing punctuation that patterns can drag in
            while val and val[-1] in ".,;:)" and not (val.endswith(")") and "(" in val):
                val = val[:-1]
                e -= 1
            if not val.strip():
                continue
            digits = sum(c.isdigit() for c in val)
            if etype == "PHONE" and not (7 <= digits <= 15):
                continue
            # keyword-anchored identifier rules must capture something identifier-like
            if name.endswith("_context") and etype not in ("DATE_OF_BIRTH", "PHONE") and digits < 2:
                continue
            out.append(Finding(etype, s + offset, e + offset, val, score, "regex", name))
    return out


def non_pii_spans(text: str) -> list:
    return [m.span() for rx in NON_PII_PATTERNS for m in rx.finditer(text)]
