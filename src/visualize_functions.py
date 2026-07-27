"""
Visualizes any number of functions and/or point series on a shared xy-plane
using Manim.

Each item you enter can be:
  * a path to a .mfunc file (e.g. an exported regression fit),
  * a path to a .pseries file (data points), drawn as dots, or
  * a raw expression in x (e.g. "sin(x)+x", "ln(x+5)-3x").

Run standalone:
    python visualize_functions.py
or call visualize_functions.run() from another script (the Chronopolis app and
core.py do this).

A video is rendered showing everything plotted together, color-coded with a
legend, and opens automatically when done (look under ./media/videos).
"""

import math
import re
from pathlib import Path

import paths
from mfunc import MathFunction
from pointseries import PointSeries
from sinusoid import Sinusoid

# Populated by run()/render() before the scene is rendered.
FUNCTIONS = []       # list of (label, MathFunction | PointSeries)
X_RANGE = (0.0, 100.0)
Y_RANGE = None       # (y_min, y_max); when None the scene auto-fits
X_TIME_BASED = False  # x is seconds-since-epoch -> label it as formatted time
SAMPLES = 1500       # points sampled across the x-range when plotting/measuring
READOUT_SWEEP_SECONDS = 6.0  # length of the dy/dx sweep in the function plot

# Test mode: a fast preview that keeps the same duration and span but renders
# far fewer frames (lower fps) and pixels - like dropping a video's frame rate.
TEST_MODE = False
TEST_FRAME_RATE = 8       # updates per second (vs 30) - the main "less dense" lever
TEST_SAMPLES = 250        # coarser sampling of the static curves


def _effective_samples() -> int:
    return TEST_SAMPLES if TEST_MODE else SAMPLES

# Populated by render_complex() before the complex scene is rendered.
REAL_FUNC = None
IMAG_FUNC = None
COMPLEX_X_RANGE = (0.0, 1.0)
COMPLEX_DURATION = 10.0   # seconds for the full sweep
COMPLEX_SEGMENT = False   # draw a segment from the origin to each point?


def load_item(text: str):
    """Turns user input into (label, obj) where obj is a MathFunction (from a
    .mfunc file or a typed expression) or a PointSeries (from a .pseries file).

    A bare name like "function" resolves to function.mfunc or function.pseries
    (you're asked which if both exist); an explicit extension always works;
    anything that isn't a file is treated as an expression in x."""
    text = text.strip()
    found = paths.find_existing(text, (".mfunc", ".pseries"))
    if found is not None:
        if found.suffix.lower() == ".pseries":
            return found.stem, PointSeries.from_file(found)
        fn = MathFunction.from_file(found)
        return fn.name or found.stem, fn
    if Path(text).suffix.lower() in paths.DATA_EXTS:
        raise ValueError(f"no .mfunc or .pseries file found for '{text}'")
    return text, MathFunction.from_expression(text)


def _finite(v) -> bool:
    return v is not None and not (math.isnan(v) or math.isinf(v))


def _items_time_based(items) -> bool:
    """True when any plotted item carries the timestamp (seconds-since-epoch)
    flag, so the shared x-axis should be labeled as time."""
    return any(getattr(obj, "time_based", False) for _, obj in items)


def _fmt_x(v, x_min=None, x_max=None) -> str:
    """Formats an x value for display: a nice UTC time string when the x-axis is
    time-based (from timestamped data), otherwise the plain numeric format."""
    if X_TIME_BASED:
        from pointseries import format_epoch
        span = (x_max - x_min) if (x_min is not None and x_max is not None) else None
        return format_epoch(v, span)
    return _fmt(v)


def suggest_x_bounds(items):
    """Educated x-bounds.

    If any point series is present, use the actual span of its data - that's
    where the points live and where a fitted curve lines up with them. Otherwise
    a sum of sinusoids is periodic, so the whole waveform shows in one
    fundamental period = 2*pi / (smallest angular frequency) (this also handles
    regression fits whose real domain sits at a huge epoch-second offset). With
    neither, fall back to [0, 100]."""
    ps_xs = []
    for _, obj in items:
        if isinstance(obj, PointSeries) and obj.xs:
            ps_xs.append(min(obj.xs))
            ps_xs.append(max(obj.xs))
    if ps_xs:
        return min(ps_xs), max(ps_xs)

    min_freq = math.inf
    for _, obj in items:
        if not isinstance(obj, MathFunction):
            continue
        for term in obj.terms:
            try:
                s = Sinusoid.from_notation(term)
            except ValueError:
                continue  # not a sinusoid term (e.g. ln(x+5)-3x)
            w = abs(s.angular_frequency)
            if w > 0:
                min_freq = min(min_freq, w)
        # Also scan for sinusoids embedded inside a composite expression
        # (e.g. an oscillator phase or a sync r(t) built from regression fits),
        # so those get the fundamental period of their underlying waves.
        embedded = _min_embedded_frequency(obj.expression())
        if embedded is not None:
            min_freq = min(min_freq, embedded)
    if min_freq == math.inf:
        return 0.0, 100.0
    return 0.0, 2 * math.pi / min_freq


