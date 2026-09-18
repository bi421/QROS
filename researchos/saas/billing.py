"""Provider-neutral billing webhook boundary."""
from __future__ import annotations
import hashlib, hmac, json
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class BillingEvent:
    event_id: str
    workspace_id: str
    plan: str
    status: str
    current_period_end: str | None

class BillingSignatureError(ValueError):
    pass

def verify_hmac_signature(payload: bytes, signature: str, secret: str) -> None:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.strip()):
        raise BillingSignatureError("invalid billing webhook signature")

def parse_billing_event(payload: bytes) -> BillingEvent:
    data: dict[str, Any] = json.loads(payload)
    required = ("event_id", "workspace_id", "plan", "status")
    if any(not str(data.get(k, "")).strip() for k in required):
        raise ValueError("billing event missing required fields")
    return BillingEvent(str(data["event_id"]), str(data["workspace_id"]), str(data["plan"]), str(data["status"]), data.get("current_period_end"))
