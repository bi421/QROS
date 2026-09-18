import hashlib, hmac, json
import pytest
from researchos.saas.billing import BillingSignatureError, parse_billing_event, verify_hmac_signature

def test_billing_signature_is_verified() -> None:
    body=b'{"event_id":"evt_1","workspace_id":"w","plan":"pro","status":"active"}'
    sig=hmac.new(b"secret",body,hashlib.sha256).hexdigest()
    verify_hmac_signature(body,sig,"secret")

def test_billing_signature_rejects_tampering() -> None:
    with pytest.raises(BillingSignatureError):
        verify_hmac_signature(b"bad","00","secret")

def test_billing_event_requires_identity_and_entitlement() -> None:
    with pytest.raises(ValueError):
        parse_billing_event(json.dumps({"event_id":"x"}).encode())
