"""
Complex functions f(x) = real(x) + i*imag(x), stored in ``.cfunc`` files.

A ``.cfunc`` file has a ``#real`` section and a ``#imag`` section, each a list of
term expressions (like a ``.mfunc``) that sum to that part::

    # complex function f(x) = real + i*imag
    #real
    5sin(2pi/5(x-4))
    #imag
    3cos(x)

The phase angle theta(x) = atan2(imag, real) is what an oscillator uses.
"""

from pathlib import Path

from mfunc import MathFunction


class ComplexFunction:
    def __init__(self, real: MathFunction, imag: MathFunction, name: str = None,
                 time_based: bool = None):
        self.real = real
        self.imag = imag
        self.name = name
        # A complex function is time_based when either of its parts is (x is
        # seconds-since-epoch); default to that unless explicitly overridden.
        if time_based is None:
            time_based = getattr(real, "time_based", False) or getattr(imag, "time_based", False)
        self.time_based = time_based

    @classmethod
    def from_parts(cls, real_expr, imag_expr, load_function=None, name=None) -> "ComplexFunction":
        """Builds from two expressions, each of which may use [name] references."""
        return cls(
            MathFunction.from_combined(real_expr, load_function),
            MathFunction.from_combined(imag_expr, load_function),
            name=name,
        )

    @classmethod
    def from_file(cls, path) -> "ComplexFunction":
        path = Path(path)
        sections = {"real": [], "imag": []}
        current = None
        time_based = False
        with open(path, "r") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                low = s.lower().replace(" ", "")
                if low in ("#real",):
                    current = "real"
                    continue
                if low in ("#imag", "#imaginary"):
                    current = "imag"
                    continue
                if s.startswith("#"):
                    if "time_based:" in low:
                        time_based = "true" in low.split("time_based:", 1)[1]
                    continue
                if current is None:
                    raise ValueError(f"{path.name}: term before a #real/#imag section: {s!r}")
                sections[current].append(s)
        if not sections["real"] or not sections["imag"]:
            raise ValueError(f"{path.name} must have a #real and a #imag section with terms")
        return cls(MathFunction(sections["real"]), MathFunction(sections["imag"]),
                   name=path.stem, time_based=time_based)

    def save(self, path, header: str = None) -> None:
        path = Path(path)
        with open(path, "w") as f:
            if header:
                for line in header.splitlines():
                    f.write(f"# {line}\n")
            if self.time_based:
                f.write("# time_based: true\n")
            f.write("# complex function f(x) = real + i*imag\n")
            f.write("#real\n")
            for term in self.real.terms:
                f.write(term + "\n")
            f.write("#imag\n")
            for term in self.imag.terms:
                f.write(term + "\n")

    def evaluate(self, x: float) -> complex:
        return complex(self.real.evaluate(x), self.imag.evaluate(x))

    def phase_expression(self) -> str:
        """The oscillator phase theta(x) = atan2(imag, real) as an expression."""
        return f"atan2(({self.imag.expression()}),({self.real.expression()}))"

    def __str__(self):
        return f"f(x) = ({self.real.expression()}) + i*({self.imag.expression()})"
