"""Where the facecam is.

A gaming stream is a game with a small webcam picture in one corner of it. The
short that comes out of it is better when the game fills the screen and the
webcam sits in the corner of it, instead of the whole 16:9 frame squeezed into
a band with blurred fill above and below.

The webcam is found by the one thing a webcam always has and a game almost never
has: a straight border that stays in the same place in every frame. A wall in
the game moves, a HUD bar changes, but the edge of the webcam box does not move
at all.

Metric: for every column and every row, how much the picture changes at that
line, counted over frames spread through the video. A border of the webcam box
stands out from the rest.

Only numpy and ffmpeg, which are already here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

W, H = 320, 180            # the picture is looked at small: only the lines matter
MAX_FRAMES = 24            # frames spread through the video
MIN_SIZE = 0.10            # the smallest a webcam may be, as a part of the width or height
MAX_SIZE = 0.60            # and the largest
EDGE = 2.2                 # how much brighter than the average line a border must be


def _frames(path: str | Path, count: int = MAX_FRAMES) -> np.ndarray:
    """The video as a few grey frames, spread through it."""
    try:
        dur = _duration(path)
        rate = max(count / dur, 0.02) if dur > 0 else 0.2
        proc = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path),
             "-vf", f"fps={rate:.4f},scale={W}:{H},format=gray",
             "-frames:v", str(count), "-f", "rawvideo", "-"],
            capture_output=True, timeout=180)
    except Exception:  # noqa: BLE001 - no ffmpeg or an unreadable file: no facecam, not a failure
        return np.zeros((0, H, W), dtype=np.uint8)
    raw = proc.stdout or b""
    size = W * H
    n = len(raw) // size
    if n < 4:
        return np.zeros((0, H, W), dtype=np.uint8)
    return np.frombuffer(raw[:n * size], dtype=np.uint8).reshape(n, H, W)


def _duration(path: str | Path) -> float:
    try:
        proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                               "-of", "default=nw=1:nk=1", str(path)],
                              capture_output=True, text=True, timeout=60)
        return float((proc.stdout or "").strip() or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _profiles(frames: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(vertical lines, horizontal lines): how much changes at each column and each row.

    The median over the frames is used, so one busy moment cannot invent a line."""
    if len(frames) < 4:
        return np.zeros(W), np.zeros(H)
    f = frames.astype(np.int16)
    gx = np.median(np.abs(np.diff(f, axis=2)).sum(axis=1), axis=0)   # change across each column boundary
    gy = np.median(np.abs(np.diff(f, axis=1)).sum(axis=2), axis=0)   # change across each row boundary
    return gx, gy


def _peaks(profile: np.ndarray, limit: int) -> list[tuple[int, float]]:
    """The lines that stand out: (where, how much)."""
    if len(profile) < 3:
        return []
    med = float(np.median(profile)) or 1.0
    out = []
    for i in range(1, len(profile) - 1):
        if profile[i] >= profile[i - 1] and profile[i] > profile[i + 1] and profile[i] > EDGE * med:
            out.append((i, float(profile[i] / med)))
    return sorted(out, key=lambda p: -p[1])[:limit]


def _size(path: str | Path) -> tuple[int, int]:
    proc = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                           "-show_entries", "stream=width,height", "-of", "default=nw=1", str(path)],
                          capture_output=True, text=True, timeout=60)
    w = h = 0
    for line in (proc.stdout or "").splitlines():
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        try:
            if k.strip() == "width":
                w = int(v.strip())
            elif k.strip() == "height":
                h = int(v.strip())
        except ValueError:
            continue
    return w, h


def _colour(path: str | Path, box: dict, src_w: int = 0, src_h: int = 0, frames: int = 4) -> tuple[float, float, float, float] | None:
    """The colour inside the box and outside it: (warmth, brightness) inside and outside.

    A webcam is a lit room: it is usually warmer and brighter than the game it
    sits on. A scoreboard or a donation overlay is not. The box is in source pixels."""
    try:
        dur = _duration(path)
        rate = max(0.02, frames / dur) if dur > 0 else 0.2
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path),
             "-vf", f"fps={rate:.4f},scale={W}:{H}", "-frames:v", str(frames),
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            capture_output=True, timeout=180).stdout or b""
    except Exception:  # noqa: BLE001
        return None
    size = W * H * 3
    n = len(raw) // size
    if n < 1:
        return None
    a = np.frombuffer(raw[:n * size], dtype=np.uint8).reshape(n, H, W, 3).astype(np.float32)
    # the box is in source pixels; the picture here is 320x180
    x = int(round(box["x"] * W / src_w)) if src_w else int(box["x"])
    y = int(round(box["y"] * H / src_h)) if src_h else int(box["y"])
    w = int(round(box["w"] * W / src_w)) if src_w else int(box["w"])
    h = int(round(box["h"] * H / src_h)) if src_h else int(box["h"])
    x, y = max(0, x), max(0, y)
    w, h = min(w, W - x), min(h, H - y)
    if w < 2 or h < 2:
        return None
    inside = a[:, y:y + h, x:x + w].reshape(-1, 3)
    mask = np.ones((H, W), bool)
    mask[y:y + h, x:x + w] = False
    outside = a[:, mask].reshape(-1, 3)
    if not len(outside):
        return None
    warm_in = float((inside[:, 0] - inside[:, 2]).mean())
    warm_out = float((outside[:, 0] - outside[:, 2]).mean())
    light_in = float(inside[:, 1].mean())
    light_out = float(outside[:, 1].mean())
    return warm_in - warm_out, light_in - light_out, warm_in, light_out


