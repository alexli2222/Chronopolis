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
tasks that render video (the three Visualize tasks and Complete Analysis) the
flags are:
    -o   open the finished video automatically
    -p   render a fast, low-resolution preview instead of full quality
Those tasks also have an output/export video path (the media folder to render
into; blank = the current folder's media). Flags and export paths are remembered
per task/section - kept in memory and written to a preferences file
(chronopolis_prefs.json) so they persist across restarts. Input files are never
saved.

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
DEFAULT_MEDIA = str(Path.cwd() / "media")


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


# Task registry. Each task: input field specs and a runner that receives the
# field values (dict), the open_video flag (-o), the test flag (-p), and the
# export path. Non-visualize tasks ignore the last three.
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
        "run": lambda v, o, t, e: core.task_pointseries(v["spreadsheet"], v["out"]),
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
        "run": lambda v, o, t, e: core.task_regression(
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
        "run": lambda v, o, t, e: core.task_transform(v["mfunc"], v["transform"], v["out"]),
    },
    {
        "key": "create_function",
        "label": "Create Function",
        "fields": [
            ("expr", "f(x) =   (use [name] to reference a .mfunc)", "text", None),
            ("out", "Output .mfunc (blank = auto)", "text", None),
        ],
        "visualize": False,
        "run": lambda v, o, t, e: core.task_create_function(v["expr"], v["out"]),
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
        "run": lambda v, o, t, e: core.task_create_complex(v["real"], v["imag"], v["out"]),
    },
    {
        "key": "oscillator",
        "label": "Complex -> Oscillator",
        "fields": [
            ("cfunc", "Input .cfunc", "file", None),
            ("out", "Output .oscillator (blank = auto)", "text", None),
        ],
        "visualize": False,
        "run": lambda v, o, t, e: core.task_oscillator(v["cfunc"], v["out"]),
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
        "run": lambda v, o, t, e: core.task_sync(v["osc1"], v["osc2"], v["out"]),
    },
    {
        "key": "visualize_functions",
        "label": "Visualize Function(s)",
        "fields": [
            ("items", "Items - one per line (.mfunc / .pseries path or an "
                      "expression in x)", "multiline", None),
        ],
        "visualize": True,
        "run": lambda v, o, t, e: core.task_visualize_functions(v["items"], o, t, e),
    },
    {
        "key": "visualize_complex",
        "label": "Visualize Complex Function",
        "fields": [
            ("cfunc", "Input .cfunc", "file", None),
        ],
        "visualize": True,
        "run": lambda v, o, t, e: core.task_visualize_complex(v["cfunc"], o, t, e),
    },
    {
        "key": "visualize_oscillator",
        "label": "Visualize Oscillator",
        "fields": [
            ("oscillator", "Input .oscillator", "file", None),
        ],
        "visualize": True,
        "run": lambda v, o, t, e: core.task_visualize_oscillator(v["oscillator"], o, t, e),
    },
]

# Flags shown/accepted for visualize tasks and Complete Analysis.
FLAGS_HINT = "(-o = open the video when done;  -p = fast low-res preview render)"

TASK_BY_KEY = {t["key"]: t for t in TASKS}
TASK_BY_LABEL = {t["label"]: t for t in TASKS}


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

        # Header.
        tk.Label(root, text=f"Chronopolis {VERSION} - the rhythm of cities").pack(anchor="w")

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
                   "last_section": "complete", "last_task": TASKS[0]["key"]}
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
        tk.Label(f, text="Complete Analysis: two spreadsheets -> synchronization "
                         "r(t) -> visualization").pack(anchor="w")

        self.ca_sp1 = self._file_row(f, "Spreadsheet 1:", SPREADSHEET_TYPES)
        self.ca_sp2 = self._file_row(f, "Spreadsheet 2:", SPREADSHEET_TYPES)

        # Output video folder (persisted).
        vrow = tk.Frame(f)
        vrow.pack(anchor="w", fill="x")
        tk.Label(vrow, text="Output video path:").pack(side="left")
        self.ca_media = PlaceholderEntry(vrow, placeholder=DEFAULT_MEDIA, width=50)
        self.ca_media.pack(side="left")
        self.ca_media.set_value(self.prefs.get("complete_media", ""))

        row = tk.Frame(f)
        row.pack(anchor="w", fill="x")
        tk.Label(row, text="Flags:").pack(side="left")
        self.ca_flags = tk.Entry(row, width=50)
        self.ca_flags.pack(side="left")
        self.ca_flags.insert(0, self.prefs.get("complete_flags", ""))
        tk.Label(f, text=FLAGS_HINT).pack(anchor="w")

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

        # Export path (persisted) - visualize tasks only.
        if task["visualize"]:
            erow = tk.Frame(self.task_body)
            erow.pack(anchor="w", fill="x")
            tk.Label(erow, text="Export path:").pack(side="left")
            self.export_entry = PlaceholderEntry(erow, placeholder=DEFAULT_MEDIA, width=50)
            self.export_entry.pack(side="left")
            self.export_entry.set_value(prefs.get("export", ""))
            tk.Label(self.task_body, text=FLAGS_HINT).pack(anchor="w")

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
        tokens = (self.flags_entry.get() if self.flags_entry else "").split()
        open_video = "-o" in tokens
        test = "-p" in tokens
        export = self.export_entry.value() if self.export_entry else ""
        self._append(f"--- Running: {task['label']} ---")
        self._start(lambda: task["run"](values, open_video, test, export))

    def _run_complete(self):
        if self._busy:
            return
        self._capture()
        sp1 = self.ca_sp1.get().strip()
        sp2 = self.ca_sp2.get().strip()
        if not sp1 or not sp2:
            self._append("ERROR: choose both spreadsheets first.")
            return
        tokens = self.ca_flags.get().split()
        open_video = "-o" in tokens
        test = "-p" in tokens
        media = self.ca_media.value()
        self._append("--- Running: Complete Analysis ---")
        self._start(lambda: core.complete_analysis(sp1, sp2, out_dir=".",
                                                    media_dir=media, open_video=open_video,
                                                    test=test, log=self._post))

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
