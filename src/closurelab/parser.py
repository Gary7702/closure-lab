from dataclasses import dataclass
from typing import NoReturn

from .ast import Begin, Call, Define, If, Lambda, Let, Literal, Logic, Node, Program, Variable
from .errors import LanguageError, Span
from .lexer import IDENTIFIER, Token, tokenize

MAX_DEPTH = 80
SPECIAL_FORMS = frozenset({"lambda", "if", "let", "letrec", "begin", "and", "or", "not", "define"})
RESERVED_NAMES = SPECIAL_FORMS | {"true", "false", "nil"}


@dataclass(frozen=True, slots=True)
class _List:
    items: tuple["Token | _List", ...]
    span: Span


def _fail(message: str, value: Token | _List) -> NoReturn:
    raise LanguageError("E_PARSE", message, value.span)


def _name(value: Token | _List) -> str:
    if not isinstance(value, Token) or value.kind != "IDENTIFIER":
        _fail("binding name must be an identifier", value)
    if not IDENTIFIER.fullmatch(value.text) or value.text in RESERVED_NAMES:
        _fail("invalid or reserved binding name", value)
    return value.text


def _arity(form: _List, name: str, count: int, *, minimum: bool = False) -> None:
    actual = len(form.items) - 1
    if (minimum and actual < count) or (not minimum and actual != count):
        requirement = f"at least {count}" if minimum else str(count)
        _fail(f"{name} requires {requirement} arguments; got {actual}", form)


def _lower(value: Token | _List, *, top_level: bool = False) -> Node:
    if isinstance(value, Token):
        if value.kind in {"INTEGER", "LITERAL", "STRING"}:
            return Literal(span=value.span, value=value.value)
        return Variable(span=value.span, name=value.text)
    if not value.items:
        _fail("empty list is not an expression", value)
    head, *arguments = value.items
    name = head.text if isinstance(head, Token) and head.kind == "IDENTIFIER" else ""
    if name == "lambda":
        _arity(value, name, 2)
        parameters = arguments[0]
        if not isinstance(parameters, _List):
            _fail("lambda parameters must be a list", parameters)
        names: list[str] = []
        seen: set[str] = set()
        for parameter in parameters.items:
            parameter_name = _name(parameter)
            if parameter_name in seen:
                _fail("duplicate lambda parameter", parameter)
            names.append(parameter_name)
            seen.add(parameter_name)
        return Lambda(span=value.span, parameters=tuple(names), body=_lower(arguments[1]))
    if name == "if":
        _arity(value, name, 3)
        return If(
            span=value.span,
            condition=_lower(arguments[0]),
            consequence=_lower(arguments[1]),
            alternative=_lower(arguments[2]),
        )
    if name in {"let", "letrec"}:
        _arity(value, name, 2)
        binding = arguments[0]
        if not isinstance(binding, _List) or len(binding.items) != 2:
            _fail(f"{name} binding must be (name value)", binding)
        return Let(
            span=value.span,
            name=_name(binding.items[0]),
            value=_lower(binding.items[1]),
            body=_lower(arguments[1]),
            recursive=name == "letrec",
        )
    if name == "begin":
        _arity(value, name, 1, minimum=True)
        return Begin(span=value.span, expressions=tuple(_lower(item) for item in arguments))
    if name in {"and", "or", "not"}:
        _arity(value, name, 1 if name == "not" else 2, minimum=name != "not")
        return Logic(span=value.span, operator=name, operands=tuple(_lower(item) for item in arguments))
    if name == "define":
        if not top_level:
            _fail("define is only allowed at the top level", value)
        _arity(value, name, 2)
        return Define(span=value.span, name=_name(arguments[0]), value=_lower(arguments[1]))
    return Call(span=value.span, function=_lower(head), arguments=tuple(_lower(item) for item in arguments))


def parse(source: str, *, max_depth: int = MAX_DEPTH) -> Program:
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise ValueError(f"max_depth must be an integer between 1 and {MAX_DEPTH}")
    tokens = tokenize(source)
    index = 0

    def expression(depth: int) -> Token | _List:
        nonlocal index
        token = tokens[index]
        if token.kind == "RPAREN":
            _fail("unexpected closing parenthesis", token)
        if token.kind == "EOF":
            _fail("expected an expression", token)
        index += 1
        if token.kind != "LPAREN":
            return token
        if depth >= max_depth:
            raise LanguageError("E_LIMIT", "parenthesis nesting limit exceeded", token.span)
        items: list[Token | _List] = []
        while tokens[index].kind != "RPAREN":
            if tokens[index].kind == "EOF":
                _fail("unclosed opening parenthesis", token)
            items.append(expression(depth + 1))
        closing = tokens[index]
        index += 1
        return _List(
            tuple(items), Span(token.span.start, closing.span.end, token.span.line, token.span.column)
        )

    expressions: list[Node] = []
    while tokens[index].kind != "EOF":
        expressions.append(_lower(expression(0), top_level=True))
    return Program(tuple(expressions))
