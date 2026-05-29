"""V3.6 — webhook authenticity + replay protection.

Two layers, applied in order to inbound `/webhook/pipeline-complete`:

  1. HMAC-SHA256 of the raw body using a per-project secret. The CI signs
     the body with the same secret it received from the dashboard's
     `POST /projects/{id}/webhook/rotate` rotation. Signature lands in
     `X-Hub-Signature-256: sha256=<hex>` (GitHub-standard naming so
     reverse proxies that already handle this header just work).

  2. Replay dedup via `X-GitHub-Delivery: <uuid>` looked up against the
     `webhook_deliveries` table. Same delivery_id arriving twice (network
     retry, malicious replay) returns 200 with `outcome=duplicate` and
     skips the work.

Back-compat: callers that don't sign (legacy V3.5 CI using bearer-token
mode) are still accepted when the project hasn't enabled signing yet.
This lets the rollout happen one project at a time without bricking
existing pipelines. Once every project's CI is upgraded, flip
`settings.WEBHOOK_REQUIRE_HMAC=true` to enforce.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.entities import Project, WebhookDelivery

log = logging.getLogger(__name__)

SignatureOutcome = Literal["valid", "invalid", "missing", "no_secret"]


@dataclass(frozen=True)
class SignatureCheckResult:
    outcome: SignatureOutcome
    matched_project_id: int | None = None
    detail: str | None = None


def compute_signature(body: bytes, secret: str) -> str:
    """Return `sha256=<hex>` digest of body under secret — same format as
    GitHub's X-Hub-Signature-256 so a CI runner can just call OpenSSL:
        echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET"
    """
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def verify_against_secret(body: bytes, header_value: str, secret: str) -> bool:
    """Constant-time compare; header_value comes straight from request
    headers (`sha256=<hex>` or — defensively — just the hex part)."""
    if not header_value or not secret:
        return False
    expected = compute_signature(body, secret)
    # Normalize: some callers strip the prefix; compare both forms.
    candidates = (expected, expected.split("=", 1)[1])
    incoming = header_value.strip()
    incoming_alts = (incoming, incoming.split("=", 1)[1]) if "=" in incoming else (incoming,)
    for inc in incoming_alts:
        for exp in candidates:
            if hmac.compare_digest(inc, exp):
                return True
    return False


async def verify_signature_against_any_project(
    session: AsyncSession, body: bytes, signature_header: str,
) -> SignatureCheckResult:
    """Walk active projects with a webhook_token set, try each as the HMAC
    secret. O(n) on number of projects — fine at thesis scale (<100). When
    projects exceed ~1000 add a `webhook_token_hash` index column and
    require the caller to send X-Project-Id so we skip the scan.

    Returns: matched project_id when signature checks; None + outcome
    indicating the failure mode otherwise.
    """
    from ..repositories.project_repo import _decrypt_project
    from sqlalchemy import select

    if not signature_header:
        return SignatureCheckResult(outcome="missing")

    result = await session.execute(select(Project))
    any_token_configured = False
    for proj in result.scalars().all():
        # Decrypt the per-project secret (Fernet) before HMAC compare.
        _decrypt_project(proj)
        secret = proj.webhook_token or ""
        if not secret:
            continue
        any_token_configured = True
        if verify_against_secret(body, signature_header, secret):
            return SignatureCheckResult(outcome="valid", matched_project_id=proj.id)

    if not any_token_configured:
        return SignatureCheckResult(
            outcome="no_secret",
            detail="No project has a rotated webhook_token — sign-in mode unavailable",
        )
    return SignatureCheckResult(outcome="invalid")


async def record_delivery(
    session: AsyncSession,
    *,
    delivery_id: str,
    project_id: int | None,
    github_run_id: int | None,
    body: bytes,
    outcome: str,
    detail: str | None = None,
) -> bool:
    """Insert a `webhook_deliveries` row. Returns False if the delivery_id
    already exists (duplicate). Caller checks the boolean to decide
    whether to process the payload.

    body_sha256 lets a follow-up audit detect tampering: same delivery_id
    + different body = someone replaying with modified payload.
    """
    body_hash = hashlib.sha256(body).hexdigest() if body else None
    existing = await session.get(WebhookDelivery, delivery_id)
    if existing is not None:
        # Existing row wins; just log if hash differs (tampering signal).
        if body_hash and existing.body_sha256 and existing.body_sha256 != body_hash:
            log.warning(
                "Webhook delivery %s replayed with different body hash "
                "(stored=%s, incoming=%s) — possible tampering",
                delivery_id, existing.body_sha256, body_hash,
            )
        return False
    session.add(WebhookDelivery(
        delivery_id=delivery_id,
        project_id=project_id,
        github_run_id=github_run_id,
        body_sha256=body_hash,
        outcome=outcome,
        detail=detail,
    ))
    return True