# Matches sin/cos with a coefficient wrapping x, e.g. "sin(2.44e-06(x+262444))".
_EMBEDDED_SINUSOID_RE = re.compile(r"(?:sin|cos)\(([^()]+)\(x", re.IGNORECASE)


def _min_embedded_frequency(expr: str):
    """Smallest |angular frequency| of any A*sin/cos(b(x-h)) buried in expr."""
    from sinusoid import _parse_coefficient

    min_w = math.inf
    for m in _EMBEDDED_SINUSOID_RE.finditer(expr):
        try:
            w = abs(_parse_coefficient(m.group(1)))
        except (ValueError, ZeroDivisionError):
            continue
        if w > 0:
            min_w = min(min_w, w)
    return None if min_w == math.inf else min_w


def suggest_y_bounds(items, x_min: float, x_max: float, samples: int = SAMPLES):
    """Educated y-bounds: the lowest and highest values reached over
    [x_min, x_max] by the functions and point series, padded by a small margin."""
    step = (x_max - x_min) / samples
    lo, hi = math.inf, -math.inf
    for _, obj in items:
        if isinstance(obj, PointSeries):
            for x, y in zip(obj.xs, obj.ys):
                if x_min <= x <= x_max and _finite(y):
                    lo = min(lo, y)
                    hi = max(hi, y)
        else:
            for i in range(samples + 1):
                x = x_min + i * step
                try:
                    y = obj.evaluate(x)
                except Exception:
                    continue
                if _finite(y):
                    lo = min(lo, y)
                    hi = max(hi, y)
    if lo == math.inf:  # nothing finite to measure
        return -1.0, 1.0
    span = hi - lo
    pad = 0.1 * span if span > 1e-9 else 1.0
    return lo - pad, hi + pad


def _complex_bounds(real_fn, imag_fn, x_min, x_max, samples=SAMPLES):
    """Re/Im axis ranges from the values re(x), im(x) reach over the sweep.
    The origin is always included (it's the complex 0 and the segment anchor)."""
    step = (x_max - x_min) / samples
    re_lo = re_hi = im_lo = im_hi = 0.0  # seed with the origin
    for i in range(samples + 1):
        t = x_min + i * step
        try:
            re, im = real_fn.evaluate(t), imag_fn.evaluate(t)
        except Exception:
            continue
        if _finite(re) and _finite(im):
            re_lo, re_hi = min(re_lo, re), max(re_hi, re)
            im_lo, im_hi = min(im_lo, im), max(im_hi, im)
    re_pad = 0.1 * (re_hi - re_lo) or 1.0
    im_pad = 0.1 * (im_hi - im_lo) or 1.0
    return (re_lo - re_pad, re_hi + re_pad), (im_lo - im_pad, im_hi + im_pad)


def suggest_complex_speed(real_fn, imag_fn, x_min, x_max, samples=400):
    """Suggests a playback speed (x-units per second) for the complex animation.

    Factors: the x-range length, and how much the trajectory winds (counted as
    direction reversals in re(x) and im(x)). A busier path gets a longer -
    slower - run so the detail is watchable; a simple loop plays quickly."""
    span = x_max - x_min
    step = span / samples
    reversals = 0
    last_re = last_im = None
    re_dir = im_dir = 0
    for i in range(samples + 1):
        t = x_min + i * step
        try:
            re, im = real_fn.evaluate(t), imag_fn.evaluate(t)
        except Exception:
            continue
        if not (_finite(re) and _finite(im)):
            continue
        if last_re is not None:
            s = (re > last_re) - (re < last_re)
            if s:
                if re_dir and s != re_dir:
                    reversals += 1
                re_dir = s
            s2 = (im > last_im) - (im < last_im)
            if s2:
                if im_dir and s2 != im_dir:
                    reversals += 1
                im_dir = s2
        last_re, last_im = re, im
    duration = min(30.0, max(6.0, 3.0 + 1.5 * reversals))
    speed = span / duration if duration > 0 else span
    return speed, duration


