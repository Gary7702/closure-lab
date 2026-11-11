from dataclasses import dataclass, fields

from .errors import Span


@dataclass(frozen=True, slots=True, kw_only=True)
class Node:
    span: Span


@dataclass(frozen=True, slots=True, kw_only=True)
class Literal(Node):
    value: int | bool | str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Variable(Node):
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Lambda(Node):
    parameters: tuple[str, ...]
    body: Node


@dataclass(frozen=True, slots=True, kw_only=True)
class Call(Node):
    function: Node
    arguments: tuple[Node, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class If(Node):
    condition: Node
    consequence: Node
    alternative: Node


@dataclass(frozen=True, slots=True, kw_only=True)
class Let(Node):
    name: str
    value: Node
    body: Node
    recursive: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class Begin(Node):
    expressions: tuple[Node, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Logic(Node):
    operator: str
    operands: tuple[Node, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Define(Node):
    name: str
    value: Node


@dataclass(frozen=True, slots=True)
class Program:
    expressions: tuple[Node, ...]


def to_data(node: Node | Program) -> dict[str, object]:
    def convert(value: object) -> object:
        if isinstance(value, Node | Program):
            return to_data(value)
        if isinstance(value, Span):
            return {field.name: getattr(value, field.name) for field in fields(value)}
        if isinstance(value, tuple):
            return [convert(item) for item in value]
        return value

    return {
        "type": type(node).__name__,
        **{field.name: convert(getattr(node, field.name)) for field in fields(node)},
    }
