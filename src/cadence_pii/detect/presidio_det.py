"""Microsoft Presidio layer (spaCy en_core_web_lg NER + Presidio's built-in recognisers).

Runs per block so tables and image text keep local context; offsets are shifted back to the
document coordinate system. Only entity types in config.PRESIDIO_MAP are kept.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import PRESIDIO_MAP
from ..models import Finding


@lru_cache(maxsize=1)
def get_analyzer():
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider

    provider = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
    })
    return AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])


@lru_cache(maxsize=1)
def supported_entities() -> list:
    """Only request entities this Presidio build has recognisers for (avoids silent no-ops/warnings)."""
    have = set(get_analyzer().get_supported_entities(language="en"))
    return [e for e in PRESIDIO_MAP if e in have]


def detect_presidio(text: str, offset: int = 0, threshold: float = 0.5) -> list:
    if not text.strip():
        return []
    res = get_analyzer().analyze(text=text, language="en", entities=supported_entities(),
                                 score_threshold=threshold)
    out = []
    for r in res:
        etype = PRESIDIO_MAP.get(r.entity_type)
        if not etype:
            continue
        rec = (r.recognition_metadata or {}).get("recognizer_name", r.entity_type)
        out.append(Finding(etype, r.start + offset, r.end + offset, text[r.start:r.end], round(r.score, 3),
                           "presidio", rec))
    return out