def _nice_step(span: float) -> float:
    if span <= 0:
        return 1.0
    raw = span / 8.0
    magnitude = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if mult * magnitude >= raw:
            return mult * magnitude
    return magnitude * 10


def render(functions=None, x_range=None, y_range=None, preview=True, test=False,
           hd=False, output_name=None, **config_overrides):
    """Renders the given functions. Imports manim lazily so the rest of the
    toolkit works without it installed. If y_range is None the scene auto-fits.
    test=True does a fast, low-resolution/low-frame-rate preview; hd=True renders
    at 1080p (vs the 720p default). output_name names the exported video file
    (kept distinct so exports don't overwrite)."""
    global FUNCTIONS, X_RANGE, Y_RANGE, X_TIME_BASED, TEST_MODE
    if functions is not None:
        FUNCTIONS = functions
    if x_range is not None:
        X_RANGE = x_range
    Y_RANGE = y_range
    X_TIME_BASED = _items_time_based(FUNCTIONS)
    TEST_MODE = test

    try:
        from manim import config
    except ImportError:
        print("This visualizer requires the 'manim' package. Install it with:")
        print("  pip install manim   (Manim also needs ffmpeg on your PATH)")
        return

    _apply_config(config, _media_name(output_name, "functions"), preview, test, hd)
    for key, value in config_overrides.items():
        setattr(config, key, value)
    _FunctionPlotScene().render()


def render_complex(real_fn, imag_fn, x_range, duration, segment, preview=True, test=False,
                   hd=False, output_name=None, kind="complex", **config_overrides):
    """Renders f(x) = real_fn(x) + i*imag_fn(x) as an animated trajectory in the
    complex plane. `duration` is the sweep length in seconds; `segment` draws a
    line from the origin to the moving point instead of a bare dot.
    test=True does a fast, low-resolution/low-frame-rate preview. output_name
    names the exported video file (kept distinct so exports don't overwrite)."""
    global REAL_FUNC, IMAG_FUNC, COMPLEX_X_RANGE, COMPLEX_DURATION, COMPLEX_SEGMENT, TEST_MODE
    REAL_FUNC, IMAG_FUNC = real_fn, imag_fn
    COMPLEX_X_RANGE = x_range
    COMPLEX_DURATION = duration  # unchanged in test mode - same length, fewer frames
    COMPLEX_SEGMENT = segment
    TEST_MODE = test

    try:
        from manim import config
    except ImportError:
        print("This visualizer requires the 'manim' package. Install it with:")
        print("  pip install manim   (Manim also needs ffmpeg on your PATH)")
        return

    _apply_config(config, _media_name(output_name, kind), preview, test, hd)
    for key, value in config_overrides.items():
        setattr(config, key, value)
    _ComplexPlotScene().render()


def _apply_config(config, output_file, preview, test, hd=False):
    # Test renders get a "_test" suffix so quick previews never overwrite a
    # full-quality export of the same subject.
    config.output_file = f"{output_file}_test" if test else output_file
    config.preview = preview
    if test:
        # Same duration/span, but far fewer frames and pixels -> a fast preview.
        # (test wins over hd: a preview is about speed, not resolution.)
        config.pixel_width, config.pixel_height = 640, 360
        config.frame_rate = TEST_FRAME_RATE
    elif hd:
        config.pixel_width, config.pixel_height = 1920, 1080
        config.frame_rate = 30
    else:
        config.pixel_width, config.pixel_height = 1280, 720
        config.frame_rate = 30


def _media_name(output_name, kind: str) -> str:
    """A filesystem-safe video name so exports are easy to tell apart.

    `output_name` is a subject label (e.g. the item names, or an oscillator's
    stem); `kind` is the visualizer ('functions', 'complex', 'oscillator').
    Result looks like 'beijing_nyc_functions' or 'beijing_oscillator'."""
    base = re.sub(r"[^A-Za-z0-9]+", "_", (output_name or "").strip()).strip("_")
    base = base[:48]
    return f"{base}_{kind}" if base else f"{kind}_plot"


