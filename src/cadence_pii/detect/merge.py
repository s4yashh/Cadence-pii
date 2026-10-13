"""Filtering, deterministic overlap resolution and within-document name propagation."""
from __future__ import annotations

import re
from functools import lru_cache

from ..config import COMMON_WORDS, PERSON_DENYLIST
from ..models import Finding

METHOD_PRIORITY = {"regex": 3, "presidio": 2, "gliner": 1, "propagation": 1, "cross_view": 1}
# When spans of different types overlap, structured identifiers win over generic NER types.
TYPE_PRIORITY = {"EMAIL": 9, "US_SSN": 8, "PASSPORT": 8, "TAX_ID": 8, "FINANCIAL_ACCOUNT": 7, "EMPLOYEE_ID": 7,
                 "PHONE": 6, "DATE_OF_BIRTH": 6, "ADDRESS": 5, "PERSON": 4}


_EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def lowercase_vocab(text: str) -> set:
    """Words that occur in lowercase somewhere in the document prose (e-mail addresses excluded)."""
    return set(re.findall(r"\b[a-z][a-z'’-]+\b", _EMAIL_RX.sub(" ", text)))


def _name_tokens(v: str) -> list:
    return [t for t in re.findall(r"[A-Za-z][A-Za-z'’-]*", v) if len(t) > 1]


def _is_common(tok: str, vocab: set) -> bool:
    lt = tok.lower().strip("'’")
    return lt in COMMON_WORDS or lt in vocab


def _looks_like_common_phrase(v: str, vocab: set) -> bool:
    """True if the span is made of ordinary words ("Vendor Tier", "T. Please"), not a name."""
    toks = _name_tokens(v)
    if not toks:
        return True
    common = sum(_is_common(t, vocab) for t in toks)
    if common == len(toks):
        return True
    # every token is a common word or an OCR near-miss of one ("Sotup Rigk" = "Setup Risk")
    if len(toks) >= 2 and all(_is_common(t, vocab) or _near_common(t, vocab, 4) for t in toks):
        return True
    return len(toks) >= 3 and common * 2 > len(toks)


def _near_common(tok: str, vocab: set, min_len: int = 5) -> bool:
    """OCR-damaged common words: 'Acommon' (A + common), 'Chiet' (chief), 'Isyour' (is + your)."""
    lt = tok.lower()
    stops = _stop_words()
    if any(lt[:i] in stops and lt[i:] in stops for i in range(2, len(lt) - 1)):
        return True  # two function words run together by OCR ("Isyour")
    if lt[:1] in ("a", "i") and (lt[1:] in vocab or lt[1:] in COMMON_WORDS) and len(lt) > 4:
        return True
    if len(lt) < min_len:
        return False
    for w in vocab | COMMON_WORDS:
        if abs(len(w) - len(lt)) <= 1 and (w[:2] == lt[:2] or w[-2:] == lt[-2:]) and _edit1(lt, w):
            return True
    return any(w.startswith(lt[:-1]) and len(w) >= len(lt) + 2 for w in vocab if w[:3] == lt[:3])


def _bad_person(v: str, vocab: set = frozenset()) -> bool:
    t = v.strip(" .,;:|()[]#*-")
    if not t or t.lower() in PERSON_DENYLIST:
        return True
    if re.search(r"[_\\/=<>{}]", t):          # markup / identifiers, not names
        return True
    if any(re.search(r"[a-z][A-Z]", w) and not w.startswith(("Mc", "Mac")) for w in t.split()):
        return True                            # CamelCase product names (OneTrust, ServPro)
    if _looks_like_common_phrase(t, vocab):
        return True
    if any(c.isdigit() for c in t) or "@" in t or "|" in t or "\n\n" in v:
        return True
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 3:
        return True
    if t.isupper() and len(t) <= 5:      # acronyms (TPRM, KRI...)
        return True
    if not t[0].isupper():
        return True
    return False


ROLE_TAIL = re.compile(r"(?:[\s,]+(?:Dir|Dir\.|Director|VP|SVP|EVP|CEO|CFO|COO|CIO|CRO|CPO|DPO|CISO|Chief|Head|"
                       r"Officer|Counsel|General|Group|Manager|Lead|Secretary|Chair|NED))+\.?$")


