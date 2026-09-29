# QROS Commercial Readiness Boundary V1

Status: **repository preparation complete; external commercial validation not
performed**.

## Implemented repository controls

- Server-side plan model: `FREE`, `PRO`, `TEAM`, `ENTERPRISE`.
- Server-side usage policy for monthly research runs, dataset bytes, and
  concurrent runs.
- Subscription state resolution from server-side workspace membership and
  subscription state.
- Billing webhook HMAC verification.
- Provider-neutral billing event contract.
- Event payload SHA-256 binding.
- Duplicate event replay detection.
- Same-event/different-payload conflict detection.
- Server-side subscription entitlement update boundary.
- Billing authorization role vocabulary including `billing_admin`.
- Audit-event persistence contract.
- API error contract for entitlement exhaustion (`402`) and rate limiting
  (`429`).

## External configuration still required

A production commercial deployment still requires:
- real payment provider account;
- provider customer/subscription identifiers;
- real webhook endpoint;
- provider webhook signing secret;
- provider test-mode or production event delivery;
- customer-facing checkout/customer-portal decision;
- pricing and entitlement policy approval;
- deployment domain/TLS/WAF;
- external customer/pilot.

No repository test can prove payment-provider delivery or customer willingness
to pay.

## Required provider verification sequence

1. Create a provider test subscription for a controlled workspace.
2. Deliver a valid signed lifecycle event.
3. Verify exactly one persisted billing event.
4. Verify server-side subscription/plan state.
5. Replay the same event and verify no duplicate business effect.
6. Deliver the same event ID with different payload bytes and verify rejection.
7. Deliver an invalid signature and verify rejection.
8. Exercise payment failure/cancellation and verify entitlement transition.
9. Verify the customer-facing API/UI reflects server state only.

## Commercial evidence classes

| State | Meaning |
|---|---|
| IMPLEMENTED | Repository behavior is covered by code/tests. |
| READY_FOR_EXTERNAL_CONFIGURATION | Repository boundary exists; provider/deployment setup is still required. |
| REQUIRES_REAL_PROVIDER | Cannot be closed without provider event delivery. |
| REQUIRES_REAL_CUSTOMER | Cannot be closed without external user/pilot/payment evidence. |

The commercial gate remains separate from software correctness and scientific
evidence.
