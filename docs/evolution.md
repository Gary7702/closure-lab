# From self-study exercises to Closure Lab

## What the supplied exercises actually showed

The author's Python exercise contained a `Scope` parent chain, manually constructed expression objects, a closure carrying a function and environment, conditional evaluation and primitive binary operations. It also exercised higher-order functions and an eager fixed-point expression for factorial and Fibonacci. A separate Python draft contained an unfinished evaluator branch.

Other supplied files explored JavaScript arrays/search/sorting, Rust ownership/linked lists and interpreter variants, Java collections, and C++ object lifetime. They are useful evidence of the learning journey, but bundling multiple partially finished exercises and compiled executables would dilute the central project.

## What is new in this repository

| Earlier approach | Current engineering iteration |
| --- | --- |
| Construct AST objects manually | Parse complete textual programs with source spans |
| Large exercise script with unused imports and top-level demos | Installable package with separated module responsibilities |
| Dictionary scope and `None`-based missing detection | Immutable lexical frames; `nil` is a valid binding, not a missing sentinel |
| Host-recursive tree walker | Explicit continuations and bounded machine transitions |
| Small ad-hoc print/test helper | Automated semantic, syntax, resource and CLI regressions |
| Implicit host arithmetic/error behavior | Strict documented types, stable error codes and bounded values |
| Literal/variable/function/call/if/binary expressions | Also let/letrec, multiple parameters, sequencing, short-circuit logic, definitions |
| Console examples embedded in the exercise | Versioned source examples, REPL, AST JSON and bounded trace |
| IDE/compiled files next to source | Clean source package, CI and release allowlist |

This is an **AI-assisted extension and rewrite** developed for the portfolio. The parser, continuation machine, tooling and documentation are not retrospectively attributed to the original self-study stage. Understand and explain these additions before presenting them as skills you can reproduce independently.

## Attribution and publication

The author confirmed that the supplied historical code was independently written and authorized this new project for public MIT publication. Some historical comments still looked like instructional scaffolding; the original files are deliberately not redistributed. If an actual third-party course or template is later identified, review and attribute it before incorporating its source.

No original binary, debug database, bytecode, archive, IDE project metadata or personal path is included. The historical files remain unmodified outside this project. Standard concepts are not presented as novel inventions.

## Good interview discussions

- Demonstrate why a closure resolves the definition environment, not the calling environment.
- Explain why `(== true 1)` is false even though Python would equate them.
- Explain the difference between Y and Z under eager evaluation.
- Show one continuation frame and walk through how it replaces a Python stack frame.
- Explain why deep recursion is stack-safe but still bounded and not necessarily memory-constant.
- Explain the snapshot semantics of top-level definitions and why recursive definitions require `letrec`.
- Trigger a malformed-input diagnostic and a step-budget error; explain the exit codes and source spans.

Do not describe this as a production language, a complete Python implementation, an audited sandbox or a performance-optimized compiler.