def clean(findings: list, text: str, non_pii: list) -> list:
    """Drop invalid/denylisted spans and anything inside a known non-PII business reference."""
    vocab = lowercase_vocab(text)
    trusted = {t for f in findings if f.entity_type == "PERSON" and len(_name_tokens(f.value)) >= 2
               for t in _name_tokens(f.value)}
    out = []
    for f in findings:
        if f.end <= f.start:
            continue
        if any(s <= f.start and f.end <= e for s, e in non_pii):
            continue
        if f.entity_type == "PERSON" and _bad_person(f.value, vocab):
            continue
        if f.entity_type == "PERSON":
            # spaCy sometimes runs a name into the next table cell / line: cut at the break
            cut = re.search(r"\s*(?:\n|\|)", f.value)
            if cut:
                f = Finding(**{**f.__dict__, "end": f.start + cut.start(), "value": f.value[:cut.start()]})
            tail = ROLE_TAIL.search(f.value)  # "S. Aarnio Dir" -> "S. Aarnio"
            if tail and tail.start() > 0:
                f = Finding(**{**f.__dict__, "end": f.start + tail.start(), "value": f.value[:tail.start()]})
            if _bad_person(f.value, vocab):
                continue
            toks = _name_tokens(f.value)
            if len(toks) == 1 and toks[0] not in trusted and (len(toks[0]) <= 3 or _near_common(toks[0], vocab)):
                continue
        out.append(f)
    return out


def resolve(findings: list) -> list:
    """Cluster overlapping spans; keep the union span (never leak a partial value) and the best type."""
    fs = sorted(findings, key=lambda f: (f.start, -f.end))
    clusters, cur, cur_end = [], [], -1
    for f in fs:
        if cur and f.start < cur_end:
            cur.append(f)
            cur_end = max(cur_end, f.end)
        else:
            if cur:
                clusters.append(cur)
            cur, cur_end = [f], f.end
    if cur:
        clusters.append(cur)
    out = []
    for c in clusters:
        best = max(c, key=lambda f: (TYPE_PRIORITY.get(f.entity_type, 0), METHOD_PRIORITY.get(f.method, 0),
                                     f.end - f.start, f.score))
        s, e = min(f.start for f in c), max(f.end for f in c)
        methods = sorted({f.method for f in c})
        recs = sorted({f.recognizer for f in c})
        out.append(Finding(best.entity_type, s, e, "", max(f.score for f in c), "+".join(methods), ",".join(recs)))
    return out


_TOKEN = re.compile(r"[A-Z][a-zA-Z'’-]{3,}")
_FIRST = r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?"
_NOT_FIRST = {"The", "Led", "By", "Dear", "From", "To", "And", "Or", "Of", "For", "With", "Chair", "Owner",
              "Author", "Contact", "Mobile", "Email", "Name", "Role", "Attested", "Challenged", "Approved"}


def _plausible_first(w: str, pos: int, text: str, known: set, vocab: set) -> bool:
    """Should the capitalised word before a known surname be redacted as a first name?"""
    if w in known:
        return True
    if w in _NOT_FIRST or _is_common(w, vocab) or w.lower() in _stop_words():
        return False
    before = text[:pos].rstrip(" \t")
    return not before.endswith((".", "!", "?"))  # sentence-initial capital is weak evidence


@lru_cache(maxsize=1)
def _stop_words() -> frozenset:
    try:
        from spacy.lang.en.stop_words import STOP_WORDS
        return frozenset(STOP_WORDS) | {"later", "earlier", "then", "today", "yesterday", "meanwhile"}
    except Exception:
        return frozenset({"later", "then", "the", "and"})


def _email_tokens(findings: list, text: str) -> set:
    """Name parts from e-mail local parts: 'p.raghunathan@' -> {'Raghunathan'}."""
    out = set()
    for f in findings:
        if f.entity_type != "EMAIL":
            continue
        local = text[f.start:f.end].split("@")[0]
        for part in re.split(r"[._-]+", local):
            if part.isalpha() and len(part) >= 4:
                out.add(part[0].upper() + part[1:].lower())
    return out


