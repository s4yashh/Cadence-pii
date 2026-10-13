"""Central configuration: entity taxonomy, thresholds and feature toggles."""
from dataclasses import dataclass, field

# Entity taxonomy. Placeholder prefix is what appears in redacted text, e.g. [PERSON_3].
ENTITY_TYPES = {
    "PERSON": "Full or partial personal name",
    "EMAIL": "E-mail address",
    "PHONE": "Telephone / mobile number",
    "EMPLOYEE_ID": "Employee / vendor-personnel identifier (e.g. EMP-38104, DIR-0063, MER-IN-4471)",
    "US_SSN": "US Social Security number (full or last-four reference)",
    "PASSPORT": "Passport number",
    "TAX_ID": "Tax identifier (e.g. Indian PAN)",
    "NATIONAL_ID": "National identity number (e.g. Polish PESEL, UK NINO, Aadhaar)",
    "DATE_OF_BIRTH": "Date of birth",
    "ADDRESS": "Street / home address",
    "FINANCIAL_ACCOUNT": "Card or account number / fragment (e.g. 'card ending 2218')",
}

# Roll-up used in audit summaries (the brief asks specifically about government-issued IDs).
CATEGORY = {"US_SSN": "GOVERNMENT_ID", "PASSPORT": "GOVERNMENT_ID", "TAX_ID": "GOVERNMENT_ID",
            "NATIONAL_ID": "GOVERNMENT_ID", "EMAIL": "CONTACT", "PHONE": "CONTACT", "ADDRESS": "CONTACT",
            "PERSON": "NAME", "EMPLOYEE_ID": "EMPLOYEE_ID", "DATE_OF_BIRTH": "DATE_OF_BIRTH",
            "FINANCIAL_ACCOUNT": "FINANCIAL"}

# Presidio entity names mapped onto our taxonomy (anything not listed is ignored).
PRESIDIO_MAP = {
    "PERSON": "PERSON",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "US_SSN": "US_SSN",
    "US_PASSPORT": "PASSPORT",
    "IN_PAN": "TAX_ID",
    "IN_AADHAAR": "NATIONAL_ID",
    "UK_NINO": "NATIONAL_ID",
    "CREDIT_CARD": "FINANCIAL_ACCOUNT",
    "IBAN_CODE": "FINANCIAL_ACCOUNT",
    "US_BANK_NUMBER": "FINANCIAL_ACCOUNT",
}

# GLiNER labels mapped onto our taxonomy.
GLINER_MAP = {
    "person": "PERSON",
    "email": "EMAIL",
    "phone number": "PHONE",
    "social security number": "US_SSN",
    "passport number": "PASSPORT",
    "tax identification number": "TAX_ID",
    "date of birth": "DATE_OF_BIRTH",
    "address": "ADDRESS",
}

# Terms that NER models commonly mis-tag as PERSON in this corpus (organisations, products, roles).
# Matching is case-insensitive on the whole detected span.
PERSON_DENYLIST = {
    "cadence", "cadence financial group", "onetrust", "optiv", "board risk committee", "tprm",
    "rcsa", "kri", "kci", "raci", "ceo", "cfo", "coo", "cro", "cio", "dpo", "soc", "sla",
}


# Generic business / UI vocabulary that NER mislabels as PERSON in policy and configuration documents.
COMMON_WORDS = {
    "workflow", "policy", "vendor", "tier", "email", "cloud", "reviewer", "data", "approval", "owner", "risk",
    "template", "questionnaire", "attribute", "stage", "rule", "rules", "allowed", "collected", "please",
    "specify", "the", "notify", "reject", "launching", "send", "push", "peer", "setup", "admin", "user",
    "users", "group", "groups", "manager", "inventory", "engagement", "assessment", "contract", "service",
    "provider", "partner", "onboarding", "offboarding", "review", "status", "submit", "approve", "task",
    # document structure / rating vocabulary
    "appendix", "section", "figure", "table", "page", "chapter", "annex", "schedule", "part", "contents",
    "critical", "high", "medium", "low", "moderate", "elevated", "severe", "minor", "major", "unlikely",
    "likely", "rare", "almost", "certain", "possible", "biennial", "annual", "quarterly", "monthly",
    "continuous", "anonymous", "legal", "compliance", "uncontrolled", "printed", "internal", "confidential",
    "chief", "officer", "director", "head", "pillar", "actionability",
}


@dataclass
class Settings:
    use_presidio: bool = True
    use_gliner: bool = False              # optional layer; enable only if evaluation shows benefit
    gliner_model: str = "urchade/gliner_multi_pii-v1"
    gliner_threshold: float = 0.5
    presidio_threshold: float = 0.5       # minimum Presidio score kept in the primary pass
    verify_presidio_threshold: float = 0.35  # stricter (lower) threshold in the verification pass
    ocr_lang: str = "eng"
    ocr_min_block_conf: float = 60.0      # OCR blocks below this mean confidence -> human review
    ocr_min_words_for_conf: int = 5       # ignore confidence on tiny fragments (logos, icons)
    pdf_dual_ocr: bool = True             # independent full-resolution Tesseract view for PDF cross-check
    redact_all_dates: bool = False        # policy choice: only birth dates are personal by default
    max_file_mb: int = 100
    allowed_ext: tuple = (".pdf", ".docx", ".pptx")
    extra: dict = field(default_factory=dict)


DEFAULT = Settings()
