"""
Chronopolis - a desktop front end for the City Rhythms toolkit.

"Chronopolis" = chronos (time / rhythm) + polis (city): the app measures the
rhythm of human activity across cities and how it synchronizes.

Two sections:
  * Complete Analysis - pick two spreadsheets and run the whole pipeline
    (regression -> remove shift & Hilbert -> complex -> oscillator; both ->
    synchronization r(t) -> visualization) with one button.
  * Individual Tasks  - pick one toolkit task; its input fields appear; run it.

Every task (and the Complete Analysis section) has a Flags text box. For the
tasks that render video (the three Visualize tasks and Complete Analysis):
    -o        open the finished video automatically
    -p        render a fast, low-resolution preview (720p default; -p = 360p)
    -hd       render at 1080p instead of the 720p default
    -s        draw a segment from the origin to the moving point
              (Visualize Complex / Oscillator only)
    -n=NAME   name the output instead of the auto-generated name
Complete Analysis additionally accepts:
    -k        also keep each city's intermediate .mfunc/.cfunc/.oscillator
    -h=N      use N harmonics instead of the automatic best guess
Those tasks also have an Output path - the single folder every output goes into
(the rendered video and, for Complete Analysis, the .mfunc and any kept
intermediate files). Blank means the current folder's "out". Manim's temporary
build files are tucked into a hidden .manim_cache there so the folder stays
clean. Flags and output paths are remembered per task/section - kept in memory
and written to a preferences file (chronopolis_prefs.json) so they persist across
restarts. Input files are never saved.

File paths can be typed, chosen with Browse, or drag-and-dropped onto a field
(needs the optional tkinterdnd2 package; without it, use Browse).

The interface is intentionally unstyled: plain Tk widgets, basic layout only.

Run:  python chronopolis.py    (Manim + ffmpeg are needed for the visualizers)
"""

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import core

# Optional cross-platform file drag-and-drop (macOS/Windows/Linux) via
# tkinterdnd2. If it's unavailable the app still works - you just use Browse.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except Exception:
    DND_FILES = None
    TkinterDnD = None
    DND_AVAILABLE = False

PREFS_PATH = Path(__file__).with_name("chronopolis_prefs.json")
DEFAULT_OUTPUT = str(Path.cwd() / "out")


