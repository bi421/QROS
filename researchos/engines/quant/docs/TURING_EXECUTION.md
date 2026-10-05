# QRE Turing Execution Contract

The QRE Turing formalism is an execution model for research workflows, not a
market-prediction model.

The implementation in `researchos/engines/quant/turing_engine.py` provides:

- deterministic state/symbol transitions;
- explicit HALTED, REJECTED, STALLED, and TIMEOUT outcomes;
- immutable execution evidence;
- a hard step bound so non-halting research programs cannot run forever.

The first executable proof case is binary increment:

`1011 -> 1100`

This proves the execution semantics end-to-end. It does **not** prove a trading
edge. Any future market model must produce independently validated research
evidence before it can be considered for production promotion.
