"""Grab a window and read its text, using tools that ship with macOS.

Two small Swift programs do the platform work and are compiled on first use
into ``.cache/``: ``windows`` lists an app's on-screen windows, and ``ocr``
reads the text in an image with the system recogniser.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE.parents[1] / ".cache"


@dataclass(frozen=True, slots=True)
class TextItem:
    """One piece of recognised text. Coordinates are fractions of the image, y from the top."""

    text: str
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def _tool(name: str) -> Path:
    """Path to a compiled helper, building it if the source is newer."""
    source, binary = HERE / f"{name}.swift", CACHE / name
    if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
        CACHE.mkdir(exist_ok=True)
        subprocess.run(["swiftc", "-O", "-o", str(binary), str(source)], check=True)
    return binary


def find_window(owner: str) -> int | None:
    """Id of the largest on-screen window belonging to the app called ``owner``."""
    out = subprocess.run([str(_tool("windows")), owner], capture_output=True, text=True).stdout
    best, best_area = None, 0
    for line in out.splitlines():
        window_id, _, size = line.split("\t")
        width, height = (int(v) for v in size.split("x"))
        if width * height > best_area:
            best, best_area = int(window_id), width * height
    return best


def grab(window_id: int, path: Path) -> bool:
    """Save a picture of one window. Needs the Screen Recording permission."""
    done = subprocess.run(["screencapture", "-x", "-o", "-l", str(window_id), str(path)])
    return done.returncode == 0 and path.exists()


def read_text(path: Path, fast: bool = False) -> list[TextItem]:
    """All text the system recogniser finds in an image."""
    command = [str(_tool("ocr")), str(path)] + (["fast"] if fast else [])
    out = subprocess.run(command, capture_output=True, text=True).stdout
    items = []
    for line in out.splitlines():
        if line.startswith("{"):
            d = json.loads(line)
            items.append(TextItem(d["text"], d["x"], d["y"], d["w"], d["h"]))
    return items
