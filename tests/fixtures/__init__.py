"""Synthetic test fixtures and fake Odoo client for unit/integration tests."""
from __future__ import annotations

from tests.fixtures.synthetic_data import (
    PROD_BLOCKED_HOST,
    SYNTHETIC_CUSTOMER_ALPHA,
    SYNTHETIC_CUSTOMER_BETA,
    SYNTHETIC_VENDOR_GAMMA,
    SyntheticOdooClient,
    assert_not_prod_url,
    build_base_synthetic_records,
)

__all__ = [
    "PROD_BLOCKED_HOST",
    "SYNTHETIC_CUSTOMER_ALPHA",
    "SYNTHETIC_CUSTOMER_BETA",
    "SYNTHETIC_VENDOR_GAMMA",
    "SyntheticOdooClient",
    "assert_not_prod_url",
    "build_base_synthetic_records",
]
