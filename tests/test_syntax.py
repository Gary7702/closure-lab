import json
from dataclasses import FrozenInstanceError

import pytest

from closurelab.ast import Begin, Call, Define, If, Lambda, Let, Literal, Logic, Program, Variable, to_data
from closurelab.errors import LanguageError, Span
from closurelab.lexer import MAX_INTEGER_DIGITS, MAX_SOURCE_CHARS, tokenize
from closurelab.parser import parse


def test_tokens_preserve_types_text_and_locations():
    tokens = tokenize('; 注释\n(-12 true false nil "你好\\n\\u4e16\\u754c" x? //)')
    assert [token.kind for token in tokens] == [
        "LPAREN",
        "INTEGER",
        "LITERAL",
        "LITERAL",
        "LITERAL",
        "STRING",
        "IDENTIFIER",
        "IDENTIFIER",
        "RPAREN",
        "EOF",
    ]
    assert type(tokens[1].value) is int
    assert tokens[1].value == -12
    assert type(tokens[2].value) is bool
    assert tokens[2].value is True
    assert tokens[3].value is False
    assert tokens[4].value is None
    assert tokens[5].value == "你好\n世界"
    assert tokens[1].text == "-12"
    assert tokens[0].span == Span(5, 6, 2, 1)
    assert tokens[1].span == Span(6, 9, 2, 2)
    assert tokens[-1].text == ""
    assert tokens[-1].span.start == tokens[-1].span.end


def test_empty_input_and_comment_have_eof():
    assert parse("; 只有注释\n").expressions == ()
    eof = tokenize("; comment")[-1]
    assert eof.kind == "EOF"
    assert eof.span == Span(9, 9, 1, 10)


@pytest.mark.parametrize("source", ["@", "1.2", "123abc", "+12", "变量", "a+b", "&", "/", "==="])
def test_unknown_characters_and_atoms_are_not_skipped(source):
    with pytest.raises(LanguageError) as caught:
        tokenize(source)
    assert caught.value.code == "E_LEX"
    assert caught.value.span == Span(0, len(source), 1, 1)


@pytest.mark.parametrize(
    "source",
    ['"unterminated', '"bad\\q"', '"bad\nline"', '"bad\rline"', '"bad\tline"', '"\\uZZZZ"', '"bad\\\nline"'],
)
def test_invalid_strings(source):
    with pytest.raises(LanguageError) as caught:
        tokenize(source)
    assert caught.value.code == "E_LEX"
    assert caught.value.span is not None


def test_escaped_quote_and_backslash():
    value = '引号 " 与反斜杠 \\ ; ()'
    assert tokenize(json.dumps(value, ensure_ascii=False))[0].value == value


def test_integer_digit_limit_before_conversion():
    token = tokenize("-" + "1" * MAX_INTEGER_DIGITS)[0]
    assert type(token.value) is int
    with pytest.raises(LanguageError, match="digit") as caught:
        tokenize("0" * (MAX_INTEGER_DIGITS + 1))
    assert caught.value.code == "E_LIMIT"


def test_source_length_limit():
    with pytest.raises(LanguageError) as caught:
        tokenize(" " * (MAX_SOURCE_CHARS + 1))
    assert caught.value.code == "E_LIMIT"
    assert caught.value.span == Span(MAX_SOURCE_CHARS, MAX_SOURCE_CHARS + 1, 1, MAX_SOURCE_CHARS + 1)


def test_token_limit_includes_eof():
    assert len(tokenize("x y", max_tokens=3)) == 3
    assert len(tokenize("", max_tokens=1)) == 1
    for source, limit in [("x y", 2), ("x", 1)]:
        with pytest.raises(LanguageError) as caught:
            tokenize(source, max_tokens=limit)
        assert caught.value.code == "E_LIMIT"
    with pytest.raises(LanguageError) as caught:
        tokenize("x " * 100_000)
    assert caught.value.code == "E_LIMIT"


@pytest.mark.parametrize("limit", [0, -1, 100_001, 200_000, True, False, 1.0, "1", None])
def test_invalid_token_limits_raise_value_error(limit):
    with pytest.raises(ValueError, match="max_tokens"):
        tokenize("", max_tokens=limit)


