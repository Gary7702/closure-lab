"""Lexically scoped, stack-safe tree-walk evaluation without Python eval/exec."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeAlias

from .ast import Begin, Call, Define, If, Lambda, Let, Literal, Logic, Node, Program, Variable
from .errors import LanguageError, Span


@dataclass(frozen=True, slots=True)
class Limits:
    max_steps: int = 100_000
    max_integer_bits: int = 4096
    max_string_chars: int = 100_000
    max_output_chars: int = 100_000
    max_trace_events: int = 200

    def __post_init__(self) -> None:
        bounds = {
            "max_steps": 10_000_000,
            "max_integer_bits": 4096,
            "max_string_chars": 1_000_000,
            "max_output_chars": 1_000_000,
            "max_trace_events": 10_000,
        }
        for name, upper in bounds.items():
            value = getattr(self, name)
            minimum = 0 if name == "max_trace_events" else 1
            if type(value) is not int or not minimum <= value <= upper:
                raise ValueError(f"{name} must be an integer in [{minimum}, {upper}]")


@dataclass(slots=True)
class _Cell:
    """Internal one-time recursive binding; never a public language value."""

    value: Value | None = None
    initialized: bool = False


@dataclass(frozen=True, slots=True)
class Environment:
    bindings: Mapping[str, Value | _Cell] = field(default_factory=dict)
    parent: Environment | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", MappingProxyType(dict(self.bindings)))

    def extend(self, bindings: Mapping[str, Value | _Cell]) -> Environment:
        return Environment(bindings, self)

    def lookup(self, name: str, span: Span | None = None) -> Value:
        env: Environment | None = self
        while env is not None:
            if name in env.bindings:
                value = env.bindings[name]
                if isinstance(value, _Cell):
                    if not value.initialized:
                        raise LanguageError("E_NAME", f"Recursive binding '{name}' is not initialized", span)
                    return value.value
                return value
            env = env.parent
        raise LanguageError("E_NAME", f"Undefined variable '{name}'", span)


@dataclass(frozen=True, slots=True)
class Closure:
    function: Lambda
    environment: Environment = field(repr=False)


@dataclass(frozen=True, slots=True)
class Builtin:
    name: str
    arity: int | None


Value: TypeAlias = int | bool | str | None | Closure | Builtin


def format_value(value: Value) -> str:
    if value is None:
        return "nil"
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, Closure):
        return f"<closure ({' '.join(value.function.parameters)})>"
    if isinstance(value, Builtin):
        return f"<builtin {value.name}>"
    return str(value)


def value_data(value: Value) -> object:
    if isinstance(value, Closure):
        return {"type": "closure", "parameters": list(value.function.parameters)}
    if isinstance(value, Builtin):
        return {"type": "builtin", "name": value.name}
    return value


def standard_environment() -> Environment:
    operators = ("+", "-", "*", "//", "%", "==", "!=", "<", "<=", ">", ">=")
    values: dict[str, Value | _Cell] = {name: Builtin(name, 2) for name in operators}
    values.update({"len": Builtin("len", 1), "print": Builtin("print", None)})
    return Environment(values)


@dataclass(frozen=True, slots=True)
class TraceEvent:
    step: int
    node: str
    line: int
    column: int

    def to_data(self) -> dict[str, object]:
        return {"step": self.step, "node": self.node, "line": self.line, "column": self.column}


@dataclass(frozen=True, slots=True)
class Execution:
    value: Value
    environment: Environment = field(repr=False)
    steps: int
    output: tuple[str, ...]
    trace: tuple[TraceEvent, ...]
    trace_truncated: bool

    def to_data(self) -> dict[str, object]:
        return {
            "value": value_data(self.value),
            "steps": self.steps,
            "output": list(self.output),
            "trace": [event.to_data() for event in self.trace],
            "trace_truncated": self.trace_truncated,
        }


@dataclass(slots=True)
class _IfFrame:
    node: If
    env: Environment


@dataclass(slots=True)
class _LetFrame:
    node: Let
    env: Environment


@dataclass(slots=True)
class _SequenceFrame:
    nodes: tuple[Node, ...]
    index: int
    env: Environment


@dataclass(slots=True)
class _FunctionFrame:
    node: Call
    env: Environment


@dataclass(slots=True)
class _ArgumentsFrame:
    node: Call
    env: Environment
    function: Value
    values: list[Value]
    index: int


@dataclass(slots=True)
class _LogicFrame:
    node: Logic
    env: Environment
    index: int


Frame: TypeAlias = _IfFrame | _LetFrame | _SequenceFrame | _FunctionFrame | _ArgumentsFrame | _LogicFrame


class Evaluator:
    def __init__(
        self,
        limits: Limits | None = None,
        *,
        trace: bool = False,
        output: Callable[[str], None] | None = None,
    ) -> None:
        self.limits = limits or Limits()
        self.trace_enabled = trace
        self.output_callback = output
        self.steps = 0
        self.output_lines: list[str] = []
        self.output_chars = 0
        self.trace_events: list[TraceEvent] = []
        self.trace_truncated = False

    def run(self, program: Program, environment: Environment | None = None) -> Execution:
        self.steps = 0
        self.output_lines = []
        self.output_chars = 0
        self.trace_events = []
        self.trace_truncated = False
        env = environment if environment is not None else standard_environment()
        value: Value = None
        for expression in program.expressions:
            if isinstance(expression, Define):
                self._tick(expression)
                value = self._evaluate(expression.value, env)
                env = env.extend({expression.name: value})
            else:
                value = self._evaluate(expression, env)
        return Execution(
            value, env, self.steps, tuple(self.output_lines), tuple(self.trace_events), self.trace_truncated
        )

    def _tick(self, node: Node | None = None) -> None:
        self.steps += 1
        if self.steps > self.limits.max_steps:
            raise LanguageError("E_LIMIT", "Evaluation step budget exceeded", node.span if node else None)
        if node is not None and self.trace_enabled:
            if len(self.trace_events) < self.limits.max_trace_events:
                self.trace_events.append(
                    TraceEvent(self.steps, type(node).__name__, node.span.line, node.span.column)
                )
            else:
                self.trace_truncated = True

    def _check(self, value: Value, span: Span) -> Value:
        if type(value) is int and value.bit_length() > self.limits.max_integer_bits:
            raise LanguageError("E_LIMIT", "Integer size budget exceeded", span)
        if isinstance(value, str) and len(value) > self.limits.max_string_chars:
            raise LanguageError("E_LIMIT", "String size budget exceeded", span)
        return value

    @staticmethod
    def _boolean(value: Value, span: Span) -> bool:
        if type(value) is not bool:
            raise LanguageError("E_TYPE", "Condition must be a boolean (no implicit truthiness)", span)
        return value

    def _evaluate(self, initial: Node, initial_env: Environment) -> Value:
        control = initial
        env = initial_env
        stack: list[Frame] = []
        value: Value = None
        evaluating = True
        while True:
            self._tick(control if evaluating else None)
            if evaluating:
                if isinstance(control, Literal):
                    value = self._check(control.value, control.span)
                    evaluating = False
                elif isinstance(control, Variable):
                    value = self._check(env.lookup(control.name, control.span), control.span)
                    evaluating = False
                elif isinstance(control, Lambda):
                    value = Closure(control, env)
                    evaluating = False
                elif isinstance(control, If):
                    stack.append(_IfFrame(control, env))
                    control = control.condition
                elif isinstance(control, Let):
                    if control.recursive:
                        if not isinstance(control.value, Lambda):
                            raise LanguageError(
                                "E_TYPE", "letrec requires a lambda value", control.value.span
                            )
                        cell = _Cell()
                        env = env.extend({control.name: cell})
                        cell.value = Closure(control.value, env)
                        cell.initialized = True
                        control = control.body
                    else:
                        stack.append(_LetFrame(control, env))
                        control = control.value
                elif isinstance(control, Begin):
                    if len(control.expressions) > 1:
                        stack.append(_SequenceFrame(control.expressions, 1, env))
                    control = control.expressions[0]
                elif isinstance(control, Logic):
                    stack.append(_LogicFrame(control, env, 0))
                    control = control.operands[0]
                elif isinstance(control, Call):
                    stack.append(_FunctionFrame(control, env))
                    control = control.function
                else:
                    raise LanguageError("E_RUNTIME", "Unsupported AST node in expression", control.span)
                continue
            if not stack:
                return value
            frame = stack.pop()
            if isinstance(frame, _IfFrame):
                branch = self._boolean(value, frame.node.condition.span)
                control = frame.node.consequence if branch else frame.node.alternative
                env = frame.env
                evaluating = True
            elif isinstance(frame, _LetFrame):
                env = frame.env.extend({frame.node.name: value})
                control = frame.node.body
                evaluating = True
            elif isinstance(frame, _SequenceFrame):
                control = frame.nodes[frame.index]
                frame.index += 1
                if frame.index < len(frame.nodes):
                    stack.append(frame)
                env = frame.env
                evaluating = True
            elif isinstance(frame, _LogicFrame):
                truth = self._boolean(value, frame.node.operands[frame.index].span)
                operator = frame.node.operator
                if operator == "not":
                    value = not truth
                elif (operator == "and" and not truth) or (operator == "or" and truth):
                    value = truth
                elif frame.index + 1 < len(frame.node.operands):
                    frame.index += 1
                    control = frame.node.operands[frame.index]
                    env = frame.env
                    stack.append(frame)
                    evaluating = True
                else:
                    value = truth
            elif isinstance(frame, _FunctionFrame):
                if frame.node.arguments:
                    stack.append(_ArgumentsFrame(frame.node, frame.env, value, [], 0))
                    control = frame.node.arguments[0]
                    env = frame.env
                    evaluating = True
                else:
                    value, next_body, next_env = self._apply(value, [], frame.node.span)
                    if next_body is not None and next_env is not None:
                        control, env, evaluating = next_body, next_env, True
            elif isinstance(frame, _ArgumentsFrame):
                frame.values.append(value)
                frame.index += 1
                if frame.index < len(frame.node.arguments):
                    stack.append(frame)
                    control = frame.node.arguments[frame.index]
                    env = frame.env
                    evaluating = True
                else:
                    value, next_body, next_env = self._apply(frame.function, frame.values, frame.node.span)
                    if next_body is not None and next_env is not None:
                        control, env, evaluating = next_body, next_env, True

    def _apply(
        self, function: Value, args: list[Value], span: Span
    ) -> tuple[Value, Node | None, Environment | None]:
        if isinstance(function, Closure):
            params = function.function.parameters
            if len(params) != len(args):
                raise LanguageError("E_ARITY", f"Expected {len(params)} arguments, got {len(args)}", span)
            return (
                None,
                function.function.body,
                function.environment.extend(dict(zip(params, args, strict=True))),
            )
        if isinstance(function, Builtin):
            if function.arity is not None and len(args) != function.arity:
                raise LanguageError(
                    "E_ARITY", f"'{function.name}' expects {function.arity} arguments, got {len(args)}", span
                )
            return self._builtin(function.name, args, span), None, None
        raise LanguageError("E_TYPE", "Cannot call a non-function value", span)

    def _builtin(self, name: str, args: list[Value], span: Span) -> Value:
        if name == "print":
            parts = [format_value(arg) for arg in args]
            length = sum(map(len, parts)) + max(0, len(parts) - 1) + 1
            if self.output_chars + length > self.limits.max_output_chars:
                raise LanguageError("E_LIMIT", "Output size budget exceeded", span)
            line = " ".join(parts)
            self.output_chars += length
            self.output_lines.append(line)
            if self.output_callback is not None:
                self.output_callback(line)
            return None
        if name == "len":
            if not isinstance(args[0], str):
                raise LanguageError("E_TYPE", "'len' expects a string", span)
            return self._check(len(args[0]), span)
        left, right = args
        if name in ("==", "!="):
            if isinstance(left, Closure | Builtin) or isinstance(right, Closure | Builtin):
                raise LanguageError("E_TYPE", "Functions cannot be compared for equality", span)
            equal = type(left) is type(right) and left == right
            return equal if name == "==" else not equal
        if name == "+" and isinstance(left, str) and isinstance(right, str):
            if len(left) + len(right) > self.limits.max_string_chars:
                raise LanguageError("E_LIMIT", "String size budget exceeded", span)
            return left + right
        if name in ("<", "<=", ">", ">=") and isinstance(left, str) and isinstance(right, str):
            return self._compare(name, left, right)
        if type(left) is not int or type(right) is not int:
            raise LanguageError(
                "E_TYPE", f"'{name}' expects two integers (or same-type strings where supported)", span
            )
        if name == "+":
            result = left + right
        elif name == "-":
            result = left - right
        elif name == "*":
            result = left * right
        elif name in ("//", "%"):
            if right == 0:
                raise LanguageError("E_ZERO", "Division by zero", span)
            result = left // right if name == "//" else left % right
        else:
            return self._compare(name, left, right)
        return self._check(result, span)

    @staticmethod
    def _compare(name: str, left: int | str, right: int | str) -> bool:
        if name == "<":
            return left < right  # type: ignore[operator]
        if name == "<=":
            return left <= right  # type: ignore[operator]
        if name == ">":
            return left > right  # type: ignore[operator]
        return left >= right  # type: ignore[operator]
