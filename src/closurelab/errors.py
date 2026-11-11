from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int
    line: int
    column: int


class LanguageError(Exception):
    def __init__(self, code: str, message: str, span: Span | None = None) -> None:
        self.code = code
        self.message = message
        self.span = span
        super().__init__(message)

    def render(self, source: str, filename: str = "<input>") -> str:
        if self.span is None:
            return f"{filename}: {self.code}: {self.message}"
        span = self.span
        header = f"{filename}:{span.line}:{span.column}: {self.code}: {self.message}"
        lines = source.split("\n")
        if not 1 <= span.line <= len(lines):
            return header
        line = lines[span.line - 1].removesuffix("\r")
        column = min(max(span.column - 1, 0), len(line))
        start = max(0, column - 60)
        end = min(len(line), start + 120)
        prefix = "..." if start else ""
        suffix = "..." if end < len(line) else ""
        excerpt = prefix + line[start:end] + suffix
        before = prefix + line[start:column]
        width = min(max(span.end - span.start, 1), max(end - column, 1))
        marker = " " * len(before.expandtabs(4)) + "^" * width
        return f"{header}\n{excerpt.expandtabs(4)}\n{marker}"