@pytest.mark.parametrize("limit", [0, -1, 81, 200, True, False, 1.0, "1", None])
def test_invalid_depth_limits_raise_value_error(limit):
    with pytest.raises(ValueError, match="max_depth"):
        parse("1", max_depth=limit)


@pytest.mark.parametrize("source", ['"\\ud800"', '"\\udfff"', '"\\ud800x"', '"\\udc00\\ud800"', '"\ud800"'])
def test_unpaired_unicode_surrogates_are_lexical_errors(source):
    with pytest.raises(LanguageError, match="surrogates") as caught:
        tokenize(source)
    assert caught.value.code == "E_LEX"
    assert caught.value.span == Span(0, len(source), 1, 1)


def test_valid_unicode_surrogate_pair_is_decoded():
    token = tokenize('"\\ud83d\\ude00"')[0]
    assert token.value == "\U0001f600"
    assert len(token.value) == 1
    assert token.value.encode("utf-8") == b"\xf0\x9f\x98\x80"


def test_literals_and_operator_references():
    nodes = parse('-12 true false nil "世界" + - * // % == != < <= > >=').expressions
    assert [node.value for node in nodes[:5]] == [-12, True, False, None, "世界"]
    assert type(nodes[0].value) is int
    assert type(nodes[1].value) is bool
    assert all(isinstance(node, Variable) for node in nodes[5:])


def test_call_and_all_special_forms():
    nodes = parse(
        "(lambda (x y) (+ x y)) (lambda () 7) (if true 1 2) "
        "(let (x 1) x) (letrec (f 42) f) (begin 1 2) "
        "(and true false true) (or false true) (not false) (define double (lambda (x) (* x 2)))"
    ).expressions
    assert isinstance(nodes[0], Lambda)
    assert nodes[0].parameters == ("x", "y")
    assert isinstance(nodes[0].body, Call)
    assert nodes[1].parameters == ()
    assert isinstance(nodes[2], If)
    assert isinstance(nodes[3], Let) and nodes[3].recursive is False
    assert isinstance(nodes[4], Let) and nodes[4].recursive is True
    assert isinstance(nodes[4].value, Literal)
    assert isinstance(nodes[5], Begin)
    assert [node.operator for node in nodes[6:9]] == ["and", "or", "not"]
    assert all(isinstance(node, Logic) for node in nodes[6:9])
    assert isinstance(nodes[9], Define)
    assert isinstance(parse("((lambda () 7))").expressions[0].function, Lambda)


@pytest.mark.parametrize(
    "source",
    [
        "()",
        ")",
        "(x",
        "1 ) 2",
        "(lambda)",
        "(lambda (x))",
        "(lambda () 1 2)",
        "(lambda x x)",
        "(lambda (x x) x)",
        "(lambda (12) 1)",
        '(lambda ("x") 1)',
        "(lambda (true) 1)",
        "(lambda (+) 1)",
        "(lambda (if) 1)",
        "(lambda ((x)) 1)",
        "(if true 1)",
        "(if true 1 2 3)",
        "(let x 1)",
        "(let (x) 1)",
        "(let (x 1 2) x)",
        "(let (nil 1) 2)",
        "(letrec (lambda 1) 2)",
        "(begin)",
        "(and true)",
        "(or)",
        "(not)",
        "(not true false)",
        "(define x)",
        "(define + 1)",
        "(define false 1)",
        "(begin (define x 1) x)",
        "(lambda () (define x 1))",
        "(f (define x 1))",
        "(if true (define x 1) 2)",
        "(define x (define y 2))",
        "(let (x (define y 2)) x)",
    ],
)
def test_invalid_syntax_has_stable_parse_errors(source):
    with pytest.raises(LanguageError) as caught:
        parse(source)
    assert caught.value.code == "E_PARSE"
    assert caught.value.span is not None


@pytest.mark.parametrize(
    "name",
    [
        "lambda",
        "if",
        "let",
        "letrec",
        "begin",
        "and",
        "or",
        "not",
        "define",
        "true",
        "false",
        "nil",
        "+",
        "-",
        "*",
        "//",
        "%",
        "==",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
    ],
)
def test_every_reserved_name_is_rejected_as_binding(name):
    for source in [f"(lambda ({name}) 1)", f"(let ({name} 1) 2)", f"(define {name} 1)"]:
        with pytest.raises(LanguageError) as caught:
            parse(source)
        assert caught.value.code == "E_PARSE"


