import json
import re
from dataclasses import dataclass

from .errors import LanguageError, Span

MAX_SOURCE_CHARS = 1_000_000
MAX_TOKENS = 100_000
MAX_INTEGER_DIGITS = 1233
IDENTIFIER = re.compile(r"[a-zA-Z_][a-zA-Z0-9_?!-]*\Z")
INTEGER = re.compile(r"-?[0-9]+\Z")
OPERATORS = frozenset({"+", "-", "*", "//", "%", "==", "!=", "<", "<=", ">", ">="})
KEYWORDS = {"true": True, "false": False, "nil": None}


@dataclass(frozen=True, slots=True)
class Token:
    kind: str
    text: str
    value: int | bool | str | None
    span: Span


def tokenize(source: str, *, max_tokens: int = MAX_TOKENS) -> tuple[Token, ...]:
    if type(max_tokens) is not int or not 1 <= max_tokens <= MAX_TOKENS:
        raise ValueError(f"max_tokens must be an integer between 1 and {MAX_TOKENS}")
    if len(source) > MAX_SOURCE_CHARS:
        offset = MAX_SOURCE_CHARS
        line = source.count("\n", 0, offset) + 1
        column = offset - source.rfind("\n", 0, offset)
        raise LanguageError("E_LIMIT", "source length limit exceeded", Span(offset, offset + 1, line, column))
    result: list[Token] = []
    index = 0
    line = column = 1

    def add(kind: str, text: str, value: int | bool | str | None, span: Span) -> None:
        if len(result) >= max_tokens:
            raise LanguageError("E_LIMIT", "token count limit exceeded", span)
        result.append(Token(kind, text, value, span))

    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            if char == "\n":
                line += 1
                column = 1
            else:
                column += 1
            continue
        if char == ";":
            end = source.find("\n", index)
            if end == -1:
                end = len(source)
            column += end - index
            index = end
            continue
        start, start_line, start_column = index, line, column
        if char in "()":
            index += 1
            column += 1
            add(
                "LPAREN" if char == "(" else "RPAREN",
                char,
                None,
                Span(start, index, start_line, start_column),
            )
            continue
        if char == '"':
            index += 1
            escaped = False
            while index < len(source):
                current = source[index]
                if current in "\r\n":
                    raise LanguageError(
                        "E_LEX",
                        "strings cannot contain raw newlines",
                        Span(index, index + 1, line, start_column + index - start),
                    )
                if current == '"' and not escaped:
                    index += 1
                    break
                if current == "\\" and not escaped:
                    escaped = True
                else:
                    escaped = False
                index += 1
            else:
                raise LanguageError("E_LEX", "unterminated string", Span(start, index, line, column))
            text = source[start:index]
            try:
                value = json.loads(text)
            except json.JSONDecodeError as error:
                offset = start + error.pos
                raise LanguageError(
                    "E_LEX",
                    "invalid string escape or control character",
                    Span(offset, min(offset + 1, index), line, start_column + error.pos),
                ) from None
            if any("\ud800" <= character <= "\udfff" for character in value):
                raise LanguageError(
                    "E_LEX",
                    "strings cannot contain unpaired Unicode surrogates",
                    Span(start, index, start_line, start_column),
                )
            column += index - start
            add("STRING", text, value, Span(start, index, start_line, start_column))
            continue
        while index < len(source) and not source[index].isspace() and source[index] not in '();"':
            index += 1
        text = source[start:index]
        span = Span(start, index, start_line, start_column)
        column += index - start
        if INTEGER.fullmatch(text):
            if len(text.removeprefix("-")) > MAX_INTEGER_DIGITS:
                raise LanguageError("E_LIMIT", "integer digit limit exceeded", span)
            add("INTEGER", text, int(text), span)
        elif text in KEYWORDS:
            add("LITERAL", text, KEYWORDS[text], span)
        elif IDENTIFIER.fullmatch(text) or text in OPERATORS:
            add("IDENTIFIER", text, text, span)
        else:
            preview = repr(text[:60]) + ("..." if len(text) > 60 else "")
            raise LanguageError("E_LEX", f"invalid token {preview}", span)
    add("EOF", "", None, Span(index, index, line, column))
    return tuple(result)
