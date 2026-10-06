# QROS Agent v1

Status: ACTIVE CONTROL-PLANE BOUNDARY

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
- never edits files;
- never executes repair commands;
- never merges;
- never deploys.

A proposal is not execution authority.

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

## Output

The CLI emits JSON containing:

- status
- task_contract
- classification
- proposal
- next_boundary

No output is evidence that a source repair succeeded. Only actual validation and CI can establish that.

## Future boundary

A later version may add a governed executor adapter. That adapter must:

1. receive only an accepted proposal;
2. operate only on files explicitly allowed by the task contract;
3. record the exact command/patch and resulting diff;
4. run canonical gates;
5. stop at the configured attempt limit;
6. require human approval for protected operations.

The model, if one is added, remains subordinate to these deterministic controls.
