"""Hosted demo API layer for Sim2Policy.

This package wraps the existing training pipeline with a thin HTTP service and
orchestration backends. Importing this package must not pull in FastAPI; the web
app lives in ``sim2policy.api.app`` and is imported only when serving.
"""
