"""Command-line execution, AST export and a single-line REPL."""

from __future__ import annotations

import argparse
import io
import json
import sys
from dataclasses import asdict
from typing import NoReturn

from . import __version__
from .api import execute
from .ast import to_data
from .errors import LanguageError
from .lexer import MAX_SOURCE_CHARS
from .parser import parse
from .runtime import Execution, Limits, format_value, standard_environment


class _ParserExit(Exception):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(status)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message:
            self._print_message(message, sys.stderr)
        raise _ParserExit(status)


def _parser() -> _ArgumentParser:
    parser = _ArgumentParser(
        prog="closurelab",
        description="An S-expression interpreter for lexical scope, closures and recursion.",
    )
    parser.add_argument("--version", action="version", version=f"closurelab {__version__}")
    commands = parser.add_subparsers(dest="command", title="commands")
    run = commands.add_parser("run", help="Execute a UTF-8 file; use - to read stdin")
    run.add_argument("file", metavar="FILE")
    evaluate = commands.add_parser("eval", help="Execute source passed as an argument")
    evaluate.add_argument("source", metavar="SOURCE")
    for command in (run, evaluate):
        command.add_argument(
            "--json", action="store_true", help="Emit one JSON object, including output or errors"
        )
        command.add_argument(
            "--trace", action="store_true", help="Record a bounded, structured evaluation trace"
        )
        command.add_argument(
            "--max-steps", type=int, default=100_000, metavar="N", help="Evaluation step budget"
        )
    ast = commands.add_parser("ast", help="Export a file as a JSON AST; use - to read stdin")
    ast.add_argument("file", metavar="FILE")
    commands.add_parser("repl", help="Single-line REPL; keep definitions after successful execution")
    return parser


def _read_source(filename: str) -> str:
    if filename == "-":
        source = sys.stdin.read(MAX_SOURCE_CHARS + 1)
    else:
        with open(filename, encoding="utf-8-sig") as stream:
            source = stream.read(MAX_SOURCE_CHARS + 1)
    if len(source) > MAX_SOURCE_CHARS:
        raise LanguageError("E_LIMIT", "Source length limit exceeded")
    return source.removeprefix("\ufeff")


def _json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=True))


def _report_error(error: LanguageError, source: str, filename: str, *, json_mode: bool) -> None:
    if json_mode:
        _json(
            {
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "filename": filename,
                    "span": asdict(error.span) if error.span is not None else None,
                }
            }
        )
    else:
        print(error.render(source, filename), file=sys.stderr)


def _show_execution(result: Execution, *, json_mode: bool, trace: bool) -> None:
    if json_mode:
        _json(result.to_data())
        return
    for line in result.output:
        print(line)
    print(format_value(result.value))
    if trace:
        print(
            json.dumps(
                {
                    "trace": [event.to_data() for event in result.trace],
                    "trace_truncated": result.trace_truncated,
                },
                ensure_ascii=True,
            ),
            file=sys.stderr,
        )


def _repl() -> int:
    environment = standard_environment()
    interactive = sys.stdin.isatty()
    if interactive:
        print("ClosureLab single-line REPL; :help for help, :quit to exit.")
    while True:
        if interactive:
            print("closurelab> ", end="", flush=True)
        line = sys.stdin.readline(MAX_SOURCE_CHARS + 2)
        if not line:
            return 0
        source = line.rstrip("\r\n")
        if len(source) > MAX_SOURCE_CHARS:
            while line and not line.endswith("\n"):
                line = sys.stdin.readline(MAX_SOURCE_CHARS + 2)
            _report_error(
                LanguageError("E_LIMIT", "Source length limit exceeded"), "", "<repl>", json_mode=False
            )
            continue
        command = source.strip()
        if command in (":quit", ":q"):
            return 0
        if command == ":help":
            print("Enter complete S-expression source on each line (no multiline input).")
            print("Successful lines keep definitions; failed lines do not commit definitions.")
            print(":help for help; :quit or :q to exit; EOF also exits.")
            continue
        if not command or command.startswith(";"):
            continue
        try:
            result = execute(source, environment=environment)
        except LanguageError as error:
            _report_error(error, source, "<repl>", json_mode=False)
            continue
        environment = result.environment
        _show_execution(result, json_mode=False, trace=False)


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in arguments or bool(arguments and arguments[0] == "ast")
    source = ""
    filename = "<cli>"
    try:
        for stream in (sys.stdout, sys.stderr):
            if isinstance(stream, io.TextIOWrapper):
                stream.reconfigure(errors="backslashreplace")
        parser = _parser()
        if not arguments:
            parser.print_help()
            return 0
        options = parser.parse_args(arguments)
        if options.command is None:
            parser.print_help()
            return 0
        if options.command == "repl":
            filename = "<repl>"
            return _repl()
        if options.command == "eval":
            filename = "<eval>"
            source = options.source
        else:
            filename = "<stdin>" if options.file == "-" else options.file
            source = _read_source(options.file)
        if options.command == "ast":
            _json(to_data(parse(source)))
            return 0
        limits = Limits(max_steps=options.max_steps)
        result = execute(source, limits=limits, trace=options.trace)
        _show_execution(result, json_mode=options.json, trace=options.trace)
        return 0
    except _ParserExit as error:
        return error.status
    except LanguageError as error:
        _report_error(error, source, filename, json_mode=json_mode)
        return 2
    except (OSError, UnicodeError) as error:
        _report_error(LanguageError("E_IO", str(error)), "", filename, json_mode=json_mode)
        return 1
    except ValueError as error:
        _report_error(LanguageError("E_ARGUMENT", str(error)), "", "<cli>", json_mode=json_mode)
        return 2
    except KeyboardInterrupt:
        if json_mode:
            _report_error(
                LanguageError("E_INTERRUPTED", "Execution interrupted"), "", filename, json_mode=True
            )
        else:
            print("Execution interrupted", file=sys.stderr)
        return 130
