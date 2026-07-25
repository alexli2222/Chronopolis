"""
General mathematical-function support for ``.mfunc`` files.

A ``.mfunc`` ("mathematical function") file describes a single function f(x) as
a list of term expressions, one per line; the function's value is the sum of
all the terms. This lets it hold either a Fourier series exported by the
regression tool (each line a sinusoid such as ``5sin(2pi/5(x-4))+5``) or any
ordinary expression a user types, e.g. a file containing::

    ln(x+5)-3x

means f(x) = ln(x + 5) - 3x.

Supported in expressions:
  * numbers, incl. scientific notation (1.5, .5, 2.44e-6)
  * variable  x
  * constants pi, e, tau
  * operators + - * / ^  and unary minus, with implicit multiplication
    (3x, 2pi/5(x-4), 2sin(x), (x+1)(x-1))
  * functions sin cos tan asin acos atan sinh cosh tanh
              ln (natural) log (base 10) log2 exp sqrt abs sign floor ceil
"""

import math
import re
from pathlib import Path
from typing import Callable, List

NAN = float("nan")

# ---- available functions & constants -----------------------------------

_FUNC_IMPL = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "atan2": math.atan2, "hypot": math.hypot,  # two-argument
    "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh,
    "ln": math.log, "log": math.log10, "log2": math.log2, "log10": math.log10,
    "exp": math.exp, "sqrt": math.sqrt, "abs": abs,
    "sign": lambda v: (v > 0) - (v < 0),
    "floor": math.floor, "ceil": math.ceil,
}

_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}

SUPPORTED_FUNCTIONS = sorted(_FUNC_IMPL)