def _load_version():
    """App version from the plain-text VERSION file (single source of truth).
    VERSION lives in the repo root while this code lives in root/src, so check
    both the script's own folder and its parent. Falls back to a constant if the
    file is missing (e.g. a bundle)."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "VERSION", here.parent / "VERSION"):
        try:
            return candidate.read_text().strip()
        except OSError:
            continue
    return "1.0.0"


VERSION = _load_version()

# Spreadsheet / file dialog filters.
SPREADSHEET_TYPES = [("Spreadsheets", "*.csv *.xlsx *.xlsm"), ("All files", "*.*")]


def _parse_harmonics(text):
    text = (text or "").strip()
    if not text:
        return None  # auto (best guess)
    try:
        return int(text)
    except ValueError:
        raise ValueError("harmonics must be a whole number (or blank for automatic)")


# Task registry. Each task: input field specs and a runner run(values, opts).
# `values` maps field key -> string; `opts` carries the parsed flags/export
# (open, test, hd, segment, name, export). Non-visualize tasks ignore `opts`.
#
# field spec = (key, label, kind, extra)
#   kind "file"      -> entry + Browse   (extra = file dialog filters or None)
#   kind "text"      -> single-line entry (extra = hint appended to the label)
#   kind "multiline" -> multi-line text box
#   kind "choice"    -> option menu       (extra = list of choices)
TASKS = [
    {
        "key": "pointseries",
        "label": "Point Series from Spreadsheet",
        "fields": [
            ("spreadsheet", "Spreadsheet", "file", SPREADSHEET_TYPES),
            ("out", "Output .pseries (blank = auto)", "text", None),
        ],
        "visualize": False,
        "run": lambda v, opts: core.task_pointseries(v["spreadsheet"], v["out"]),
    },
    {
        "key": "regression",
        "label": "Regression (fit sinusoids)",
        "fields": [
            ("data", "Data file (.csv/.xlsx/.xlsm/.pseries)", "file", None),
            ("harmonics", "Harmonics (blank = best guess)", "text", None),
            ("out", "Output .mfunc (blank = auto)", "text", None),
        ],
        "visualize": False,
        "run": lambda v, opts: core.task_regression(
            v["data"], _parse_harmonics(v["harmonics"]), v["out"]),
    },
    {
        "key": "transform",
        "label": "Transform Function",
        "fields": [
            ("mfunc", "Input .mfunc", "file", None),
            ("transform", "Transform", "choice", ["hilbert", "remove_shift"]),
            ("out", "Output .mfunc (blank = auto)", "text", None),
        ],
        "visualize": False,
        "run": lambda v, opts: core.task_transform(v["mfunc"], v["transform"], v["out"]),
    },
    {
        "key": "create_function",
        "label": "Create Function",
        "fields": [
            ("expr", "f(x) =   (use [name] to reference a .mfunc)", "text", None),
            ("out", "Output .mfunc (blank = auto)", "text", None),
        ],
        "visualize": False,
        "run": lambda v, opts: core.task_create_function(v["expr"], v["out"]),
    },
    {
        "key": "create_complex",
        "label": "Create Complex Function",
        "fields": [
            ("real", "Real part  real(x) =", "text", None),
            ("imag", "Imag part  imag(x) =", "text", None),
            ("out", "Output .cfunc (blank = auto)", "text", None),
        ],
        "visualize": False,
        "run": lambda v, opts: core.task_create_complex(v["real"], v["imag"], v["out"]),
    },
    {
        "key": "oscillator",
        "label": "Complex -> Oscillator",
        "fields": [
            ("cfunc", "Input .cfunc", "file", None),
            ("out", "Output .oscillator (blank = auto)", "text", None),
        ],
        "visualize": False,
        "run": lambda v, opts: core.task_oscillator(v["cfunc"], v["out"]),
    },
    {
        "key": "sync",
        "label": "Oscillator Synchronization",
        "fields": [
            ("osc1", "Oscillator 1 (.oscillator)", "file", None),
            ("osc2", "Oscillator 2 (.oscillator)", "file", None),
            ("out", "Output .mfunc (blank = auto)", "text", None),
        ],
        "visualize": False,
        "run": lambda v, opts: core.task_sync(v["osc1"], v["osc2"], v["out"]),
    },
    {
        "key": "visualize_functions",
        "label": "Visualize Function(s)",
        "fields": [
            ("items", "Items - one per line (.mfunc / .pseries path or an "
                      "expression in x)", "multiline", None),
        ],
        "visualize": True,
        "run": lambda v, opts: core.task_visualize_functions(
            v["items"], opts["open"], opts["test"], opts["hd"], opts["output"], opts["name"]),
    },
    {
        "key": "visualize_complex",
        "label": "Visualize Complex Function",
        "fields": [
            ("cfunc", "Input .cfunc", "file", None),
        ],
        "visualize": True,
        "run": lambda v, opts: core.task_visualize_complex(
            v["cfunc"], opts["open"], opts["test"], opts["hd"], opts["segment"],
            opts["output"], opts["name"]),
    },
    {
        "key": "visualize_oscillator",
        "label": "Visualize Oscillator",
        "fields": [
            ("oscillator", "Input .oscillator", "file", None),
        ],
        "visualize": True,
        "run": lambda v, opts: core.task_visualize_oscillator(
            v["oscillator"], opts["open"], opts["test"], opts["hd"], opts["segment"],
            opts["output"], opts["name"]),
    },
]

# Flag hints shown under the Flags box.
VIS_FLAGS_HINT = ("Flags: -o open when done   -p low-res preview   -hd 1080p   "
                  "-s origin segment [complex/oscillator]   -n=NAME output name")
CA_FLAGS_HINT = ("Flags: -o open when done   -p low-res preview   -hd 1080p   "
                 "-k keep intermediates   -h=N harmonics   -n=NAME output name")


def _parse_flags(text):
    """Splits a flags string into (boolean_flags set, key_value dict). Tokens
    like -o/-p go in the set; tokens like -h=8 or -n=sync go in the dict."""
    booleans, values = set(), {}
    for token in (text or "").split():
        if "=" in token:
            key, _, value = token.partition("=")
            values[key] = value
        else:
            booleans.add(token)
    return booleans, values

TASK_BY_KEY = {t["key"]: t for t in TASKS}
TASK_BY_LABEL = {t["label"]: t for t in TASKS}

# One-line, in-app explanations shown when a task is selected, so users can work
# without reading the README.
TASK_DESCRIPTIONS = {
    "pointseries":
        "Reads a two-column x,y spreadsheet and saves it as a .pseries point set. "
        "The x column may be numbers or timestamps (e.g. 2025-06-01); y must be numeric.",
    "regression":
        "Fits a sum of sinusoids (a Fourier series) to x,y data and saves a .mfunc. "
        "Leave Harmonics blank to auto-pick the best count, or set it yourself.",
    "transform":
        "Transforms a sinusoidal .mfunc: 'hilbert' phase-shifts every component by "
        "-90 degrees (the imaginary part); 'remove_shift' removes the vertical offset "
        "so it is centered on 0 (the real part).",
    "create_function":
        "Builds a function from a math expression in x (e.g. sin(x)+x). Reference a "
        "saved function with [name] to combine them. Saves a .mfunc.",
    "create_complex":
        "Builds a complex function f(x) = real(x) + i*imag(x) from two expressions "
        "and saves a .cfunc.",
    "oscillator":
        "Turns a .cfunc into an oscillator - its phase theta(t) = atan2(imag, real). "
        "Saves a .oscillator.",
    "sync":
        "Computes the Kuramoto synchronization r(t) of two oscillators "
        "(1 = fully in sync, 0 = anti-phase) and saves it as a .mfunc.",
    "visualize_functions":
        "Renders an animation of one or more functions and/or point series on one "
        "plot. Enter one item per line: a .mfunc/.pseries path or an expression in x.",
    "visualize_complex":
        "Animates a complex function f(x) = real + i*imag as a moving point tracing "
        "its path through the complex plane.",
    "visualize_oscillator":
        "Animates an oscillator's phasor e^(i*theta(t)) spinning on the unit circle.",
}


class PlaceholderEntry(tk.Entry):
    """A plain entry that shows grey placeholder text when empty. value()
    returns "" while the placeholder is showing."""

    def __init__(self, master, placeholder="", width=50):
        super().__init__(master, width=width)
        self.placeholder = placeholder
        self._showing = False
        self.bind("<FocusIn>", self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)
        self._show_placeholder()

    def _on_focus_in(self, _e=None):
        if self._showing:
            self.delete(0, "end")
            self.config(fg="black")
            self._showing = False

    def _on_focus_out(self, _e=None):
        if not self.get():
            self._show_placeholder()

    def _show_placeholder(self):
        self.delete(0, "end")
        self.config(fg="grey")
        self.insert(0, self.placeholder)
        self._showing = True

    def value(self):
        return "" if self._showing else self.get()

    def set_value(self, text):
        self.delete(0, "end")
        if text:
            self.config(fg="black")
            self.insert(0, text)
            self._showing = False
        else:
            self._show_placeholder()


class ChronopolisApp:
    def __init__(self, root):
        self.root = root
        root.title(f"Chronopolis {VERSION}")

        self.prefs = self._load_prefs()
        self.current_section = None
        self.current_task = None
        self.field_getters = {}     # field key -> callable returning str
        self.flags_entry = None
        self.export_entry = None
        self.run_buttons = []
        self._busy = False
        # Worker threads talk to the UI only through this queue, which the main
        # thread drains on a timer (Tkinter is not thread-safe).
        self._queue = queue.Queue()

        # Header + a short "what is this" so the app is self-explanatory.
        tk.Label(root, text=f"Chronopolis {VERSION} - the rhythm of cities").pack(anchor="w")
        tk.Label(root, justify="left", wraplength=680, text=(
            "Measures how the rhythm of human activity synchronizes between two regions. "
            "Use Complete Analysis for the whole pipeline in one click, or Individual "
            "Tasks for step-by-step control. Progress and any errors appear in Status "
            "below. Flag options are listed under each Flags box.")).pack(anchor="w")

        # Section switcher.
        bar = tk.Frame(root)
        bar.pack(anchor="w", fill="x")
        tk.Button(bar, text="Complete Analysis",
                  command=lambda: self._show_section("complete")).pack(side="left")
        tk.Button(bar, text="Individual Tasks",
                  command=lambda: self._show_section("tasks")).pack(side="left")

        # Section bodies (only one packed at a time).
        self.complete_frame = tk.Frame(root)
        self.tasks_frame = tk.Frame(root)
        self._build_complete_section()
        self._build_tasks_section()

        # Shared status log.
        tk.Label(root, text="Status:").pack(anchor="w")
        self.status = tk.Text(root, height=12, width=90)
        self.status.pack(fill="both", expand=True)

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_queue)  # start the main-thread poller

        # Restore the last-used section/task.
        last_task = self.prefs.get("last_task")
        if last_task in TASK_BY_KEY:
            self.task_var.set(TASK_BY_KEY[last_task]["label"])
            self._build_task(last_task)
        self._show_section(self.prefs.get("last_section", "complete"), initial=True)

    # ---- preferences ----------------------------------------------------

    def _load_prefs(self):
        default = {"complete_flags": "", "complete_media": "", "tasks": {},
                   "last_section": "complete", "last_task": TASKS[0]["key"],
                   "rendered_once": False}
        try:
            with open(PREFS_PATH) as f:
                data = json.load(f)
            if isinstance(data, dict):
                default.update(data)
                default.setdefault("tasks", {})
        except (OSError, ValueError):
            pass
        return default

    def _save_prefs(self):
        try:
            with open(PREFS_PATH, "w") as f:
                json.dump(self.prefs, f, indent=2)
        except OSError:
            pass

    def _capture(self):
        """Reads the persisted fields (flags, export paths) of whatever is on
        screen into prefs, then writes prefs to disk. Input files are not saved."""
        self.prefs["last_section"] = self.current_section
        if self.current_section == "complete":
            self.prefs["complete_flags"] = self.ca_flags.get()
            self.prefs["complete_media"] = self.ca_media.value()
        elif self.current_section == "tasks" and self.current_task:
            self.prefs["last_task"] = self.current_task
            entry = self.prefs["tasks"].setdefault(self.current_task, {})
            if self.flags_entry is not None:
                entry["flags"] = self.flags_entry.get()
            if self.export_entry is not None:
                entry["export"] = self.export_entry.value()
        self._save_prefs()

    # ---- complete-analysis section -------------------------------------

    def _build_complete_section(self):
        f = self.complete_frame
        tk.Label(f, justify="left", wraplength=640, text=(
            "Complete Analysis runs the whole pipeline on two spreadsheets in one step: "
            "each is fit with sinusoidal regression, turned into a phase oscillator "
            "(remove-shift + Hilbert -> complex -> phase), and the two are compared with "
            "the Kuramoto order parameter r(t) (1 = in sync, 0 = anti-phase). It writes "
            "sync.mfunc and renders a video of r(t). Pick two x,y spreadsheets (x may be "
            "timestamps) and press Run.")).pack(anchor="w", pady=(0, 4))

        self.ca_sp1 = self._file_row(f, "Spreadsheet 1:", SPREADSHEET_TYPES)
        self.ca_sp2 = self._file_row(f, "Spreadsheet 2:", SPREADSHEET_TYPES)

        # Output video folder (persisted).
        vrow = tk.Frame(f)
        vrow.pack(anchor="w", fill="x")
        tk.Label(vrow, text="Output path:").pack(side="left")
        self.ca_media = PlaceholderEntry(vrow, placeholder=DEFAULT_OUTPUT, width=50)
        self.ca_media.pack(side="left")
        self.ca_media.set_value(self.prefs.get("complete_media", ""))

        row = tk.Frame(f)
        row.pack(anchor="w", fill="x")
        tk.Label(row, text="Flags:").pack(side="left")
        self.ca_flags = tk.Entry(row, width=50)
        self.ca_flags.pack(side="left")
        self.ca_flags.insert(0, self.prefs.get("complete_flags", ""))
        tk.Label(f, text=CA_FLAGS_HINT).pack(anchor="w")

        btn = tk.Button(f, text="Run Complete Analysis", command=self._run_complete)
        btn.pack(anchor="w")
        self.run_buttons.append(btn)

    def _file_row(self, parent, label, filetypes):
        """A label + entry + Browse button row (with file drag-and-drop). Returns
        the entry."""
        row = tk.Frame(parent)
        row.pack(anchor="w", fill="x")
        tk.Label(row, text=label).pack(side="left")
        entry = tk.Entry(row, width=50)
        entry.pack(side="left")
        tk.Button(row, text="Browse",
                  command=lambda: self._browse(entry, filetypes)).pack(side="left")
        self._enable_file_drop(entry)
        return entry

    def _browse(self, entry, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes or [("All files", "*.*")])
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)

    def _enable_file_drop(self, entry):
        """Lets the user drop a file onto `entry` to fill in its path. No-op when
        tkinterdnd2 is unavailable. Cross-platform (macOS/Windows/Linux)."""
        if not DND_AVAILABLE:
            return

        def on_drop(event):
            paths = self.root.tk.splitlist(event.data)  # handles spaces/braces
            if paths:
                entry.delete(0, "end")
                entry.insert(0, paths[0])  # single-file slot: take the first
            return event.action

        entry.drop_target_register(DND_FILES)
        entry.dnd_bind("<<Drop>>", on_drop)

    def _enable_multiline_drop(self, text):
        """Lets the user drop one or more files onto a multiline box, appending
        each path as its own line. No-op when tkinterdnd2 is unavailable."""
        if not DND_AVAILABLE:
            return

        def on_drop(event):
            for path in self.root.tk.splitlist(event.data):
                text.insert("end", path + "\n")
            return event.action

        text.drop_target_register(DND_FILES)
        text.dnd_bind("<<Drop>>", on_drop)

    # ---- individual-tasks section --------------------------------------

    def _build_tasks_section(self):
        f = self.tasks_frame
        row = tk.Frame(f)
        row.pack(anchor="w", fill="x")
        tk.Label(row, text="Task:").pack(side="left")
        self.task_var = tk.StringVar(value=TASKS[0]["label"])
        tk.OptionMenu(row, self.task_var, *[t["label"] for t in TASKS],
                      command=self._on_task_selected).pack(side="left")

        # Rebuilt per task: input fields, flags, export, run button.
        self.task_body = tk.Frame(f)
        self.task_body.pack(anchor="w", fill="x")

    def _on_task_selected(self, label):
        self._capture()  # save the task we are leaving
        self._build_task(TASK_BY_LABEL[label]["key"])

    def _build_task(self, task_key):
        for child in self.task_body.winfo_children():
            child.destroy()
        self.field_getters = {}
        self.flags_entry = None
        self.export_entry = None
        self.current_task = task_key
        task = TASK_BY_KEY[task_key]

        # What this task does (so users don't have to read the docs).
        desc = TASK_DESCRIPTIONS.get(task_key, "")
        if desc:
            tk.Label(self.task_body, text=desc, justify="left",
                     wraplength=620).pack(anchor="w", pady=(0, 4))

        for key, label, kind, extra in task["fields"]:
            self.field_getters[key] = self._build_field(self.task_body, key, label, kind, extra)

        # Flags (persisted).
        prefs = self.prefs["tasks"].get(task_key, {})
        row = tk.Frame(self.task_body)
        row.pack(anchor="w", fill="x")
        tk.Label(row, text="Flags:").pack(side="left")
        self.flags_entry = tk.Entry(row, width=50)
        self.flags_entry.pack(side="left")
        self.flags_entry.insert(0, prefs.get("flags", ""))

        # Output path (persisted) - visualize tasks only.
        if task["visualize"]:
            erow = tk.Frame(self.task_body)
            erow.pack(anchor="w", fill="x")
            tk.Label(erow, text="Output path:").pack(side="left")
            self.export_entry = PlaceholderEntry(erow, placeholder=DEFAULT_OUTPUT, width=50)
            self.export_entry.pack(side="left")
            self.export_entry.set_value(prefs.get("export", ""))
            tk.Label(self.task_body, text=VIS_FLAGS_HINT).pack(anchor="w")

        btn = tk.Button(self.task_body, text="Run", command=self._run_task)
        btn.pack(anchor="w")
        self.run_buttons.append(btn)

    def _build_field(self, parent, key, label, kind, extra):
        """Builds one input widget and returns a getter callable for its value."""
        if kind == "multiline":
            tk.Label(parent, text=label + ":").pack(anchor="w")
            text = tk.Text(parent, height=5, width=70)
            text.pack(anchor="w", fill="x")
            self._enable_multiline_drop(text)  # drop files to append their paths
            return lambda: text.get("1.0", "end-1c").strip()

        row = tk.Frame(parent)
        row.pack(anchor="w", fill="x")
        tk.Label(row, text=label + ":").pack(side="left")

        if kind == "choice":
            var = tk.StringVar(value=extra[0])
            tk.OptionMenu(row, var, *extra).pack(side="left")
            return var.get

        entry = tk.Entry(row, width=50)
        entry.pack(side="left")
        if kind == "file":
            tk.Button(row, text="Browse",
                      command=lambda: self._browse(entry, extra)).pack(side="left")
            self._enable_file_drop(entry)  # drop a file to fill in its path
        return entry.get

    # ---- section switching ---------------------------------------------

    def _show_section(self, section, initial=False):
        if not initial and section == self.current_section:
            return
        if not initial:
            self._capture()  # save the section we are leaving
        self.complete_frame.pack_forget()
        self.tasks_frame.pack_forget()
        if section == "complete":
            self.complete_frame.pack(anchor="w", fill="x")
        else:
            self.tasks_frame.pack(anchor="w", fill="x")
        self.current_section = section

    # ---- running (in a background thread) ------------------------------

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in self.run_buttons:
            try:
                b.config(state=state)
            except tk.TclError:
                pass  # button was destroyed on a task rebuild

    def _post(self, text):
        """Thread-safe: hand a status line to the main thread via the queue."""
        self._queue.put(("log", text))

    def _poll_queue(self):
        """Runs on the main thread: drain worker messages and apply them."""
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    self._append(payload)
                elif kind == "busy":
                    self._set_busy(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _append(self, text):
        self.status.insert("end", text + "\n")
        self.status.see("end")

    def _note_first_render(self):
        """The first video render on a machine triggers a one-time Manim/Pango
        font-cache build that can take a few minutes. Warn about it once so the
        wait is expected; later renders are fast."""
        if self.prefs.get("rendered_once"):
            return
        self._append("First video render on this machine: Manim is building its "
                     "font cache - this can take a few minutes. Later renders are fast.")
        self.prefs["rendered_once"] = True
        self._save_prefs()

    def _run_task(self):
        if self._busy:
            return
        self._capture()
        task = TASK_BY_KEY[self.current_task]
        try:
            values = {k: g() for k, g in self.field_getters.items()}
        except Exception as e:  # a getter should not fail, but be safe
            self._append(f"ERROR: {e}")
            return
        flags, kv = _parse_flags(self.flags_entry.get() if self.flags_entry else "")
        opts = {
            "open": "-o" in flags,
            "test": "-p" in flags,
            "hd": "-hd" in flags,
            "segment": "-s" in flags,
            "name": kv.get("-n") or None,
            "output": self.export_entry.value() if self.export_entry else "",
        }
        self._append(f"--- Running: {task['label']} ---")
        if task["visualize"]:
            self._note_first_render()
        self._start(lambda: task["run"](values, opts))

    def _run_complete(self):
        if self._busy:
            return
        self._capture()
        sp1 = self.ca_sp1.get().strip()
        sp2 = self.ca_sp2.get().strip()
        if not sp1 or not sp2:
            self._append("ERROR: choose both spreadsheets first.")
            return
        flags, kv = _parse_flags(self.ca_flags.get())
        harmonics = None
        if "-h" in kv:
            try:
                harmonics = int(kv["-h"])
            except ValueError:
                self._append("ERROR: -h must be a whole number, e.g. -h=8")
                return
        output = self.ca_media.value()
        name = kv.get("-n") or "sync"
        open_video, test, hd, keep = ("-o" in flags, "-p" in flags,
                                      "-hd" in flags, "-k" in flags)
        self._append("--- Running: Complete Analysis ---")
        self._note_first_render()
        self._start(lambda: core.complete_analysis(
            sp1, sp2, output_dir=output, open_video=open_video, test=test,
            hd=hd, keep=keep, harmonics=harmonics, name=name, log=self._post))

    def _start(self, work):
        """Runs `work()` on a worker thread; reports its result/errors. All UI
        updates go through the queue so only the main thread touches Tk."""
        self._set_busy(True)

        def worker():
            try:
                result = work()
                if result:
                    self._queue.put(("log", str(result)))
            except Exception as e:
                self._queue.put(("log", f"ERROR: {e}"))
            finally:
                self._queue.put(("busy", False))

        threading.Thread(target=worker, daemon=True).start()

    # ---- shutdown -------------------------------------------------------

    def _on_close(self):
        self._capture()
        self.root.destroy()


def main():
    # A TkinterDnD root enables file drag-and-drop; fall back to plain Tk if the
    # optional dependency is missing (the app then works without drag-and-drop).
    root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
    ChronopolisApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
