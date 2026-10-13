"""Overlap resolution, name filtering/propagation and placeholder redaction."""
from cadence_pii.detect import merge
from cadence_pii.models import Finding
from cadence_pii.redact import masked_context, redact


def F(t, s, e, text, method="regex", score=0.9):
    return Finding(t, s, e, text[s:e], score, method, "test")


def test_overlap_keeps_union_and_structured_type():
    text = "mail m.achebe@example.com now"
    a = F("EMAIL", 5, 25, text)
    b = F("PERSON", 5, 13, text, "presidio", 0.85)
    out = merge.resolve([a, b])
    assert len(out) == 1 and out[0].entity_type == "EMAIL" and (out[0].start, out[0].end) == (5, 25)
    assert out[0].method == "presidio+regex"


def test_resolution_is_deterministic():
    text = "Miriam T. Achebe"
    fs = [F("PERSON", 0, 16, text), F("PERSON", 10, 16, text, "presidio")]
    assert [(f.start, f.end) for f in merge.resolve(fs)] == [(f.start, f.end) for f in merge.resolve(fs[::-1])]


def test_common_words_are_not_people():
    text = "Open the Workflow page. Every workflow has an owner. Vendor Tier is set per vendor tier."
    a, b = text.index("Workflow"), text.index("Vendor Tier")
    fs = [F("PERSON", a, a + 8, text, "presidio"), F("PERSON", b, b + 11, text, "presidio")]
    assert merge.clean(fs, text, []) == []


def test_camelcase_and_markup_rejected():
    text = "OneTrust and RP\\_T\\_Push"
    fs = [F("PERSON", 0, 8, text, "presidio"), F("PERSON", 13, len(text), text, "presidio")]
    assert merge.clean(fs, text, []) == []


def test_role_suffix_trimmed():
    text = "| S. Aarnio Dir. TPRM |"
    out = merge.clean([F("PERSON", 2, 15, text, "presidio")], text, [])
    assert out and out[0].value == "S. Aarnio"


def test_propagation_from_names_and_emails():
    text = ("Rafael E. Duarte reported it. Later Duarte confirmed. Led by Priyanka Raghunathan. "
            "p.raghunathan@example.com")
    fs = [F("PERSON", 0, 16, text), F("EMAIL", text.index("p.rag"), len(text), text)]
    props = merge.propagate_names(fs, text)
    vals = {text[f.start:f.end] for f in props}
    assert "Duarte" in vals and "Priyanka Raghunathan" in vals


def test_ocr_variant_propagation():
    text = "Karen Caira-Ruiz KC Burney approved. Selected users: KC Burnev x"
    fs = [F("PERSON", 0, 26, text, "presidio")]
    vals = {text[f.start:f.end] for f in merge.propagate_names(fs, text)}
    assert any("Burnev" in v for v in vals)


def test_placeholders_stable_and_typed():
    text = "a@example.com wrote to b@example.com and again a@example.com"
    fs = [F("EMAIL", 0, 13, text), F("EMAIL", 23, 36, text), F("EMAIL", 47, 60, text)]
    red, mapping = redact(text, fs)
    assert red == "[EMAIL_1] wrote to [EMAIL_2] and again [EMAIL_1]"
    assert fs[2].placeholder == "[EMAIL_1]" and red[fs[1].red_start:fs[1].red_end] == "[EMAIL_2]"


def test_phone_placeholder_normalises_formatting():
    text = "+1 (212) 555-0147 or +1 212 555-0147"
    fs = [F("PHONE", 0, 17, text), F("PHONE", 21, 36, text)]
    red, _ = redact(text, fs)
    assert red == "[PHONE_1] or [PHONE_1]"


def test_audit_context_cannot_copy_missed_neighboring_pii():
    text = "Owner Ada Lovelace, phone +91 B80 4555 0182"
    f = F("PERSON", 6, 18, text)
    red, _ = redact(text, [f])
    context = masked_context(red, f)
    assert "[PERSON_1]" in context
    assert "B80" not in context and "4555" not in context and "Owner" not in context
