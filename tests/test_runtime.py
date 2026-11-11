from pathlib import Path

import pytest

from closurelab.ast import Define, Literal
from closurelab.errors import LanguageError, Span
from closurelab.parser import parse
from closurelab.runtime import (
    Builtin,
    Closure,
    Environment,
    Evaluator,
    Limits,
    _Cell,
    format_value,
    standard_environment,
    value_data,
)


def run(source, **kwargs):
    return Evaluator(**kwargs).run(parse(source))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("42", 42),
        ("-12", -12),
        ("true", True),
        ("false", False),
        ("nil", None),
        ('"hello"', "hello"),
        ("(+ 2 3)", 5),
        ("(- 9 4)", 5),
        ("(* 7 7)", 49),
        ("(// 7 3)", 2),
        ("(% 7 3)", 1),
        ("(// -7 3)", -3),
        ("(% -7 3)", 2),
        ("(== 2 2)", True),
        ("(!= 2 2)", False),
        ("(== true 1)", False),
        ("(== nil nil)", True),
        ('(!= 1 "1")', True),
        ("(< 1 2)", True),
        ("(<= 2 2)", True),
        ("(> 3 2)", True),
        ("(>= 2 2)", True),
        ('(+ "hello " "world")', "hello world"),
        ('(< "a" "b")', True),
        ('(<= "b" "b")', True),
        ('(> "b" "a")', True),
        ('(>= "a" "a")', True),
        ('(len "你好")', 2),
        ("(if true 42 (// 1 0))", 42),
        ("(if false missing 24)", 24),
        ("((lambda (x) (* x x)) 7)", 49),
        ("((lambda () 12))", 12),
        ("((lambda (x y) (+ x y)) 2 3)", 5),
        ("(let (x 1) (let (x 2) x))", 2),
        ("(begin 1 2 3)", 3),
        ("(begin 42)", 42),
        ("(and false missing)", False),
        ("(and true true true)", True),
        ("(and true true false)", False),
        ("(or true missing)", True),
        ("(or false false true)", True),
        ("(or false false)", False),
        ("(not true)", False),
        ("(not false)", True),
        ("(define x 2) (define x 5) x", 5),
        ("(define x nil) x", None),
        ("(let (x 2) (let (y x) y))", 2),
        ("(define op +) (op 2 3)", 5),
    ],
)
def test_values(source, expected):
    value = run(source).value
    assert type(value) is type(expected)
    assert value == expected


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("missing", "E_NAME"),
        ("(let (x x) x)", "E_NAME"),
        ("(if 1 2 3)", "E_TYPE"),
        ("(and true 1)", "E_TYPE"),
        ("(not nil)", "E_TYPE"),
        ('(or false "yes")', "E_TYPE"),
        ("(+ true 1)", "E_TYPE"),
        ('(- "x" "y")', "E_TYPE"),
        ('(+ "x" 1)', "E_TYPE"),
        ('(< 1 "2")', "E_TYPE"),
        ("(len 1)", "E_TYPE"),
        ("(1 2)", "E_TYPE"),
        ("(nil)", "E_TYPE"),
        ("(// 2 0)", "E_ZERO"),
        ("(% 1 0)", "E_ZERO"),
        ("(+ 1)", "E_ARITY"),
        ("(+ 1 2 3)", "E_ARITY"),
        ("(len)", "E_ARITY"),
        ("((lambda (x) x))", "E_ARITY"),
        ("((lambda () 1) 2)", "E_ARITY"),
        ("(== (lambda () 1) (lambda () 1))", "E_TYPE"),
        ("(== + +)", "E_TYPE"),
        ("(letrec (x 1) x)", "E_TYPE"),
    ],
)
def test_errors(source, code):
    with pytest.raises(LanguageError) as caught:
        run(source)
    assert caught.value.code == code
    assert caught.value.span is not None


def test_lexical_scope_and_snapshot():
    source = """(define x 10)
    (define f (lambda (y) (+ x y)))
    (define x 1000)
    (let (x 999) (f 5))"""
    assert run(source).value == 15
    with pytest.raises(LanguageError, match="Undefined variable 'y'"):
        run("(define x 1) (define f (lambda () y)) (define y 2) (f)")


def test_closure_representation_and_environment():
    execution = run("((lambda (x) (lambda (y) (+ x y))) 2)")
    assert isinstance(execution.value, Closure)
    assert format_value(execution.value) == "<closure (y)>"
    assert value_data(execution.value) == {"type": "closure", "parameters": ["y"]}
    assert "environment" not in repr(execution.value)
    assert execution.value.environment.lookup("x") == 2
    assert format_value(Builtin("+", 2)) == "<builtin +>"
    assert value_data(Builtin("+", 2)) == {"type": "builtin", "name": "+"}
    assert format_value(None) == "nil"
    assert format_value(True) == "true"
    assert format_value(False) == "false"