def propagate_names(findings: list, text: str) -> list:
    """Find further mentions of people already evidenced in the document.

    Seeds: tokens of detected PERSON spans ("Rafael E. Duarte" -> "Rafael", "Duarte") and name parts of
    detected e-mail addresses. A seed is used only if it is capitalised every time it occurs in prose
    (proper-noun signal), so common words are not swept up. A matched surname is extended to an
    immediately preceding capitalised first name ("Priyanka Raghunathan").
    """
    # seed only from multi-token names: a lone NER token ("Incontrollec") is too weak to spread
    names = {text[f.start:f.end] for f in findings
             if f.entity_type == "PERSON" and len(_name_tokens(text[f.start:f.end])) >= 2}
    # lowercase mentions inside e-mail addresses ("h.park@...") are not evidence of a common word
    prose = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", " ", text)
    seeds = {t for n in names for t in _TOKEN.findall(n)} | _email_tokens(findings, text)
    tokens = set()
    for t in seeds:
        if t.endswith(("'s", "’s")):
            t = t[:-2]
        if t.lower() in PERSON_DENYLIST or len(t) < 4 or t.isupper() or _is_common(t, set()):
            continue
        if re.search(rf"\b{re.escape(t.lower())}\b", prose):
            continue
        if not re.search(rf"\b{re.escape(t)}\b", prose):
            continue
        tokens.add(t)
    covered = [(f.start, f.end) for f in findings]
    out = []
    # OCR variants of known name tokens ("Burnev" for "Burney"): edit distance 1, capitalised, not a common word
    vocab = lowercase_vocab(text)
    variants = set()
    for w in set(re.findall(r"\b[A-Z][a-z]{4,}\b", text)) - tokens:
        if _is_common(w, vocab):
            continue
        if any(len(t) >= 5 and _edit1(w, t) for t in tokens):
            variants.add(w)
    for t in sorted(tokens | variants):
        for m in re.finditer(rf"(?:\b({_FIRST})[ \t]+)?\b{re.escape(t)}\b", text):
            s = m.start()
            first = m.group(1)
            if first and not _plausible_first(first, m.start(), text, tokens, vocab):
                s = m.end() - len(t)
            if any(a < m.end() and s < b for a, b in covered):
                s = m.end() - len(t)  # fall back to the surname token alone
                if any(a < m.end() and s < b for a, b in covered):
                    continue
            out.append(Finding("PERSON", s, m.end(), text[s:m.end()], 0.7 if t in tokens else 0.6, "propagation",
                               "known_name_token" if t in tokens else "ocr_name_variant"))
            covered.append((s, m.end()))
    return out


def _edit1(a: str, b: str) -> bool:
    """True if a and b differ by exactly one substitution, insertion or deletion."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def join_adjacent_persons(findings: list, text: str) -> list:
    """'[PERSON_1] [PERSON_2]' for one name is confusing: merge PERSON spans separated only by spaces/hyphen."""
    fs = sorted(findings, key=lambda f: f.start)
    out = []
    for f in fs:
        if out and out[-1].entity_type == "PERSON" and f.entity_type == "PERSON":
            gap = text[out[-1].end:f.start]
            if len(gap) <= 2 and gap.strip(" -") == "" and "\n" not in gap:
                p = out[-1]
                out[-1] = Finding("PERSON", p.start, f.end, "", max(p.score, f.score),
                                  "+".join(sorted(set(p.method.split("+")) | set(f.method.split("+")))),
                                  ",".join(sorted(set(p.recognizer.split(",")) | set(f.recognizer.split(",")))))
                continue
        out.append(f)
    return out


_INITIALS_BEFORE = re.compile(r"(?:^|(?<=[\s|(/]))([A-Z]{1,3}\.?)[ \t]+$")


def extend_initials(findings: list, text: str) -> list:
    """Include leading initials Presidio leaves out: 'KC Burney', 'DK Koran'."""
    out = []
    for f in findings:
        if f.entity_type == "PERSON":
            m = _INITIALS_BEFORE.search(text, max(0, f.start - 6), f.start)
            if m and m.group(1).rstrip(".").lower() not in PERSON_DENYLIST | {"vp", "svp", "evp", "id", "no"}:
                f = Finding(**{**f.__dict__, "start": m.start(1), "value": text[m.start(1):f.end]})
        out.append(f)
    return out
