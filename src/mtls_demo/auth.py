from __future__ import annotations

import hmac
import os
import time
from hashlib import sha256


AUTH_AGENT_HEADER = "X-Agent-Id"
AUTH_TIMESTAMP_HEADER = "X-Timestamp"
AUTH_SIGNATURE_HEADER = "X-Signature"
DEFAULT_MAX_SKEW_SECONDS = 300


def resolve_shared_secret(explicit_secret: str | None) -> str:
    secret = explicit_secret or os.getenv("MTLS_DEMO_SHARED_SECRET")
    if not secret:
        raise ValueError("Shared secret is required; pass --shared-secret or set MTLS_DEMO_SHARED_SECRET")
    return secret


def sign_request(secret: str, method: str, path: str, agent_id: str, timestamp: str, body: bytes) -> str:
    payload = b"\n".join(
        [
            method.upper().encode("utf-8"),
            path.encode("utf-8"),
            agent_id.encode("utf-8"),
            timestamp.encode("utf-8"),
            body,
        ]
    )
    return hmac.new(secret.encode("utf-8"), payload, sha256).hexdigest()


def build_auth_headers(secret: str, method: str, path: str, agent_id: str, body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    signature = sign_request(secret, method, path, agent_id, timestamp, body)
    return {
        AUTH_AGENT_HEADER: agent_id,
        AUTH_TIMESTAMP_HEADER: timestamp,
        AUTH_SIGNATURE_HEADER: signature,
    }


def verify_signature(
    secret: str,
    method: str,
    path: str,
    agent_id: str,
    timestamp: str,
    signature: str,
    body: bytes,
    max_skew_seconds: int = DEFAULT_MAX_SKEW_SECONDS,
) -> bool:
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - sent_at) > max_skew_seconds:
        return False
    expected = sign_request(secret, method, path, agent_id, timestamp, body)
    return hmac.compare_digest(expected, signature)
