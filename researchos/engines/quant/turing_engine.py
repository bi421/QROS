"""Bounded deterministic Turing-machine execution for QRE research workflows.

This module is research infrastructure, not a trading signal generator.
Execution is explicitly bounded so a non-halting machine cannot run forever.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Mapping, TypeAlias

Symbol: TypeAlias = Hashable
State: TypeAlias = Hashable
TransitionKey: TypeAlias = tuple[State, Symbol]


@dataclass(frozen=True)
class Transition:
    """One deterministic transition."""

    next_state: State
    write_symbol: Symbol
    move: int

    def __post_init__(self) -> None:
        if self.move not in (-1, 0, 1):
            raise ValueError("move must be -1, 0, or 1")


@dataclass(frozen=True)
class TuringResult:
    """Immutable execution evidence."""

    status: str
    state: State
    head: int
    tape: tuple[tuple[int, Symbol], ...]
    steps: int

    @property
    def output(self) -> tuple[Symbol, ...]:
        """Return non-blank tape cells in position order."""
        return tuple(symbol for _, symbol in self.tape)


class TuringMachine:
    """Deterministic single-tape Turing machine with a hard step bound."""

    def __init__(
        self,
        transitions: Mapping[TransitionKey, Transition],
        *,
        initial_state: State,
        halt_states: frozenset[State],
        reject_states: frozenset[State] = frozenset(),
        blank: Symbol = "_",
        max_steps: int = 100_000,
    ) -> None:
        if max_steps < 0:
            raise ValueError("max_steps must be non-negative")
        if not halt_states:
            raise ValueError("at least one halt state is required")
        if halt_states & reject_states:
            raise ValueError("halt and reject states must be disjoint")

        self._transitions = dict(transitions)
        self._initial_state = initial_state
        self._halt_states = halt_states
        self._reject_states = reject_states
        self._blank = blank
        self._max_steps = max_steps

    def run(self, input_symbols: tuple[Symbol, ...]) -> TuringResult:
        """Execute deterministically and return bounded execution evidence."""
        tape = {index: symbol for index, symbol in enumerate(input_symbols)}
        state = self._initial_state
        head = 0
        steps = 0

        while True:
            # Terminal states take precedence over the step limit: a machine
            # that halts on its final permitted transition has HALTED status.
            if state in self._halt_states:
                return self._result("HALTED", state, head, tape, steps)
            if state in self._reject_states:
                return self._result("REJECTED", state, head, tape, steps)
            if steps >= self._max_steps:
                return self._result("TIMEOUT", state, head, tape, steps)

            symbol = tape.get(head, self._blank)
            transition = self._transitions.get((state, symbol))
            if transition is None:
                return self._result("STALLED", state, head, tape, steps)

            tape[head] = transition.write_symbol
            head += transition.move
            state = transition.next_state
            steps += 1

    def _result(
        self,
        status: str,
        state: State,
        head: int,
        tape: Mapping[int, Symbol],
        steps: int,
    ) -> TuringResult:
        non_blank = tuple(
            sorted(
                (position, symbol)
                for position, symbol in tape.items()
                if symbol != self._blank
            )
        )
        return TuringResult(status, state, head, non_blank, steps)
