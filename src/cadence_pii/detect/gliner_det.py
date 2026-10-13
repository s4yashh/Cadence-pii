"""Optional GLiNER layer (zero-shot NER, runs locally once weights are downloaded).

Disabled by default; enabled only if the evaluation shows a recall gain worth the runtime.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import GLINER_MAP
from ..models import Finding


@lru_cache(maxsize=1)
def get_model(name: str):
    from gliner import GLiNER
    return GLiNER.from_pretrained(name)


def detect_gliner(text: str, offset: int, model_name: str, threshold: float = 0.5, window: int = 1200) -> list:
    """GLiNER has a limited context window, so long blocks are scanned in overlapping chunks."""
    if not text.strip():
        return []
    model = get_model(model_name)
    labels = list(GLINER_MAP)
    out, seen = [], set()
    step = window - 200
    for cs in range(0, max(1, len(text)), step):
        chunk = text[cs:cs + window]
        for ent in model.predict_entities(chunk, labels, threshold=threshold):
            s, e = ent["start"] + cs, ent["end"] + cs
            if (s, e) in seen:
                continue
            seen.add((s, e))
            out.append(Finding(GLINER_MAP[ent["label"]], s + offset, e + offset, text[s:e],
                               round(float(ent["score"]), 3), "gliner", "gliner:" + ent["label"]))
        if cs + window >= len(text):
            break
    return out
