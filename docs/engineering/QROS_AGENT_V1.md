# QROS Agent v1

Status: ACTIVE CONTROL-PLANE + GOVERNED EXECUTION BOUNDARY

## Purpose

qros-agent is the deterministic engineering-agent kernel for QROS. It is not yet a model-backed source-repair bot.

Its job is to turn task contract plus observed CI log into a bounded machine-readable decision:

validate -> classify -> propose -> stop/authorize-next-boundary

## Safety boundary

v1:

- requires a valid engineering task contract;
- delegates failure classification to scripts/classify_ci_failure.py;
- delegates repairability to scripts/propose_ci_repair.py;
- enforces an explicit attempt limit;
- fails closed on invalid, empty, ambiguous, or non-repairable evidence;
- never executes a repair command without explicit human approval;
- validates command scope before any approved execution;
- requires the approved command to match the proposal's governed action;
- records the exact approved command and resulting git diff in the execution result;
- never merges;
- never deploys.

A proposal is not execution authority. The governed executor requires an explicit approval flag, a bounded command allowlist, explicit allowed paths, and a positive attempt budget.

## Decision model

Task Contract
     |
     v
Contract validation
     |
     +-- FAIL --> STOP
     |
     v
Observed CI log
     |
     v
Deterministic classifier
     |
     +-- ambiguous / non-repairable --> STOP
     |
     v
Bounded repair proposal
     |
     +-- attempt_limit == 0 --> STOP
     |
     v
PROPOSAL_READY
     |
     v
Human approval
     |
     v
Governed executor
     |
     +-- rejected scope/command --> STOP
     |
     v
Execution + diff receipt

## Output

The CLI emits JSON containing:

- status
- task_contract
- classification
- proposal
- next_boundary

The governed executor additionally returns:

- exact command
- process result
- stdout/stderr
- resulting git diff
- next boundary

No output is evidence that a source repair succeeded. Only actual validation and CI can establish that.

## Current execution boundary

The governed executor is a bounded adapter, not autonomous source repair.

It:

1. receives an accepted proposal;
2. derives executable paths from the task contract;
3. requires an explicit governed action in the accepted proposal;
4. allows only Ruff check or format when the command exactly matches that action;
5. requires explicit human approval;
6. records the exact command and resulting git diff after approved execution;
7. never merges or deploys.

The model, if one is added, remains subordinate to these deterministic controls.
