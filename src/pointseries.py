"""
Reads a two-column spreadsheet (.csv, .xlsx, or .xlsm) of x,y data points.

The first column is x, the second is y. The x column may be plain numbers or
timestamps; timestamps are converted to seconds-since-epoch so everything
downstream works with plain floats. The y column must be numeric. Unparseable
rows (e.g. a header) are skipped. Only the first worksheet is read for XLSX/XLSM
files.

Accepted timestamp forms (date separators may be '-' or '/'):
    2000-06-01          2000/06/01
    2024-01-15T10:30:00     2024-01-15 10:30:00
    2024-01-15T10:30:00Z    (trailing Z or +hh:mm -> read as that exact zone)

Timezone handling:
  * A timestamp with NO zone is read as wall-clock time (used as written), so
    the same clock reading in different cities lines up - this compares local
    day/night cycles rather than absolute UTC time.
  * A timestamp ending in 'Z' (or carrying a +hh:mm offset) is read as standard
    time in that zone and converted to the true UTC instant. Add 'Z' when your
    timestamps are already in UTC and you want them compared as absolute time.
"""

import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path


class PointSeries:
    def __init__(self, xs, ys, time_based=False):
        if len(xs) != len(ys):
            raise ValueError("x and y must have the same length")
        self.xs = list(xs)
        self.ys = list(ys)
        self.time_based = time_based

    def __len__(self):
        return len(self.xs)

    @classmethod
    def from_file(cls, path) -> "PointSeries":
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return cls._from_csv(path)
        if suffix in (".xlsx", ".xlsm"):
            return cls._from_excel(path)
        if suffix == ".pseries":
            return cls._from_pseries(path)
        raise ValueError(
            f"Unsupported file type (expected .csv, .xlsx, .xlsm, or .pseries): {path}"
        )

    def save(self, path, source: str = None) -> None:
        """Writes this point series as a .pseries file (x,y per line)."""
        path = Path(path)
        with open(path, "w") as f:
            if source:
                f.write(f"# Point series from {source}\n")
            f.write(f"# {len(self.xs)} points\n")
            f.write(f"# time_based: {'true' if self.time_based else 'false'}\n")
            f.write("# columns: x,y\n")
            for x, y in zip(self.xs, self.ys):
                f.write(f"{x},{y}\n")

    # ---- .pseries ------------------------------------------------------

    @classmethod
    def _from_pseries(cls, path: Path) -> "PointSeries":
        xs, ys = [], []
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
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                try:
                    xs.append(float(parts[0].strip()))
                    ys.append(float(parts[1].strip()))
                except ValueError:
                    continue
        return cls(xs, ys, time_based=time_based)

    # ---- CSV -----------------------------------------------------------

    @classmethod
    def _from_csv(cls, path: Path) -> "PointSeries":
        xs, ys = [], []
        state = {"time": False}
        with open(path, "r", newline="") as f:
            for line in f:
                parts = line.split(",")
                if len(parts) < 2:
                    continue
                try:
                    x = _parse_x(parts[0].strip(), state)
                    y = float(parts[1].strip())
                except ValueError:
                    continue  # header or non-data row
                xs.append(x)
                ys.append(y)
        return cls(xs, ys, time_based=state["time"])

    # ---- XLSX / XLSM ---------------------------------------------------

    @classmethod
    def _from_excel(cls, path: Path) -> "PointSeries":
        xs, ys = [], []
        state = {"time": False}
        with zipfile.ZipFile(path) as zf:
            shared = _load_shared_strings(zf)
            with zf.open("xl/worksheets/sheet1.xml") as sheet:
                tree = ET.parse(sheet)
            for row in tree.getroot().iter():
                if _local(row.tag) != "row":
                    continue
                x = y = None
                for cell in row:
                    if _local(cell.tag) != "c":
                        continue
                    col = _column_index(cell.get("r", ""))
                    text = _cell_text(cell, shared)
                    if text is None:
                        continue
                    if col == 0:
                        try:
                            x = _parse_x(text.strip(), state)
                        except ValueError:
                            x = None
                    elif col == 1:
                        try:
                            y = float(text.strip())
                        except ValueError:
                            y = None
                if x is not None and y is not None:
                    xs.append(x)
                    ys.append(y)
        return cls(xs, ys, time_based=state["time"])


# ---- xlsx helpers ------------------------------------------------------

def _local(tag: str) -> str:
    """Strips an XML namespace, e.g. '{...}row' -> 'row'."""
    return tag.rsplit("}", 1)[-1]


def _cell_text(cell, shared):
    cell_type = cell.get("t", "")
    if cell_type == "inlineStr":
        for node in cell.iter():
            if _local(node.tag) == "t":
                return node.text
        return None
    value = None
    for node in cell:
        if _local(node.tag) == "v":
            value = node.text
            break
    if value is None:
        return None
    if cell_type == "s":  # shared string reference
        idx = int(value)
        return shared[idx] if 0 <= idx < len(shared) else None
    return value  # numeric or formula-string result


def _load_shared_strings(zf):
    strings = []
    if "xl/sharedStrings.xml" not in zf.namelist():
        return strings
    with zf.open("xl/sharedStrings.xml") as f:
        tree = ET.parse(f)
    for si in tree.getroot():
        if _local(si.tag) != "si":
            continue
        text = "".join(node.text or "" for node in si.iter() if _local(node.tag) == "t")
        strings.append(text)
    return strings


def _column_index(cell_ref: str) -> int:
    idx = 0
    for ch in cell_ref:
        if not ch.isalpha():
            break
        idx = idx * 26 + (ord(ch.upper()) - ord("A") + 1)
    return idx - 1


# ---- number-or-timestamp x parsing -------------------------------------

def _parse_x(raw: str, state) -> float:
    try:
        return float(raw)
    except ValueError:
        pass
    seconds = _parse_timestamp(raw)  # raises ValueError if not a timestamp either
    state["time"] = True
    return seconds


def _parse_timestamp(raw: str) -> float:
    dt = _to_datetime(raw.strip())
    if dt.tzinfo is not None:
        # Zone given (a trailing 'Z' or a +hh:mm offset): honor it and convert to
        # the true UTC instant, so timestamps are compared as absolute time.
        return dt.timestamp()
    # No zone: use the wall-clock time as written (anchored to UTC only so the
    # number is machine-independent). Lets the same clock reading in different
    # cities line up - comparing local day/night cycles, not absolute UTC time.
    return dt.replace(tzinfo=timezone.utc).timestamp()


def _to_datetime(text: str) -> datetime:
    """Parses a timestamp string to a datetime, raising ValueError if it isn't one.

    datetime.fromisoformat (3.11+) handles date, datetime, 'T'/space, and 'Z';
    we additionally accept '/' as a date separator (YYYY/MM/DD)."""
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    if "/" in text:  # e.g. 2000/06/01 or 2024/01/15 10:30:00Z (time part uses ':')
        try:
            return datetime.fromisoformat(text.replace("/", "-"))
        except ValueError:
            pass
    raise ValueError(f"not a recognized timestamp: {text!r}")


def format_epoch(seconds: float, span_seconds: float = None) -> str:
    """Formats seconds-since-epoch (as produced by the timestamp reader) into a
    readable UTC time string. `span_seconds` (the full x-range being shown) tunes
    the resolution: whole days for wide spans, down to seconds for narrow ones."""
    try:
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return str(seconds)
    if span_seconds is None or span_seconds >= 3 * 86400:
        return dt.strftime("%Y-%m-%d")
    if span_seconds >= 2 * 3600:
        return dt.strftime("%m-%d %H:%M")
    return dt.strftime("%H:%M:%S")