def run():
    """Interactive entry point: collect items, then render them."""
    print("=== Function Visualizer ===")
    print("Plot any number of functions and/or point series on one xy-plane.")
    print("Enter a .mfunc path, a .pseries path, or an expression in x")
    print("(e.g. sin(x)+x, ln(x+5)-3x). .pseries files are drawn as data points.")
    print("Press Enter on an empty line when you are done adding items.")
    print()

    functions = []
    while True:
        prompt = f"Item #{len(functions) + 1} (blank to finish): "
        text = input(prompt).strip()
        if not text:
            if functions:
                break
            print("Enter at least one item.")
            continue
        try:
            functions.append(load_item(text))
            print(f"  added: {functions[-1][0]}")
        except (OSError, ValueError) as e:
            print(f"  could not load item: {e}")

    time_based = _items_time_based(functions)
    sx_min, sx_max = suggest_x_bounds(functions)
    print(f"Suggested x-range (one full period of the waveform): "
          f"[{_round_bound(sx_min)}, {_round_bound(sx_max)}]{_time_hint(time_based, sx_min, sx_max)}")
    x_min = _ask_float("x-min", _round_bound(sx_min))
    x_max = _ask_float("x-max", _round_bound(sx_max))
    if x_max <= x_min:
        x_max = x_min + 1.0

    sy_min, sy_max = suggest_y_bounds(functions, x_min, x_max)
    sy_min, sy_max = _round_bound(sy_min), _round_bound(sy_max)
    print(f"Suggested y-bounds from the functions' range over x: [{sy_min}, {sy_max}]")
    y_min = _ask_float("y-min", sy_min)
    y_max = _ask_float("y-max", sy_max)
    if y_max <= y_min:
        y_max = y_min + 1.0

    test = _ask_yes_no("Test mode (fast preview: fewer frames, same length)?", default=False)

    print(f"Rendering {len(functions)} function(s) over x in [{x_min}, {x_max}], "
          f"y in [{y_min}, {y_max}]{' [TEST MODE]' if test else ''} ...")
    output_name = "_".join(lbl for lbl, _ in functions)
    render(functions=functions, x_range=(x_min, x_max), y_range=(y_min, y_max),
           test=test, output_name=output_name)
    print("Done. If the video didn't open automatically, check the 'media/videos' folder.")


def run_complex():
    """Interactive entry point for the complex-plane animation:
    f(x) = real(x) + i*imag(x), swept over x as time. Accepts a .cfunc file or
    real/imag parts entered by hand."""
    import paths

    print("=== Complex Visualizer ===")
    print("Animates f(x) = real(x) + i*imag(x) as a trajectory in the complex plane")
    print("(x is the parameter / time).")
    print()

    typed = input("Load a .cfunc file (path), or blank to enter parts by hand: ").strip()
    if typed:
        found = paths.find_existing(typed, (".cfunc",))
        if found is None:
            print(f"No .cfunc file found for '{typed}'")
            return
        from cfunc import ComplexFunction
        try:
            cf = ComplexFunction.from_file(found)
        except (OSError, ValueError) as e:
            print(f"Could not read file: {e}")
            return
        real_fn, imag_fn = cf.real, cf.imag
        subject = found.stem
        print(f"  loaded f(x) = ({cf.real.expression()}) + i*({cf.imag.expression()})")
    else:
        subject = None
        print("Enter each part as an expression or [name] references, e.g. [fn1].")

        def resolver(name):
            f = paths.find_existing(name, (".mfunc",))
            if f is None:
                raise ValueError(f"referenced function not found: {name} (looked for {name}.mfunc)")
            return MathFunction.from_file(f)

        real_fn = _ask_function("Real part      real(x)", resolver)
        if real_fn is None:
            return
        imag_fn = _ask_function("Imaginary part imag(x)", resolver)
        if imag_fn is None:
            return

    _finish_complex(real_fn, imag_fn, subject=subject, kind="complex")


def run_oscillator():
    """Interactive entry point for visualizing an oscillator as its phasor
    e^(i*theta(t)) = cos(theta) + i*sin(theta) spinning on the unit circle."""
    import paths

    print("=== Oscillator Visualizer ===")
    print("Animates the phasor e^(i*theta(t)) = cos(theta) + i*sin(theta) of an")
    print("oscillator, spinning on the unit circle (x is the parameter / time).")
    print()

    typed = input("Oscillator .oscillator file (blank to cancel): ").strip()
    if not typed:
        return
    found = paths.find_existing(typed, (".oscillator",))
    if found is None:
        print(f"No .oscillator file found for '{typed}'")
        return
    try:
        theta = MathFunction.from_file(found)
    except (OSError, ValueError) as e:
        print(f"Could not read file: {e}")
        return

    th = theta.expression()
    real_fn = MathFunction.from_expression(f"cos(({th}))", time_based=theta.time_based)
    imag_fn = MathFunction.from_expression(f"sin(({th}))", time_based=theta.time_based)
    print(f"  phasor from theta(t) in {found.name}")
    _finish_complex(real_fn, imag_fn, default_segment=True, subject=found.stem, kind="oscillator")


