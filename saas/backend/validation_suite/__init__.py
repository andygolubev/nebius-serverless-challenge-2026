"""Executable My Robots validation matrix and sanitized reporting helpers.

Keep package import side-effect free. In particular, ``python -m
validation_suite.local_server`` must establish its temporary database and mock
environment before any module imports the FastAPI application.
"""
