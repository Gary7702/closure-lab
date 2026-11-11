"""Behavioral regression tests for the public API, CLI and REPL."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from closurelab import Environment, LanguageError, Limits, __version__, execute, format_value
from closurelab.cli import main
from closurelab.lexer import MAX_SOURCE_CHARS


@pytest.mark.parametrize("arguments", [[], ["--help"], ["run", "--help"], ["repl", "--help"]])
def test_help(arguments, capsys):
    assert main(arguments) == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out
    assert not captured.err


def test_version(capsys):
    assert main(["--version"]) == 0
    assert capsys.readouterr().out == f"closurelab {__version__}\n"


def test_eval_prints_output_before_value(capsys):
    assert main(["eval", '(print "你好" 3) (+ 20 22)']) == 0
    captured = capsys.readouterr()
    assert captured.out == "你好 3\n42\n"
    assert not captured.err


def test_eval_empty_and_nil(capsys):
    assert main(["eval", ""]) == 0
    assert capsys.readouterr().out == "nil\n"
    assert main(["eval", "nil"]) == 0
    assert capsys.readouterr().out == "nil\n"


def test_run_unicode_utf8_bom_file(tmp_path, capsys):
    path = tmp_path / "闭包程序.cl"
    path.write_text('(print "中文 café") (+ 1 2)', encoding="utf-8-sig")
    assert main(["run", str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == "中文 café\n3\n"
    assert not captured.err


def test_run_stdin(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO('\ufeff(+ "甲" "乙")'))
    assert main(["run", "-"]) == 0
    assert capsys.readouterr().out == "甲乙\n"


def test_ast_json(tmp_path, capsys):
    path = tmp_path / "program.cl"
    path.write_text("(+ 2 3)", encoding="utf-8")
    assert main(["ast", str(path)]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["type"] == "Program"
    assert data["expressions"][0]["type"] == "Call"
    assert not captured.err


def test_ast_stdin(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("7"))
    assert main(["ast", "-"]) == 0
    assert json.loads(capsys.readouterr().out)["expressions"][0]["value"] == 7


@pytest.mark.parametrize(
    "source, code",
    [
        ("(", "E_PARSE"),
        ("@", "E_LEX"),
        ("missing", "E_NAME"),
        ("(// 1 0)", "E_ZERO"),
        ("(if 1 2 3)", "E_TYPE"),
    ],
)
def test_language_errors_have_caret(source, code, capsys):
    assert main(["eval", source]) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert code in captured.err
    assert "<eval>:1:" in captured.err
    assert "^" in captured.err


def test_error_reports_filename(tmp_path, capsys):
    path = tmp_path / "bad.cl"
    path.write_text("\nmissing", encoding="utf-8")
    assert main(["run", str(path)]) == 2
    assert f"{path}:2:1:" in capsys.readouterr().err


def test_missing_file(tmp_path, capsys):
    assert main(["run", str(tmp_path / "missing.cl")]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "E_IO" in captured.err


def test_invalid_utf8(tmp_path, capsys):
    path = tmp_path / "invalid.cl"
    path.write_bytes(b"\xff\xfe")
    assert main(["run", str(path)]) == 1
    assert "E_IO" in capsys.readouterr().err


def test_directory_is_io_error(tmp_path, capsys):
    assert main(["run", str(tmp_path)]) == 1
    assert "E_IO" in capsys.readouterr().err


def test_step_budget(capsys):
    assert main(["eval", "(+ 1 2)", "--max-steps", "1"]) == 2
    assert "E_LIMIT" in capsys.readouterr().err


def test_recursive_step_budget(capsys):
    source = "(letrec (loop (lambda (n) (loop (+ n 1)))) (loop 0))"
    assert main(["eval", source, "--max-steps", "50"]) == 2
    assert "E_LIMIT" in capsys.readouterr().err


@pytest.mark.parametrize("budget", ["0", "-1", "10000001", "oops"])
def test_invalid_budget_is_argument_error(budget, capsys):
    assert main(["eval", "1", "--max-steps", budget]) == 2
    assert "E_ARGUMENT" in capsys.readouterr().err


@pytest.mark.parametrize("arguments", [["unknown"], ["eval"], ["run"], ["eval", "1", "--unknown"]])
def test_invalid_arguments(arguments, capsys):
    assert main(arguments) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert "E_ARGUMENT" in captured.err


def test_source_read_is_bounded(monkeypatch, capsys):
    class TrackedInput(io.StringIO):
        def read(self, size=-1):
            assert size == MAX_SOURCE_CHARS + 1
            return super().read(size)

    stream = TrackedInput(" " * (MAX_SOURCE_CHARS + 100))
    monkeypatch.setattr(sys, "stdin", stream)
    assert main(["run", "-"]) == 2
    assert stream.tell() == MAX_SOURCE_CHARS + 1
    assert "E_LIMIT" in capsys.readouterr().err


def test_eval_source_budget(capsys):
    assert main(["eval", " " * (MAX_SOURCE_CHARS + 1), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "E_LIMIT"


def test_success_json_captures_print_and_trace(capsys):
    assert main(["eval", '(print "你好") (+ 2 3)', "--json", "--trace"]) == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["value"] == 5
    assert data["output"] == ["你好"]
    assert data["steps"] > 0
    assert data["trace"]
    assert data["trace_truncated"] is False
    assert "environment" not in data
    assert not captured.err


def test_closure_json_is_serializable(capsys):
    assert main(["eval", "(lambda (x) x)", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["value"] == {"type": "closure", "parameters": ["x"]}


def test_json_language_error_does_not_leak_prior_output(capsys):
    assert main(["eval", '(print "不要泄漏") (// 1 0)', "--json"]) == 2
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["error"]["code"] == "E_ZERO"
    assert data["error"]["filename"] == "<eval>"
    assert data["error"]["span"]["line"] == 1
    assert "不要泄漏" not in captured.out
    assert not captured.err


def test_json_io_error(tmp_path, capsys):
    assert main(["run", str(tmp_path / "missing.cl"), "--json"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"]["code"] == "E_IO"
    assert not captured.err


def test_json_argument_error(capsys):
    assert main(["eval", "1", "--max-steps", "nope", "--json"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"]["code"] == "E_ARGUMENT"
    assert not captured.err


def test_ast_error_is_single_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("("))
    assert main(["ast", "-"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["error"]["code"] == "E_PARSE"
    assert not captured.err


def test_normal_trace_stays_on_stderr(capsys):
    assert main(["eval", "(+ 1 2)", "--trace"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "3\n"
    data = json.loads(captured.err)
    assert data["trace"]
    assert set(data["trace"][0]) == {"step", "node", "line", "column"}
    assert "environment" not in captured.err


def test_trace_is_bounded(capsys):
    source = "(begin " + " ".join("1" for _ in range(250)) + ")"
    assert main(["eval", source, "--trace", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert len(data["trace"]) == 200
    assert data["trace_truncated"] is True


def test_repl_persists_success_and_rolls_back_failed_definitions(monkeypatch, capsys):
    lines = "(define x 7)\n(define leaked 9) (// 1 0)\nleaked\n(+ x 1)\n:q\n999\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(lines))
    assert main(["repl"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "7\n8\n"
    assert "E_ZERO" in captured.err
    assert "E_NAME" in captured.err


def test_repl_failure_does_not_replace_prior_definition(monkeypatch, capsys):
    lines = "(define x 7)\n(define x 9) (// 1 0)\nx\n:quit\n"
    monkeypatch.setattr(sys, "stdin", io.StringIO(lines))
    assert main(["repl"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "7\n7\n"
    assert "E_ZERO" in captured.err


def test_repl_help_nil_and_eof(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(':help\n; 注释\n\n(print "你好")\nnil\n'))
    assert main(["repl"]) == 0
    captured = capsys.readouterr()
    assert "no multiline input" in captured.out
    assert captured.out.endswith("你好\nnil\nnil\n")
    assert not captured.err


def test_repl_single_line_parse_error_then_recovers(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("(+ 1\n2\n:quit\n"))
    assert main(["repl"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "2\n"
    assert "E_PARSE" in captured.err


def test_repl_oversized_line_is_discarded(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(" " * (MAX_SOURCE_CHARS + 20) + "99\n5\n"))
    assert main(["repl"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "5\n"
    assert "E_LIMIT" in captured.err


def test_interactive_repl_prompt(monkeypatch, capsys):
    class TerminalInput(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", TerminalInput(":q\n"))
    assert main(["repl"]) == 0
    captured = capsys.readouterr()
    assert "single-line REPL" in captured.out
    assert captured.out.endswith("closurelab> ")


@pytest.mark.parametrize("arguments", [["run", "-"], ["repl"], ["run", "-", "--json"]])
def test_keyboard_interrupt(monkeypatch, capsys, arguments):
    class InterruptedInput(io.StringIO):
        def read(self, size=-1):
            raise KeyboardInterrupt

        def readline(self, size=-1):
            raise KeyboardInterrupt

    monkeypatch.setattr(sys, "stdin", InterruptedInput())
    assert main(arguments) == 130
    captured = capsys.readouterr()
    if "--json" in arguments:
        assert json.loads(captured.out)["error"]["code"] == "E_INTERRUPTED"
        assert not captured.err
    else:
        assert "interrupted" in captured.err


def test_main_reads_sys_argv(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["closurelab", "eval", "(+ 1 2)"])
    assert main() == 0
    assert capsys.readouterr().out == "3\n"


def test_public_api_environment_and_limits():
    result = execute("(+ x 1)", environment=Environment({"x": 8, "+": execute("+").value}))
    assert result.value == 9
    assert result.environment.lookup("x") == 8
    assert format_value(execute("nil").value) == "nil"
    with pytest.raises(LanguageError, match="budget"):
        execute("(+ 1 2)", limits=Limits(max_steps=1))


def test_public_api_retains_execution_metadata():
    result = execute('(print "test") 3', trace=True)
    assert result.value == 3
    assert result.output == ("test",)
    assert result.trace
    assert result.to_data()["value"] == 3


@pytest.mark.parametrize(
    "arguments, source, status, expected",
    [
        (["--version"], None, 0, "closurelab 0.1.0\n"),
        (["eval", "(+ 20 22)"], None, 0, "42\n"),
        (["run", "-"], '(+ "中文" " café")', 0, "中文 café\n"),
        (["eval", "("], None, 2, ""),
    ],
)
def test_python_module_subprocess(arguments, source, status, expected):
    project = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(project / "src"), PYTHONUTF8="1")
    completed = subprocess.run(
        [sys.executable, "-m", "closurelab", *arguments],
        input=source,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        cwd=project,
        timeout=10,
        check=False,
    )
    assert completed.returncode == status
    assert completed.stdout == expected
    if status == 2:
        assert "E_PARSE" in completed.stderr
    else:
        assert not completed.stderr


@pytest.mark.parametrize("encoding", ["gbk", "ascii"])
@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize("valid", [False, True])
def test_non_utf8_output_preserves_status_and_json_semantics(monkeypatch, encoding, json_mode, valid):
    stdout_buffer, stderr_buffer = io.BytesIO(), io.BytesIO()
    stdout = io.TextIOWrapper(stdout_buffer, encoding=encoding, newline="", write_through=True)
    stderr = io.TextIOWrapper(stderr_buffer, encoding=encoding, newline="", write_through=True)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    arguments = ["eval", '(print "😀") "😀"' if valid else "😀"]
    if json_mode:
        arguments.append("--json")
    assert main(arguments) == (0 if valid else 2)
    assert stdout.encoding == stderr.encoding == encoding
    output = stdout_buffer.getvalue().decode(encoding)
    diagnostic = stderr_buffer.getvalue().decode(encoding)
    if json_mode:
        assert output.isascii()
        data = json.loads(output)
        if valid:
            assert data["value"] == "😀"
            assert data["output"] == ["😀"]
        else:
            assert data["error"]["code"] == "E_LEX"
            assert "😀" in data["error"]["message"]
        assert not diagnostic
    elif valid:
        assert output == "\\U0001f600\n\\U0001f600\n"
        assert not diagnostic
    else:
        assert not output
        assert "E_LEX" in diagnostic
        assert "\\U0001f600" in diagnostic
        assert "^" in diagnostic


@pytest.mark.parametrize("arguments", [["run", "-"], ["run", "-", "--json"], ["ast", "-"], ["repl"]])
def test_invalid_stdin_encoding_is_io_error(monkeypatch, capsys, arguments):
    stream = io.TextIOWrapper(io.BytesIO(b"\xff"), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", stream)
    assert main(arguments) == 1
    captured = capsys.readouterr()
    if "--json" in arguments or arguments[0] == "ast":
        assert json.loads(captured.out)["error"]["code"] == "E_IO"
        assert not captured.err
    else:
        assert not captured.out
        assert "E_IO" in captured.err


@pytest.mark.parametrize("encoding", ["gbk", "ascii"])
def test_non_utf8_repl_reports_errors_and_keeps_running(monkeypatch, encoding):
    stdout_buffer, stderr_buffer = io.BytesIO(), io.BytesIO()
    stdout = io.TextIOWrapper(stdout_buffer, encoding=encoding, newline="", write_through=True)
    stderr = io.TextIOWrapper(stderr_buffer, encoding=encoding, newline="", write_through=True)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(sys, "stdin", io.StringIO('😀\n"😀"\n:q\n'))
    assert main(["repl"]) == 0
    assert stdout_buffer.getvalue().decode(encoding) == "\\U0001f600\n"
    diagnostic = stderr_buffer.getvalue().decode(encoding)
    assert "E_LEX" in diagnostic
    assert "\\U0001f600" in diagnostic


@pytest.mark.parametrize("encoding", ["gbk", "ascii"])
def test_ast_json_preserves_unicode_on_non_utf8_stream(monkeypatch, encoding):
    buffer = io.BytesIO()
    stdout = io.TextIOWrapper(buffer, encoding=encoding, newline="", write_through=True)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stdin", io.StringIO('"😀"'))
    assert main(["ast", "-"]) == 0
    output = buffer.getvalue().decode(encoding)
    assert output.isascii()
    assert json.loads(output)["expressions"][0]["value"] == "😀"
