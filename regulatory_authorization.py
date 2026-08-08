"""Structured regulatory authorization state.

This module intentionally does not infer authorization from prose.  The value
must come from an authoritative connector/source that has already resolved the
jurisdiction/product context.

Semantics:
- authorized: current authorization/Union-list inclusion is confirmed.
- not_authorized: authorization required but not granted for the matched context.
- pending: application/procedure is still unresolved.
- denied: authorization was explicitly refused.
- terminated: authorization procedure ended without granting authorization.
- unknown: no structured authorization conclusion is available.
"""
from __future__ import annotations
from enum import Enum


class AuthorizationStatus(str, Enum):
    AUTHORIZED="authorized"
    NOT_AUTHORIZED="not_authorized"
    PENDING="pending"
    DENIED="denied"
    TERMINATED="terminated"
    UNKNOWN="unknown"


_BLOCKING={
    AuthorizationStatus.NOT_AUTHORIZED,
    AuthorizationStatus.DENIED,
    AuthorizationStatus.TERMINATED,
}


def normalize_authorization_status(value) -> AuthorizationStatus:
    n=" ".join(str(value or "").strip().lower().replace("-"," ").replace("_"," ").split())
    mapping={
        "authorized":AuthorizationStatus.AUTHORIZED,
        "authorised":AuthorizationStatus.AUTHORIZED,
        "approved":AuthorizationStatus.AUTHORIZED,
        "granted":AuthorizationStatus.AUTHORIZED,
        "not authorized":AuthorizationStatus.NOT_AUTHORIZED,
        "not authorised":AuthorizationStatus.NOT_AUTHORIZED,
        "unauthorized":AuthorizationStatus.NOT_AUTHORIZED,
        "unauthorised":AuthorizationStatus.NOT_AUTHORIZED,
        "authorization not granted":AuthorizationStatus.NOT_AUTHORIZED,
        "authorisation not granted":AuthorizationStatus.NOT_AUTHORIZED,
        "pending":AuthorizationStatus.PENDING,
        "under review":AuthorizationStatus.PENDING,
        "denied":AuthorizationStatus.DENIED,
        "refused":AuthorizationStatus.DENIED,
        "rejected":AuthorizationStatus.DENIED,
        "terminated":AuthorizationStatus.TERMINATED,
        "procedure terminated":AuthorizationStatus.TERMINATED,
        "unknown":AuthorizationStatus.UNKNOWN,
    }
    return mapping.get(n,AuthorizationStatus.UNKNOWN)


def is_market_blocking(status: AuthorizationStatus) -> bool:
    return status in _BLOCKING