def _refine(profile: np.ndarray, i: int) -> float:
    """Where the line really is, to the pixel: the middle of the energy around it."""
    lo, hi = max(0, i - 2), min(len(profile), i + 3)
    w = profile[lo:hi]
    if not len(w) or w.sum() <= 0:
        return float(i)
    return float((np.arange(lo, hi) * w).sum() / w.sum())


def _exact(path: str | Path, at: float, px: float, py: float) -> tuple[float, float]:
    """The two borders, measured on a full-size frame: the column and the row.

    The small grid finds the border to the nearest column; on the full picture it can be
    found to the pixel."""
    w, h = _size(path)
    if not w or not h:
        return px, py
    try:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, at):.1f}", "-i", str(path),
             "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
            capture_output=True, timeout=120).stdout or b""
    except Exception:  # noqa: BLE001
        return px * w / W, py * h / H
    if len(raw) < w * h:
        return px * w / W, py * h / H
    frame = np.frombuffer(raw[:w * h], dtype=np.uint8).reshape(h, w).astype(np.int16)
    col = np.abs(np.diff(frame, axis=1)).sum(axis=0)      # change at each column boundary
    row = np.abs(np.diff(frame, axis=0)).sum(axis=1)      # change at each row boundary

    def best(profile: np.ndarray, approx: float, span: int = 8) -> float:
        lo, hi = max(0, int(approx) - span), min(len(profile), int(approx) + span + 1)
        seg = profile[lo:hi]
        return float(lo + seg.argmax()) if len(seg) else approx

    return best(col, px * w / W), best(row, py * h / H)


def detect(path: str | Path) -> dict | None:
    """The facecam's box in the source, in source pixels, or None.

    The box is given as x, y, width, height, with the confidence in "score" and
    how sure we are that it is a camera in "conf"."""
    frames = _frames(path)
    if len(frames) < 4:
        return None
    vx, hy = _profiles(frames)
    vpeaks = _peaks(vx, 40)
    hpeaks = _peaks(hy, 40)
    if not vpeaks or not hpeaks:
        return None

    best = None
    # A webcam sits in a corner: its box runs from that corner to the two borders we can see.
    corners = (
        ("top-left", lambda x: x <= W * 0.60, lambda y: y <= H * 0.60, 0, 0),
        ("top-right", lambda x: x >= W * 0.40, lambda y: y <= H * 0.60, 1, 0),
        ("bottom-left", lambda x: x <= W * 0.60, lambda y: y >= H * 0.40, 0, 1),
        ("bottom-right", lambda x: x >= W * 0.40, lambda y: y >= H * 0.40, 1, 1),
    )
    for name, vx_ok, hy_ok, side, vside in corners:
        vs = [(x, s) for x, s in vpeaks if vx_ok(x)]
        hs = [(y, s) for y, s in hpeaks if hy_ok(y)]
        if not vs or not hs:
            continue
        for x, sx in vs[:12]:
            for y, sy in hs[:12]:
                x0, x1 = (0, x) if side == 0 else (x, W)
                y0, y1 = (0, y) if vside == 0 else (y, H)
                bw, bh = (x1 - x0) / W, (y1 - y0) / H
                if not (MIN_SIZE <= bw <= MAX_SIZE and MIN_SIZE <= bh <= MAX_SIZE):
                    continue
                # a webcam is wider than it is tall, most of the time (compared in pixels, not in parts)
                if (bw * W) < (bh * H) * 1.05:
                    continue
                score = min(sx, sy)
                if best is None or score > best["score"]:
                    best = {"px": x, "py": y, "corner": name, "score": round(score, 2)}
    if not best:
        return None
    # the two lines to the pixel, not to the column
    px = _refine(vx, best["px"])
    py = _refine(hy, best["py"])
    name = best["corner"]
    side, vside = name.endswith("right"), name.startswith("bottom")
    w, h = _size(path)
    if not w or not h:
        return None
    # on a full-size frame the border is found to the pixel
    try:
        ex, ey = _exact(path, _duration(path) / 2.0, px, py)
    except Exception:  # noqa: BLE001
        ex, ey = px * w / W, py * h / H
    x0, x1 = (0.0, ex) if not side else (ex, float(w))
    y0, y1 = (0.0, ey) if not vside else (ey, float(h))
    best = dict(best, x=int(round(x0)), y=int(round(y0)), w=int(round(x1 - x0)), h=int(round(y1 - y0)))
    # is it a camera, or a scoreboard drawn over the game?
    col = _colour(path, best, w, h)
    conf = "low"
    if col:
        warm, light = col[0], col[1]
        if warm > 4 or light > 6:
            conf = "high"
        elif warm < -4 and light < -6:
            return None            # colder and darker than the game: not a lit room
    best["conf"] = conf
    return best
