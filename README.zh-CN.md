# Closure Lab 中文入门

这是一个用 **Python 3.11+** 实现的小型解释器，主线是：**词法作用域 → 闭包 → 高阶函数 → 递归 → 可验证的工程实现**。

它不是把多个零散习题直接打包，而是从原有的手工 AST 解释器思路出发，独立整理为可安装、可测试、可讲解的作品集项目。**本次新增解析器、命令行、显式求值栈等功能，属于 AI 辅助的扩展与重写，不应冒称是历史练习里已有的功能。**

## 安装与运行

在项目根目录打开终端：

```bash
python -m pip install -e .
python -m closurelab eval "(+ 20 22)"
python -m closurelab run examples/closures.cl
python -m closurelab run examples/fixed-point.cl --json
python -m closurelab repl
```

安装后也可以使用 `closurelab` 命令。运行不依赖第三方库，开发检查工具需单独安装：

```bash
python -m pip install -e ".[dev]"
```

## 先看这六个例子

| 文件 | 重点 | 最终结果 |
| --- | --- | --- |
| `closures.cl` | 捕获定义位置的变量，不读取调用者局部变量 | `12` |
| `factorial.cl` | `letrec` 命名递归 | `5040` |
| `fibonacci.cl` | 简单树形递归，故意不声称高效 | `55` |
| `fixed-point.cl` | 适用于立即求值的 Z 不动点组合子 | `720` |
| `countdown.cl` | 2000 次递归不依赖 Python 调用栈 | `0` |
| `short-circuit.cl` | 不执行短路分支中的除零或未定义变量 | `true` |

语言采用 S 表达式，例如 `(+ 2 3)`，而不是 Python 的 `2 + 3`。支持整数、严格布尔值、字符串、`nil`、函数、局部绑定与条件。没有浮点数、列表值、导入、赋值或完整的 Python 语法。

## 最值得解释的设计

1. **闭包与词法作用域**：函数保存定义时的环境；后续定义形成新环境，不污染已捕获的旧环境。
2. **显式 continuation 栈**：把未完成的计算放进数据帧，而非递归调用 Python 求值函数。尾递归和非尾递归均可避免宿主栈溢出，但仍受步骤与内存约束。
3. **类型边界**：Python 中 `True == 1`，而本语言 `(== true 1)` 为 `false`，布尔值不参与整数运算。
4. **递归绑定**：`define` 不隐式递归；`letrec` 提供单个递归函数绑定。
5. **可重复验证**：错误行列、短路、求值顺序、资源预算和命令行 JSON 都有自动测试。

## 错误与调试

```bash
closurelab eval "(// 1 0)"
closurelab ast examples/factorial.cl
closurelab run examples/closures.cl --trace --json
```

普通模式显示文件、行、列与插入符号；JSON 模式只输出一个对象。跟踪包含节点类别与源码位置，不输出闭包捕获的环境值。默认求值上限 100000 个状态机步骤，括号深度 80，还有整数、字符串和输出大小上限。**这些限制不是安全沙箱或操作系统隔离。**

REPL 只接受单行完整程序，不支持跨行编辑。`:help` 查看帮助，`:q` 或 `:quit` 退出。成功行保留定义；失败行不会提交新环境。CLI 会缓冲语言打印，成功后才输出。

## 验证

```bash
ruff check .
ruff format --check .
mypy src/closurelab
coverage run -m pytest
coverage report
python -m build
python tools/verify_release.py
```

具体本地测试结果见交付文件 `closure-lab-verification.json`。提供 Python 3.11–3.13 的 CI 配置，但未在远端运行之前不能宣称 CI 已通过。


## 上传范围与许可

发布新的源码、测试、文档、示例与 CI；不发布原始练习、可执行文件、调试文件、Java 字节码、IDE 元数据或凭证。原附件保持不变。本项目按用户确认采用 MIT 许可；详见 `LICENSE` 与 `NOTICE`。
