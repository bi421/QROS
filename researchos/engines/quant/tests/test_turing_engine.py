"""Executable contracts for the bounded QRE Turing-machine formalism."""

from researchos.engines.quant.turing_engine import Transition, TuringMachine


def _binary_incrementer() -> TuringMachine:
    # Input is MSB -> LSB. The machine walks to the right edge, then adds one.
    transitions = {
        ("scan", "0"): Transition("scan", "0", 1),
        ("scan", "1"): Transition("scan", "1", 1),
        ("scan", "_"): Transition("carry", "_", -1),
        ("carry", "1"): Transition("carry", "0", -1),
        ("carry", "0"): Transition("halt", "1", 0),
        ("carry", "_"): Transition("halt", "1", 0),
    }
    return TuringMachine(
        transitions,
        initial_state="scan",
        halt_states=frozenset({"halt"}),
        blank="_",
        max_steps=100,
    )


def test_binary_increment_has_real_deterministic_result() -> None:
    result = _binary_incrementer().run(("1", "0", "1", "1"))

    assert result.status == "HALTED"
    assert result.output == ("1", "1", "0", "0")
    assert result.steps == 8


def test_non_halting_machine_is_bounded() -> None:
    machine = TuringMachine(
        {("loop", "0"): Transition("loop", "0", 1)},
        initial_state="loop",
        halt_states=frozenset({"halt"}),
        blank="_",
        max_steps=3,
    )

    result = machine.run(("0",))

    assert result.status == "TIMEOUT"
    assert result.steps == 3


def test_missing_transition_is_explicitly_stalled() -> None:
    machine = TuringMachine(
        {},
        initial_state="start",
        halt_states=frozenset({"halt"}),
    )

    result = machine.run(("X",))

    assert result.status == "STALLED"
    assert result.steps == 0