def _finish_complex(real_fn, imag_fn, default_segment=False, subject=None, kind="complex"):
    """Shared tail for the complex/oscillator visualizers: prompts for x-range,
    the origin segment, speed and test mode, then renders. `subject`/`kind` name
    the exported video (e.g. 'beijing_oscillator') so exports stay distinct."""
    time_based = getattr(real_fn, "time_based", False) or getattr(imag_fn, "time_based", False)
    sx_min, sx_max = suggest_x_bounds([("re", real_fn), ("im", imag_fn)])
    print(f"Suggested x-range (one full period): [{_round_bound(sx_min)}, {_round_bound(sx_max)}]"
          f"{_time_hint(time_based, sx_min, sx_max)}")
    x_min = _ask_float("x-min", _round_bound(sx_min))
    x_max = _ask_float("x-max", _round_bound(sx_max))
    if x_max <= x_min:
        x_max = x_min + 1.0

    segment = _ask_yes_no("Draw a segment from the origin to each point?", default=default_segment)

    speed, dur = suggest_complex_speed(real_fn, imag_fn, x_min, x_max)
    print(f"Suggested speed: {_round_bound(speed)} x-units/sec (~{dur:.0f}s for the whole sweep),")
    print("based on the x-range length and how much the trajectory winds.")
    speed = _ask_float("speed (x-units/sec)", _round_bound(speed))
    if speed <= 0:
        speed = (x_max - x_min) / dur
    duration = max(1.0, min(120.0, (x_max - x_min) / speed))

    test = _ask_yes_no("Test mode (fast preview: fewer frames, same length)?", default=False)

    print(f"Rendering complex trajectory over x in [{x_min}, {x_max}] "
          f"at {_round_bound(speed)} x-units/sec (~{duration:.0f}s)"
          f"{' [TEST MODE]' if test else ''} ...")
    render_complex(real_fn, imag_fn, (x_min, x_max), duration, segment, test=test,
                   output_name=subject, kind=kind)
    print("Done. If the video didn't open automatically, check the 'media/videos' folder.")


def _ask_function(label, resolver):
    """Prompts for a function (expression or [name] references); None to cancel."""
    while True:
        text = input(f"{label} = ").strip()
        if not text:
            return None
        try:
            return MathFunction.from_combined(text, resolver, name=label)
        except (OSError, ValueError) as e:
            print(f"  invalid: {e}")