def test_valid_binding_names_and_multiple_definitions():
    nodes = parse("(define _x-2?! 1) (define x 2) (let (x? 3) x?)").expressions
    assert nodes[0].name == "_x-2?!"
    assert len(nodes) == 3


def test_nesting_limit_precedes_python_recursion_error():
    source = "(f " * 80 + "1" + ")" * 80
    node = parse(source).expressions[0]
    for _ in range(80):
        assert isinstance(node, Call)
        node = node.arguments[0]
    assert node.value == 1
    json.dumps(to_data(parse(source)))
    for nested, depth in [
        ("(f " * 81 + "1" + ")" * 81, 80),
        ("(f " * 5 + "1" + ")" * 5, 4),
        ("(f (g 1))", 1),
    ]:
        with pytest.raises(LanguageError) as caught:
            parse(nested, max_depth=depth)
        assert caught.value.code == "E_LIMIT"
    assert parse("(f 1)", max_depth=1)
    assert parse("1", max_depth=1)
    with pytest.raises(LanguageError) as caught:
        parse("(lambda () 1)", max_depth=1)
    assert caught.value.code == "E_LIMIT"


def test_exact_multiline_node_spans_and_json_data():
    program = parse("; test\n(+ 1\n 2)")
    call = program.expressions[0]
    assert call.span == Span(7, 15, 2, 1)
    assert call.arguments[1].span == Span(13, 14, 3, 2)
    assert to_data(program) == {
        "type": "Program",
        "expressions": [
            {
                "type": "Call",
                "span": {"start": 7, "end": 15, "line": 2, "column": 1},
                "function": {
                    "type": "Variable",
                    "span": {"start": 8, "end": 9, "line": 2, "column": 2},
                    "name": "+",
                },
                "arguments": [
                    {"type": "Literal", "span": {"start": 10, "end": 11, "line": 2, "column": 4}, "value": 1},
                    {"type": "Literal", "span": {"start": 13, "end": 14, "line": 3, "column": 2}, "value": 2},
                ],
            }
        ],
    }
    assert json.loads(json.dumps(to_data(parse("true 1 false 0 nil"))))["expressions"][0]["value"] is True


def test_public_objects_are_immutable():
    node = Literal(span=Span(0, 1, 1, 1), value=1)
    with pytest.raises(FrozenInstanceError):
        node.value = 2
    with pytest.raises(FrozenInstanceError):
        node.span.start = 2
    with pytest.raises(FrozenInstanceError):
        Program((node,)).expressions = ()
    with pytest.raises(FrozenInstanceError):
        tokenize("1")[0].text = "2"


def test_error_fields_and_exact_render():
    error = LanguageError("E_PARSE", "unexpected closing parenthesis", Span(5, 6, 2, 3))
    assert error.code == "E_PARSE"
    assert error.message == "unexpected closing parenthesis"
    assert str(error) == "unexpected closing parenthesis"
    assert (
        error.render("ok\n  )", "demo.cl") == "demo.cl:2:3: E_PARSE: unexpected closing parenthesis\n  )\n  ^"
    )
    assert LanguageError("E_LIMIT", "限制").render("") == "<input>: E_LIMIT: 限制"
    with pytest.raises(LanguageError) as caught:
        parse("ok\n  )")
    assert caught.value.span == Span(5, 6, 2, 3)
    assert caught.value.render("ok\n  )", "demo.cl") == error.render("ok\n  )", "demo.cl")


def test_long_line_render_keeps_caret_at_offending_character():
    source = "x" * 300 + "@" + "y" * 300
    error = LanguageError("E_LEX", "无效字符", Span(300, 301, 1, 301))
    header, excerpt, marker = error.render(source).splitlines()
    assert "1:301" in header
    assert len(excerpt) <= 126
    assert excerpt[marker.index("^")] == "@"
    assert excerpt.startswith("...") and excerpt.endswith("...")


def test_tab_and_eof_carets_are_aligned():
    rendered = LanguageError("E_PARSE", "错误", Span(1, 2, 1, 2)).render("\t)")
    assert rendered.splitlines()[1:] == ["    )", "    ^"]
    rendered = LanguageError("E_PARSE", "错误", Span(300, 300, 1, 301)).render("x" * 300)
    excerpt, marker = rendered.splitlines()[1:]
    assert marker.index("^") == len(excerpt)