# ---- tokenizer ---------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""\s+
      | (?P<NUMBER>(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
      | (?P<NAME>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<OP>[+\-*/^()])
      | (?P<COMMA>,)
    """,
    re.VERBOSE,
)


def _tokenize(expr: str):
    tokens = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if not m or m.end() == pos:
            raise ValueError(f"Unexpected character {expr[pos]!r} in expression: {expr}")
        pos = m.end()
        if m.lastgroup == "NUMBER":
            tokens.append(("NUMBER", float(m.group())))
        elif m.lastgroup == "NAME":
            tokens.append(("NAME", m.group()))
        elif m.lastgroup == "OP":
            tokens.append(("OP", m.group()))
        elif m.lastgroup == "COMMA":
            tokens.append(("COMMA", ","))
        # whitespace: skip
    tokens.append(("EOF", None))
    return tokens


# ---- safe numeric helpers ----------------------------------------------

def _apply_func(name: str, values) -> float:
    try:
        return float(_FUNC_IMPL[name](*values))
    except (ValueError, OverflowError, ZeroDivisionError, TypeError):
        return NAN


def _safe_div(a: float, b: float) -> float:
    try:
        return a / b
    except ZeroDivisionError:
        return NAN


def _safe_pow(base: float, exp: float) -> float:
    try:
        r = base ** exp
    except (ValueError, ZeroDivisionError, OverflowError):
        return NAN
    return NAN if isinstance(r, complex) else r


# ---- recursive-descent parser -> callable(x) ---------------------------

class _Parser:
    def __init__(self, expr: str):
        self.expr = expr
        self.tokens = _tokenize(expr)
        self.i = 0

    def _peek(self):
        return self.tokens[self.i]

    def _advance(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def _error(self, msg):
        raise ValueError(f"{msg} in expression: {self.expr}")

    @staticmethod
    def _starts_factor(tok) -> bool:
        kind, value = tok
        return kind in ("NUMBER", "NAME") or tok == ("OP", "(")

    def parse(self) -> Callable[[float], float]:
        fn = self._parse_add()
        if self._peek()[0] != "EOF":
            self._error(f"Unexpected token {self._peek()[1]!r}")
        return fn

    def _parse_add(self):
        node = self._parse_mul()
        while self._peek() in (("OP", "+"), ("OP", "-")):
            op = self._advance()[1]
            rhs = self._parse_mul()
            if op == "+":
                node = (lambda a, b: lambda x: a(x) + b(x))(node, rhs)
            else:
                node = (lambda a, b: lambda x: a(x) - b(x))(node, rhs)
        return node

    def _parse_mul(self):
        node = self._parse_unary()
        while True:
            tok = self._peek()
            if tok in (("OP", "*"), ("OP", "/")):
                op = self._advance()[1]
                rhs = self._parse_unary()
                if op == "*":
                    node = (lambda a, b: lambda x: a(x) * b(x))(node, rhs)
                else:
                    node = (lambda a, b: lambda x: _safe_div(a(x), b(x)))(node, rhs)
            elif self._starts_factor(tok):  # implicit multiplication (e.g. 2pi, 3x, (x+1)(x-1))
                rhs = self._parse_unary()
                node = (lambda a, b: lambda x: a(x) * b(x))(node, rhs)
            else:
                break
        return node

    def _parse_unary(self):
        if self._peek() == ("OP", "-"):
            self._advance()
            operand = self._parse_unary()
            return (lambda a: lambda x: -a(x))(operand)
        if self._peek() == ("OP", "+"):
            self._advance()
            return self._parse_unary()
        return self._parse_power()

    def _parse_power(self):
        base = self._parse_atom()
        if self._peek() == ("OP", "^"):
            self._advance()
            exponent = self._parse_unary()  # right-associative, exponent may be signed
            return (lambda a, b: lambda x: _safe_pow(a(x), b(x)))(base, exponent)
        return base

    def _parse_atom(self):
        kind, value = self._advance()
        if kind == "NUMBER":
            return (lambda v: lambda x: v)(value)
        if kind == "NAME":
            if value in _FUNC_IMPL:
                if self._peek() != ("OP", "("):
                    self._error(f"Expected '(' after function {value!r}")
                self._advance()
                args = [self._parse_add()]
                while self._peek() == ("COMMA", ","):
                    self._advance()
                    args.append(self._parse_add())
                if self._peek() != ("OP", ")"):
                    self._error("Expected ')'")
                self._advance()
                return (lambda name, fs: lambda x: _apply_func(name, [f(x) for f in fs]))(value, args)
            if value == "x":
                return lambda x: x
            if value in _CONSTS:
                return (lambda v: lambda x: v)(_CONSTS[value])
            self._error(f"Unknown name {value!r}")
        if (kind, value) == ("OP", "("):
            node = self._parse_add()
            if self._peek() != ("OP", ")"):
                self._error("Expected ')'")
            self._advance()
            return node
        self._error(f"Unexpected token {value!r}")


def parse_expression(expr: str) -> Callable[[float], float]:
    """Compiles a math expression in ``x`` into a callable f(x) -> float.

    The returned callable yields NaN wherever the function is undefined
    (e.g. ln of a negative number), which visualizers render as a gap.
    """
    if not expr or not expr.strip():
        raise ValueError("Empty expression")
    return _Parser(expr).parse()


# ---- MathFunction ------------------------------------------------------

class MathFunction:
    """A function f(x) defined by one or more term expressions that are summed."""

    def __init__(self, terms: List[str], name: str = None, time_based: bool = False):
        self.terms = [t.strip() for t in terms if t.strip()]
        if not self.terms:
            raise ValueError("A MathFunction needs at least one term")
        self._funcs = [parse_expression(t) for t in self.terms]
        self.name = name
        # True when x is seconds-since-epoch from a timestamped spreadsheet, so
        # visualizers show x as a formatted time instead of a raw number.
        self.time_based = time_based

    def evaluate(self, x: float) -> float:
        # Plain sum so that a NaN from an out-of-domain term propagates to a gap.
        return sum(f(x) for f in self._funcs)

    def __call__(self, x: float) -> float:
        return self.evaluate(x)

    def expression(self) -> str:
        parts = [self.terms[0]]
        for term in self.terms[1:]:
            if term.startswith("-"):
                parts.append(" - " + term[1:].strip())
            else:
                parts.append(" + " + term)
        return "".join(parts)

    def __str__(self):
        return f"f(x) = {self.expression()}"

    @classmethod
    def from_expression(cls, expr: str, name: str = None, time_based: bool = False) -> "MathFunction":
        return cls([expr], name=name, time_based=time_based)

    @classmethod
    def from_combined(cls, expr: str, load_function=None, name: str = None) -> "MathFunction":
        """Builds a function from an expression that may reference other functions
        as [name]. Each [name] is expanded to that function's expression, and the
        result is split into additive terms (one per line). load_function(name)
        must return a MathFunction (only needed if the expression uses [name]).

        If any referenced function is time_based, the result is too, so the
        timestamp x-axis flag flows through [name] combinations."""
        seen_time_based = [False]

        def tracking_loader(name_):
            fn = load_function(name_)
            if getattr(fn, "time_based", False):
                seen_time_based[0] = True
            return fn

        loader = tracking_loader if load_function is not None else None
        combined = expand_references(expr, loader)
        parse_expression(combined)  # validate up front for a clear error
        return cls(split_terms(combined), name=name, time_based=seen_time_based[0])

    @classmethod
    def from_file(cls, path) -> "MathFunction":
        path = Path(path)
        terms = []
        time_based = False
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("#"):
                    if "time_based:" in line.lower():
                        time_based = "true" in line.lower().split("time_based:", 1)[1]
                    continue
                terms.append(line)
        if not terms:
            raise ValueError(f"No function terms found in {path}")
        # Validate each term parses, with a line-aware error message.
        for term in terms:
            try:
                parse_expression(term)
            except ValueError as e:
                raise ValueError(f"In {path.name}: {e}") from e
        return cls(terms, name=path.stem, time_based=time_based)

    def save(self, path, header: str = None) -> None:
        path = Path(path)
        with open(path, "w") as f:
            if header:
                for line in header.splitlines():
                    f.write(f"# {line}\n")
            if self.time_based:
                f.write("# time_based: true\n")
            f.write(f"# f(x) = sum of the terms below ({len(self.terms)} term(s))\n")
            for term in self.terms:
                f.write(term + "\n")


# ---- combining functions ([name] references) ---------------------------

_REF_RE = re.compile(r"\[([^\[\]]+)\]")


def expand_references(expr: str, load_function=None) -> str:
    """Replaces each ``[name]`` in expr with the parenthesized expression of that
    function. ``load_function(name)`` must return a MathFunction."""
    def repl(match):
        if load_function is None:
            raise ValueError("function references [..] are not allowed here")
        name = match.group(1).strip()
        fn = load_function(name)
        return "(" + fn.expression() + ")"
    return _REF_RE.sub(repl, expr)


def _value_end(ch: str) -> bool:
    """True if ch can end a value, so a following +/- is a binary operator."""
    return ch.isalnum() or ch in ").]"


def _raw_split(expr: str):
    """Splits at top-level '+'/'-' operators, keeping each operator with its term.
    Respects parentheses and does not split inside scientific notation (2.4e-6)."""
    terms = []
    depth = 0
    cur = ""
    prev = prev2 = ""
    for ch in expr:
        if ch in "([":
            depth += 1
            cur += ch
        elif ch in ")]":
            depth -= 1
            cur += ch
        elif (
            ch in "+-"
            and depth == 0
            and _value_end(prev)
            and not (prev in "eE" and (prev2.isdigit() or prev2 == "."))
        ):
            if cur.strip():
                terms.append(cur)
            cur = ch
        else:
            cur += ch
        if not ch.isspace():
            prev2 = prev
            prev = ch
    if cur.strip():
        terms.append(cur)
    return terms


def _strip_wrapping_parens(t: str) -> str:
    """If t is fully enclosed in one matching paren pair, return the inside."""
    if not (t.startswith("(") and t.endswith(")")):
        return t
    depth = 0
    for i, ch in enumerate(t):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return t[1:-1].strip() if i == len(t) - 1 else t
    return t


def split_terms(expr: str):
    """Splits an expression into additive terms (one per .mfunc line), flattening
    parenthesized sums so that e.g. (a+b)+(c) becomes [a, b, c]."""
    result = []
    for raw in _raw_split(expr):
        t = raw.strip()
        if t.startswith("+"):
            t = t[1:].strip()
        if not t:
            continue
        stripped = _strip_wrapping_parens(t)
        if stripped != t:
            result.extend(split_terms(stripped))
        else:
            result.append(t)
    return result or ["0"]
