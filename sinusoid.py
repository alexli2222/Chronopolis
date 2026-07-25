"""
A single sinusoid of the form

    f(x) = amplitude * sin( angularFrequency * (x - phaseShift) ) + verticalShift

rendered in / parsed from standard math notation such as ``5sin(2pi/5(x-4))+5``.
Used to format the terms produced by the sinusoidal regression and to
manipulate them (e.g. the Hilbert transform).
"""

import math
import re

# group 1: amplitude              (optional sign/number, incl. scientific)
# group 2: coefficient b          (when written as sin( COEF (x +/- h) ))
# group 3: phase, with coefficient
# group 4: phase, no coefficient  (sin( x +/- h ))
# group 5: trailing vertical shift
_NUM = r"[+-]?\d*\.?\d*(?:[eE][+-]?\d+)?"
_SIGNED = r"[+-]\d*\.?\d+(?:[eE][+-]?\d+)?"
_EXPRESSION_RE = re.compile(
    r"^(" + _NUM + r")sin\("
    r"(?:([^()]+)\(x(" + _SIGNED + r")?\)|x(" + _SIGNED + r")?)"
    r"\)(" + _SIGNED + r")?$",
    re.IGNORECASE,
)


def _parse_signed_or_one(s: str) -> float:
    if s is None or s == "":
        return 1.0
    if s == "-":
        return -1.0
    if s == "+":
        return 1.0
    return float(s)


def _parse_coefficient(raw: str) -> float:
    """Parses a coefficient like '2pi/5', 'pi', '-pi/2', '2.4e-6', or '-'."""
    s = raw.replace("*", "").replace("π", "pi")
    if s in ("-", "+"):
        return -1.0 if s == "-" else 1.0
    idx = s.lower().find("pi")
    if idx < 0:
        if "/" in s:
            num, den = s.split("/")
            return float(num) / float(den)
        return float(s)
    before, after = s[:idx], s[idx + 2:]
    value = _parse_signed_or_one(before) * math.pi
    if after:
        if not after.startswith("/"):
            raise ValueError(f"Cannot parse coefficient: {raw}")
        value /= float(after[1:])
    return value


def _fmt_number(n: float) -> str:
    n = float(n)  # normalize numpy scalars so repr() stays plain
    if n == int(n) and not math.isinf(n):
        return str(int(n))
    return repr(n)


def _fmt_coefficient(b: float) -> str:
    """Renders b as a tidy multiple of pi (e.g. '2pi/5') when it is one, else a number."""
    ratio = b / math.pi
    for d in range(1, 65):
        scaled = ratio * d
        n = round(scaled)
        if n != 0 and abs(scaled - n) < 1e-6:
            g = math.gcd(abs(n), d)
            num, den = n // g, d // g
            out = ""
            if num == -1:
                out = "-"
            elif num != 1:
                out = str(num)
            out += "pi"
            if den != 1:
                out += f"/{den}"
            return out
    return _fmt_number(b)


class Sinusoid:
    def __init__(self, amplitude: float, frequency: float, phase_shift: float, vertical_shift: float):
        self.amplitude = float(amplitude)
        self.angular_frequency = 2 * math.pi * float(frequency)
        self.phase_shift = float(phase_shift)
        self.vertical_shift = float(vertical_shift)

    @property
    def frequency(self) -> float:
        return self.angular_frequency / (2 * math.pi)

    def evaluate(self, x: float) -> float:
        return self.amplitude * math.sin(self.angular_frequency * (x - self.phase_shift)) + self.vertical_shift

    def __call__(self, x: float) -> float:
        return self.evaluate(x)

    @classmethod
    def from_notation(cls, expression: str) -> "Sinusoid":
        expr = re.sub(r"\s+", "", expression)
        m = _EXPRESSION_RE.match(expr)
        if not m:
            raise ValueError(f"Not a sinusoid expression: {expression!r}")
        amplitude = _parse_signed_or_one(m.group(1))
        b_expr = m.group(2)
        phase_with_coef = m.group(3)
        phase_no_coef = m.group(4)
        vshift = m.group(5)
        if b_expr is not None:
            angular = _parse_coefficient(b_expr)
            phase_shift = -float(phase_with_coef) if phase_with_coef else 0.0
        else:
            angular = 1.0
            phase_shift = -float(phase_no_coef) if phase_no_coef else 0.0
        vertical_shift = float(vshift) if vshift else 0.0
        s = cls.__new__(cls)
        s.amplitude = amplitude
        s.angular_frequency = angular
        s.phase_shift = phase_shift
        s.vertical_shift = vertical_shift
        return s

    def __str__(self) -> str:
        amp, b, h, k = self.amplitude, self.angular_frequency, self.phase_shift, self.vertical_shift
        out = ""
        if amp == -1:
            out += "-"
        elif amp != 1:
            out += _fmt_number(amp)
        out += "sin("

        if h == 0:
            phase_term = ""
        elif h > 0:
            phase_term = "-" + _fmt_number(h)
        else:
            phase_term = "+" + _fmt_number(-h)

        if b == 1.0:
            out += "x" + phase_term
        elif b == -1.0:
            out += "-(x" + phase_term + ")"
        else:
            out += _fmt_coefficient(b) + "(x" + phase_term + ")"
        out += ")"

        if k != 0:
            out += ("+" if k > 0 else "-") + _fmt_number(abs(k))
        return out
