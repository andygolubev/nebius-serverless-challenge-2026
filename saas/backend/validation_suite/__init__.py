"""Executable My Robots validation matrix and sanitized reporting helpers."""

from .matrix import (
    CONTROL_INVENTORY,
    CapacityCase,
    ObjectParameterCase,
    SetupCase,
    catalog_fingerprint,
    capacity_cases,
    expected_case_ids,
    object_parameter_cases,
    positive_setup_cases,
    select_shard,
)

__all__ = [
    "CONTROL_INVENTORY",
    "CapacityCase",
    "ObjectParameterCase",
    "SetupCase",
    "catalog_fingerprint",
    "capacity_cases",
    "expected_case_ids",
    "object_parameter_cases",
    "positive_setup_cases",
    "select_shard",
]