def test_environment_immutable_and_nil_distinct():
    source = {"x": 1, "nil-value": None}
    env = Environment(source)
    source["x"] = 9
    assert env.lookup("x") == 1
    assert env.lookup("nil-value") is None
    child = env.extend({"x": 2})
    assert child.lookup("x") == 2
    assert child.lookup("nil-value") is None
    assert env.lookup("x") == 1
    with pytest.raises(TypeError):
        env.bindings["x"] = 3
    with pytest.raises(LanguageError):
        env.lookup("missing")
    with pytest.raises(LanguageError, match="not initialized"):
        Environment({"x": _Cell()}).lookup("x")


def test_deep_environment_lookup_is_iterative():
    env = Environment({"x": 5})
    for _ in range(3000):
        env = env.extend({})
    assert env.lookup("x") == 5


def test_named_recursion_and_z_combinator():
    root = Path(__file__).resolve().parents[1]
    expected = {
        "factorial.cl": 5040,
        "fibonacci.cl": 55,
        "fixed-point.cl": 720,
        "closures.cl": 12,
        "countdown.cl": 0,
        "short-circuit.cl": True,
    }
    for file, result in expected.items():
        assert run((root / "examples" / file).read_text()).value == result


def test_non_tail_recursion_is_stack_safe():
    code = "(letrec (sum (lambda (n) (if (== n 0) 0 (+ n (sum (- n 1)))))) (sum 1500))"
    assert run(code).value == 1125750


def test_eager_argument_order():
    execution = run('((lambda (x y) (+ x y)) (begin (print "first") 2) (begin (print "second") 3))')
    assert execution.output == ("first", "second")
    assert execution.value == 5


def test_print_and_structured_trace():
    emitted = []
    execution = run('(begin (print "answer" 42 nil true) (+ 1 2))', output=emitted.append, trace=True)
    assert emitted == ["answer 42 nil true"]
    assert execution.output == tuple(emitted)
    assert execution.value == 3
    data = execution.to_data()
    assert data["trace"]
    assert data["value"] == 3
    assert all(set(event) == {"step", "node", "line", "column"} for event in data["trace"])
    assert not execution.trace_truncated
    assert run("(print)").output == ("",)


def test_evaluator_resets_between_runs():
    evaluator = Evaluator(trace=True)
    first = evaluator.run(parse('(print "x")'))
    second = evaluator.run(parse("42"), first.environment)
    assert second.output == ()
    assert second.value == 42
    assert second.steps < first.steps
    assert len(second.trace) == 1
    assert evaluator.run(parse("")).value is None


@pytest.mark.parametrize(
    "source",
    ["(letrec (loop (lambda () (loop))) (loop))", "(letrec (loop (lambda (n) (+ 1 (loop n)))) (loop 0))"],
)
def test_budget_stops_infinite_program(source):
    with pytest.raises(LanguageError) as caught:
        run(source, limits=Limits(max_steps=200))
    assert caught.value.code == "E_LIMIT"


@pytest.mark.parametrize("source", ["256", "(+ 255 1)", "(* 128 2)", '(len "abcdefgh")'])
def test_integer_limits(source):
    limits = Limits(max_integer_bits=3 if source.startswith("(len") else 8)
    with pytest.raises(LanguageError) as caught:
        run(source, limits=limits)
    assert caught.value.code == "E_LIMIT"


@pytest.mark.parametrize("source", ['"abcdef"', '(+ "abc" "def")'])
def test_string_limits(source):
    with pytest.raises(LanguageError) as caught:
        run(source, limits=Limits(max_string_chars=5))
    assert caught.value.code == "E_LIMIT"


def test_output_limit_and_trace_limit():
    with pytest.raises(LanguageError, match="Output size"):
        run('(begin (print "abc") (print "def"))', limits=Limits(max_output_chars=6))
    execution = run("(+ 1 2)", trace=True, limits=Limits(max_trace_events=1))
    assert len(execution.trace) == 1
    assert execution.trace_truncated
    assert run("1", trace=True, limits=Limits(max_trace_events=0)).trace == ()


@pytest.mark.parametrize(
    "name,value",
    [
        ("max_steps", 0),
        ("max_steps", True),
        ("max_steps", 10_000_001),
        ("max_integer_bits", 4097),
        ("max_string_chars", 0),
        ("max_output_chars", -1),
        ("max_trace_events", -1),
    ],
)
def test_invalid_limits(name, value):
    with pytest.raises(ValueError):
        Limits(**{name: value})


def test_nested_define_ast_is_rejected():
    span = Span(0, 1, 1, 1)
    node = Define(span=span, name="x", value=Literal(span=span, value=1))
    with pytest.raises(LanguageError, match="Unsupported AST"):
        Evaluator()._evaluate(node, standard_environment())


def test_external_values_are_budget_checked():
    with pytest.raises(LanguageError, match="Integer size"):
        Evaluator(Limits(max_integer_bits=4)).run(parse("x"), Environment({"x": 100}))
