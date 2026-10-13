"""Cadence PII detection pipeline (Optiv Case Study 2).

Flow: ingest -> extract (+OCR) -> detect -> merge -> redact -> verify -> gate -> report.
Everything runs inside the local Python runtime; no document content is sent to external services.
"""
__version__ = "0.1.0"
