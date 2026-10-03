# Bounded CI Repair Proposal v1

This boundary sits after the deterministic CI failure classifier and before any future repair implementation.

## Contract

Input is the classifier machine-readable JSON. Output is a deterministic proposal containing action, category, repairable, allowed, attempt_limit, and rationale.

Only categories explicitly marked repairable by the classifier are eligible.

## Safety boundary

1. Does not edit repository files.
2. Does not generate a patch.
3. Does not execute commands.
4. Does not merge or deploy.
5. Stops on missing or invalid evidence.
6. Stops on non-repairable or unknown categories.
7. Stops when the configured attempt limit is zero.

A proposal-only result does not grant execution authority.

## Pipeline

observed CI log -> classifier -> bounded repair proposal -> human or separately governed repair controller

The classifier remains authoritative for failure classification. The proposal layer must not reinterpret an ambiguous or unsafe result as repairable.
