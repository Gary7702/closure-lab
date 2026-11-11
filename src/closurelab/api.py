"""Public execution API for the interpreter."""

from __future__ import annotations

from .parser import parse
from .runtime import Environment, Evaluator, Execution, Limits


def execute(
    source: str,
    *,
    environment: Environment | None = None,
    limits: Limits | None = None,
    trace: bool = False,
) -> Execution:
    return Evaluator(limits, trace=trace).run(parse(source), environment)