def _ask_yes_no(question, default=False):
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{question} [{hint}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  please answer y or n.")


def _ask_float(label: str, default: float) -> float:
    while True:
        raw = input(f"{label} (Enter for {default}): ").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            print("  please enter a number.")


def _round_bound(v: float) -> float:
    """Rounds a suggested bound to a tidy value for display/use."""
    return round(v) if abs(v) >= 1000 else round(v, 3)


def _time_hint(time_based: bool, lo: float, hi: float) -> str:
    """A trailing '(= <date> to <date>)' note for time-based x, else ''.
    x is still entered as seconds-since-epoch; this just makes it human-readable."""
    if not time_based:
        return ""
    from pointseries import format_epoch
    return f"  (= {format_epoch(lo, hi - lo)} to {format_epoch(hi, hi - lo)})"


def _fmt(v) -> str:
    """Formats a readout value; NaN/inf/None show as a dash."""
    if v is None:
        return "--"
    try:
        if math.isnan(v) or math.isinf(v):
            return "--"
    except TypeError:
        return "--"
    av = abs(v)
    if av != 0 and (av < 1e-3 or av >= 1e5):
        return f"{v:.2e}"
    return f"{v:.3f}"


def _ratio(num, den):
    """num/den, or None when the denominator is ~0 (undefined slope)."""
    return num / den if abs(den) > 1e-12 else None


def _wrap_angle(a: float) -> float:
    """Wraps an angle difference into (-pi, pi] for the shortest step."""
    return (a + math.pi) % (2 * math.pi) - math.pi


def _make_glyph_readout(labels, values_fn, font_size=16, corner=None, buff=0.3, colors=None):
    """A live numeric readout that is fast to animate.

    Building a manim Text every frame is expensive (Pango renders ~50 ms each),
    which dominated render time. Instead we render each label once and each
    digit glyph once, then compose the changing value strings per frame from
    cheap copies of those pre-rendered glyphs.

    `labels` are the static left-hand strings; `values_fn()` returns the list of
    value strings (same length) for the current frame. Returns (labels_mobject,
    animated_values_mobject) - add both to the scene.
    """
    from manim import Text, VGroup, always_redraw, RIGHT, UP, DOWN, LEFT, UL, WHITE

    corner = UL if corner is None else corner
    colors = colors or [WHITE] * len(labels)

    label_mobs = VGroup(*[Text(lbl, font_size=font_size, color=colors[i])
                          for i, lbl in enumerate(labels)])
    label_mobs.arrange(DOWN, aligned_edge=LEFT, buff=0.2).to_corner(corner, buff=buff)

    # Static anchor (value start x, baseline y) for each label - computed once.
    anchors = [(m.get_right()[0] + 0.1, m.get_bottom()[1]) for m in label_mobs]

    # Glyph bank + metrics, rendered once. width/center/bottom let us place a copy
    # with a cheap shift() (no per-frame bounding-box calls).
    bank, metric = {}, {}
    for c in "0123456789.-e+:":  # ':' supports time-of-day readouts (HH:MM:SS)
        g = Text(c, font_size=font_size)
        bank[c] = g
        metric[c] = (g.width, g.get_center()[0], g.get_center()[1], g.get_bottom()[1])
    gap = 0.03
    space_width = 0.12  # width to advance for a space (no glyph rendered)

    def values_group():
        strings = values_fn()
        vg = VGroup()
        for i, s in enumerate(strings):
            x, base_y = anchors[i]
            color = colors[i]
            for ch in s:
                if ch == " ":
                    x += space_width
                    continue
                g = bank.get(ch)
                if g is None:
                    continue
                w, gcx, gcy, gby = metric[ch]
                copy = g.copy().set_color(color)
                copy.shift(RIGHT * (x + w / 2 - gcx) + UP * (base_y - gby))
                vg.add(copy)
                x += w + gap
        return vg

    return label_mobs, always_redraw(values_group)


def _build_scene_class():
    """Defines the Manim Scene lazily (only when manim is importable)."""
    from manim import (
        Scene, Axes, VMobject, VGroup, Line, Dot, Text, Create, Write, FadeIn,
        ValueTracker, always_redraw, linear, config,
        BLUE, RED, GREEN, YELLOW, PURPLE, ORANGE, TEAL, PINK, GOLD, MAROON, WHITE,
        RIGHT, DOWN, LEFT, UP, UL, UR,
    )

    palette = [BLUE, RED, GREEN, YELLOW, PURPLE, ORANGE, TEAL, PINK, GOLD, MAROON]

    class FunctionPlotScene(Scene):
        def construct(self):
            items = FUNCTIONS
            x_min, x_max = X_RANGE
            samples = _effective_samples()
            step_x = (x_max - x_min) / samples

            y_min, y_max = self._resolve_y_range(items, x_min, x_max, samples, step_x)

            axes = Axes(
                x_range=[x_min, x_max, _nice_step(x_max - x_min)],
                y_range=[y_min, y_max, _nice_step(y_max - y_min)],
                x_length=11,
                y_length=6,
                tips=True,
            )
            x_axis_name = "time" if X_TIME_BASED else "x"
            x_label = Text(x_axis_name, font_size=24).next_to(axes.x_axis.get_end(), UP, buff=0.15)
            y_label = Text("y", font_size=24).next_to(axes.y_axis.get_end(), RIGHT, buff=0.15)
            # Scale marks at the ends of the x-axis, plus a ranges line, so the
            # span is readable at a glance. For time-based x these read as dates.
            x_lo = Text(_fmt_x(x_min, x_min, x_max), font_size=15).next_to(
                axes.x_axis.get_start(), DOWN, buff=0.15)
            x_hi = Text(_fmt_x(x_max, x_min, x_max), font_size=15).next_to(
                axes.x_axis.get_end(), DOWN, buff=0.15)
            units = Text(f"{x_axis_name} in [{_fmt_x(x_min, x_min, x_max)}, {_fmt_x(x_max, x_min, x_max)}]"
                         f"     y in [{_fmt(y_min)}, {_fmt(y_max)}]",
                         font_size=16).to_edge(DOWN, buff=0.12)
            self.play(Create(axes), Write(x_label), Write(y_label))
            self.add(x_lo, x_hi, units)

            graphs = []
            legend = VGroup()
            for i, (label, obj) in enumerate(items):
                color = palette[i % len(palette)]
                if isinstance(obj, PointSeries):
                    group = VGroup()
                    for x, y in zip(obj.xs, obj.ys):
                        if _finite(y) and x_min <= x <= x_max and y_min <= y <= y_max:
                            group.add(Dot(axes.coords_to_point(x, y), radius=0.04, color=color))
                    swatch = Dot(radius=0.06, color=color)
                else:
                    group = VGroup()
                    run = []
                    for j in range(samples + 1):
                        x = x_min + j * step_x
                        try:
                            y = obj.evaluate(x)
                        except Exception:
                            y = float("nan")
                        if _finite(y) and y_min <= y <= y_max:
                            run.append(axes.coords_to_point(x, y))
                        else:
                            if len(run) >= 2:
                                group.add(VMobject(stroke_color=color, stroke_width=3).set_points_as_corners(run))
                            run = []
                    if len(run) >= 2:
                        group.add(VMobject(stroke_color=color, stroke_width=3).set_points_as_corners(run))
                    swatch = Line(color=color, stroke_width=4).set_length(0.5)
                graphs.append(group)

                shown = label if len(label) <= 28 else label[:25] + "..."
                entry = VGroup(swatch, Text(shown, font_size=20)).arrange(RIGHT, buff=0.15)
                legend.add(entry)

            legend.arrange(DOWN, aligned_edge=LEFT, buff=0.15).to_corner(UR, buff=0.4)

            self.play(*[Create(g) for g in graphs], run_time=3)
            self.play(FadeIn(legend))

            # Sweep a cursor across x and read out dy/dx for each function.
            func_items = [(lbl, obj, palette[i % len(palette)])
                          for i, (lbl, obj) in enumerate(items)
                          if not isinstance(obj, PointSeries)]
            if not func_items:
                self.wait(2)
                return

            fps = config.frame_rate or 30
            dur = READOUT_SWEEP_SECONDS
            h = (x_max - x_min) / (dur * fps)  # per-frame step = the "last point"
            tracker = ValueTracker(x_min)

            def cursor():
                x = tracker.get_value()
                return Line(axes.coords_to_point(x, y_min), axes.coords_to_point(x, y_max),
                            stroke_color=WHITE, stroke_width=1).set_opacity(0.4)

            def dots():
                x = tracker.get_value()
                group = VGroup()
                for _, obj, color in func_items:
                    try:
                        y = obj.evaluate(x)
                    except Exception:
                        y = float("nan")
                    if _finite(y) and y_min <= y <= y_max:
                        group.add(Dot(axes.coords_to_point(x, y), radius=0.05, color=color))
                return group

            def values():
                x = tracker.get_value()
                out = [_fmt_x(x, x_min, x_max)]
                for _, obj, _color in func_items:
                    try:
                        y1, y0 = obj.evaluate(x), obj.evaluate(x - h)
                        y = y1 if _finite(y1) else None
                        dydx = (y1 - y0) / h if (_finite(y1) and _finite(y0)) else None
                    except Exception:
                        y = dydx = None
                    out.append(_fmt(y))       # y at the point
                    out.append(_fmt(dydx))    # slope at the point
                return out

            # Readout shows x (time), then y and dy/dx for each function.
            readout_labels = [f"{x_axis_name} ="]
            readout_colors = [WHITE]
            for lbl, _obj, color in func_items:
                name = lbl if len(lbl) <= 14 else lbl[:11] + "..."
                readout_labels.append(f"{name} y =")
                readout_colors.append(color)
                readout_labels.append(f"{name} dy/dx =")
                readout_colors.append(color)
            label_mob, value_mob = _make_glyph_readout(
                readout_labels, values, font_size=18, colors=readout_colors)

            self.add(always_redraw(cursor), always_redraw(dots), label_mob, value_mob)
            self.play(tracker.animate.set_value(x_max), run_time=dur, rate_func=linear)
            self.wait(1)

        @staticmethod
        def _resolve_y_range(items, x_min, x_max, samples, step_x):
            if Y_RANGE is not None:
                return Y_RANGE
            # Fallback auto-fit (robust percentile) when no bounds were given.
            all_y = []
            for _, obj in items:
                if isinstance(obj, PointSeries):
                    for x, y in zip(obj.xs, obj.ys):
                        if x_min <= x <= x_max and _finite(y):
                            all_y.append(y)
                else:
                    for j in range(samples + 1):
                        x = x_min + j * step_x
                        try:
                            y = obj.evaluate(x)
                        except Exception:
                            continue
                        if _finite(y):
                            all_y.append(y)
            if all_y:
                all_y.sort()
                lo = all_y[int(0.02 * (len(all_y) - 1))]
                hi = all_y[int(0.98 * (len(all_y) - 1))]
            else:
                lo, hi = -1.0, 1.0
            if hi <= lo:
                hi = lo + 1.0
            pad = (hi - lo) * 0.15
            return lo - pad, hi + pad

    return FunctionPlotScene


# Lazily-resolved scene class; render() populates this.
def _FunctionPlotScene():
    cls = _build_scene_class()
    return cls()


def _build_complex_scene_class():
    """Defines the complex-plane Manim Scene lazily."""
    from manim import (
        Scene, Axes, VGroup, Line, Dot, Text, Create, Write,
        TracedPath, ValueTracker, always_redraw, linear, config,
        YELLOW, BLUE, WHITE, RIGHT, DOWN, LEFT, UP, UL,
    )

    class ComplexPlotScene(Scene):
        def construct(self):
            real_fn, imag_fn = REAL_FUNC, IMAG_FUNC
            x_min, x_max = COMPLEX_X_RANGE
            (re_lo, re_hi), (im_lo, im_hi) = _complex_bounds(
                real_fn, imag_fn, x_min, x_max, samples=_effective_samples())

            # Equal-aspect axes so circles look circular.
            re_span = re_hi - re_lo
            im_span = im_hi - im_lo
            scale = min(11.0 / re_span, 6.0 / im_span)
            axes = Axes(
                x_range=[re_lo, re_hi, _nice_step(re_span)],
                y_range=[im_lo, im_hi, _nice_step(im_span)],
                x_length=re_span * scale,
                y_length=im_span * scale,
                tips=True,
            )
            re_label = Text("Re", font_size=24).next_to(axes.x_axis.get_end(), DOWN, buff=0.2)
            im_label = Text("Im", font_size=24).next_to(axes.y_axis.get_end(), LEFT, buff=0.2)
            self.play(Create(axes), Write(re_label), Write(im_label))

            origin = axes.coords_to_point(0, 0)

            def point_at(t):
                try:
                    re, im = real_fn.evaluate(t), imag_fn.evaluate(t)
                except Exception:
                    re = im = 0.0
                if not (_finite(re) and _finite(im)):
                    re = im = 0.0
                return axes.coords_to_point(re, im)

            tracker = ValueTracker(x_min)

            def indicator():
                p = point_at(tracker.get_value())
                if COMPLEX_SEGMENT:
                    return VGroup(
                        Line(origin, p, color=YELLOW, stroke_width=3),
                        Dot(p, color=YELLOW, radius=0.05),
                    )
                return Dot(p, color=YELLOW, radius=0.07)

            trail = TracedPath(lambda: point_at(tracker.get_value()),
                               stroke_color=BLUE, stroke_width=3)
            moving = always_redraw(indicator)

            # Live readout: coordinates, radius, and deltas/derivatives vs. the
            # previous point (one frame back).
            fps = config.frame_rate or 30
            h = (x_max - x_min) / (COMPLEX_DURATION * fps)

            def state_at(t):
                try:
                    x, y = real_fn.evaluate(t), imag_fn.evaluate(t)
                except Exception:
                    x = y = 0.0
                if not (_finite(x) and _finite(y)):
                    x = y = 0.0
                return x, y, math.hypot(x, y), math.atan2(y, x)

            def values():
                t = tracker.get_value()
                x, y, r, theta = state_at(t)
                x0, y0, r0, th0 = state_at(t - h)
                dx, dy, dr = x - x0, y - y0, r - r0
                dtheta = _wrap_angle(theta - th0)
                ddist = math.hypot(dx, dy)
                return [
                    _fmt(x), _fmt(y), _fmt(r), _fmt(ddist),
                    _fmt(dx), _fmt(dy), _fmt(dr), _fmt(dtheta),
                    _fmt(_ratio(dy, dx)), _fmt(_ratio(dx, dtheta)),
                    _fmt(_ratio(dy, dtheta)), _fmt(_ratio(dr, dtheta)),
                ]

            labels = ["x =", "y =", "r =", "d dist =", "dx =", "dy =", "dr =",
                      "dtheta =", "dy/dx =", "dx/dtheta =", "dy/dtheta =", "dr/dtheta ="]
            label_mob, value_mob = _make_glyph_readout(labels, values, font_size=16)
            self.add(trail, moving, label_mob, value_mob)

            self.play(tracker.animate.set_value(x_max),
                      run_time=COMPLEX_DURATION, rate_func=linear)
            self.wait(1)

    return ComplexPlotScene


def _ComplexPlotScene():
    cls = _build_complex_scene_class()
    return cls()


if __name__ == "__main__":
    run()
