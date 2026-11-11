# Language reference

Closure Lab is an intentionally small expression language, not an implementation of Python, Scheme or JavaScript. Its syntax uses S-expressions; parentheses are structural, not optional grouping punctuation.

## Lexical grammar

```ebnf
program    = { expression } ;
expression = integer | string | literal | identifier | operator | list ;
list       = "(" , expression , { expression } , ")" ;
integer    = [ "-" ] , digit , { digit } ;
literal    = "true" | "false" | "nil" ;
identifier = ( letter | "_" ) , { letter | digit | "_" | "?" | "!" | "-" } ;
operator   = "+" | "-" | "*" | "//" | "%" | "==" | "!=" | "<" | "<=" | ">" | ">=" ;
```

Letters in identifiers are ASCII. Strings use double quotes and JSON escapes; Unicode characters are supported, but lone surrogate code points and raw newlines inside strings are rejected. A semicolon starts a comment ending at the next newline. Whitespace separates tokens. There are no floats, quotes, lists-as-values, imports, attributes or assignment. Empty programs produce `nil`; empty expression lists are errors.

## Forms and evaluation

| Form | Semantics |
| --- | --- |
| `(lambda (x y) body)` | Capture the current lexical environment; zero or more unique parameters. |
| `(function arg ...)` | Evaluate function, then arguments left-to-right; exact arity. |
| `(if condition consequence alternative)` | Strict boolean condition; evaluate only the selected branch. |
| `(let (name value) body)` | Evaluate value in the outer environment, then body in a new local frame. |
| `(letrec (name (lambda (...) body)) expression)` | One recursive function binding; its closure sees itself. Non-lambda values are rejected. |
| `(begin expression ...)` | At least one expression, evaluate in order, return the last value. |
| `(and expression expression ...)` | At least two booleans; stop at first false. |
| `(or expression expression ...)` | At least two booleans; stop at first true. |
| `(not expression)` | Negate one strict boolean. |
| `(define name expression)` | Top-level only; evaluate, then extend the persistent environment. Returns the defined value. |

A binding name must be an identifier, not a literal, operator or special-form keyword. The built-ins `len` and `print` can be shadowed deliberately. `define` does **not** provide implicit recursion: use `letrec` for a recursive function.

## Values and operators

- Integers are signed and size-limited. Booleans are not integers, despite Python's host-language relationship.
- `+`, `-`, `*`, `//`, `%` take two integers. `//` rounds toward negative infinity; `%` has the divisor's sign. Division by zero is an error.
- `+` also concatenates two strings. `<`, `<=`, `>`, `>=` compare two integers or two strings; strings compare by Unicode code-point order.
- `==` and `!=` compare primitive values with strict types: `(== true 1)` is false. Function equality is unsupported.
- `(len string)` counts Unicode code points, not bytes or user-perceived grapheme clusters.
- `(print value ...)` accepts any number of values, records one line and returns `nil`.
- Functions are first-class: an operator can be passed or stored, and a closure can return another closure.

## Lexical scope is a snapshot

```lisp
(define x 10)
(define add-x (lambda (y) (+ x y)))
(define x 1000)
(let (x 999) (add-x 5)) ; 15, not 1004 or 1005
```

Every definition creates a new immutable frame. `add-x` retains the frame visible at definition time. It cannot see names defined later. This is a deliberate, testable language choice, not an incidental Python dictionary behavior.

## Fixed points

The provided `fixed-point.cl` demonstrates the **Z combinator**, suitable for eager/call-by-value evaluation. The extra lambda delays self-application. Calling this the unmodified Y combinator would obscure that evaluation-order distinction.

## Limits and errors

Defaults: source 1,000,000 characters, 100,000 tokens **including EOF**, 80 nested parentheses, 100,000 evaluation-machine transitions, 4096 integer bits, 100,000 string characters, 100,000 recorded output characters including newline separators, and 200 trace events. Integers are lexically limited to 1233 decimal digits before conversion; the runtime then enforces the bit limit. Leading zero digits still count toward the lexical limit.

`Limits` can lower runtime budgets; maximum configurable values are explicitly validated. The CLI exposes `--max-steps`. These are deterministic work/size guardrails, **not** a process-isolation or memory-hard security sandbox. Parsing uses bounded Python recursion; evaluation and environment lookup use explicit iteration. Trace events record node type and source position, not captured values.

Stable diagnostic codes: `E_LEX`, `E_PARSE`, `E_NAME`, `E_TYPE`, `E_ARITY`, `E_ZERO`, `E_LIMIT`, `E_RUNTIME`. CLI failures add `E_IO`, `E_ARGUMENT`, `E_INTERRUPTED`. Source offsets are zero-based character offsets with exclusive ends; displayed line and column numbers are one-based. Error excerpts are cropped; tabs are expanded. CJK/combining-character terminal display widths are not normalized.

## CLI output contract

Normal successful execution prints recorded language output and then the final value. `--json` emits exactly one JSON object containing value, output, steps and optional trace. Errors emit one error object in JSON mode or a caret diagnostic to stderr in normal mode. Recorded language output from a failed execution is not emitted by the CLI. Trusted Python hosts using the optional evaluator output callback may already have observed output; no rollback of external callbacks is promised.

Exit codes: `0` success/help, `1` file/encoding I/O failure, `2` argument or language error, `130` interruption. REPL is **single-line**: successful definitions persist; an unsuccessful line does not publish its new environment. `:help`, `:q` and `:quit` are supported.
