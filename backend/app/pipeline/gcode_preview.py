"""פירוק G-code לשכבות לצורך preview (F-7.7) ורנדור שכבה ראשונה.

מחזיר לכל שכבה את קטעי האקסטרוזיה בלבד (תנועות שמושכות חוט) —
בדיוק מה שצריך כדי לצייר את מסלול ההדפסה.
"""
import re
from pathlib import Path

_COORD = re.compile(r"([XYZEF])(-?\d+\.?\d*)")


def parse_layers(gcode_path: Path, max_segments_per_layer: int = 4000) -> list[dict]:
    """[{z, segments: [[x1,y1,x2,y2], ...]}, ...] — מדולל אם צפוף מדי."""
    layers: list[dict] = []
    current: dict | None = None
    x = y = z = 0.0
    e_prev = 0.0
    absolute_e = True

    with open(gcode_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(";LAYER_CHANGE"):
                if current and current["segments"]:
                    layers.append(current)
                current = {"z": z, "segments": []}
                continue
            if line.startswith(";Z:") and current is not None:
                try:
                    current["z"] = float(line[3:].strip())  # הגובה האמיתי של השכבה
                except ValueError:
                    pass
                continue
            if line.startswith("M82"):
                absolute_e = True
                continue
            if line.startswith("M83"):
                absolute_e = False
                continue
            if line.startswith("G92"):
                for axis, val in _COORD.findall(line.split(";")[0]):
                    if axis == "E":
                        e_prev = float(val)
                continue
            if not (line.startswith("G1") or line.startswith("G0")):
                continue

            coords = dict(_COORD.findall(line.split(";")[0]))
            nx = float(coords.get("X", x))
            ny = float(coords.get("Y", y))
            nz = float(coords.get("Z", z))
            e = coords.get("E")

            extruding = False
            if e is not None:
                ev = float(e)
                extruding = (ev > e_prev) if absolute_e else (ev > 0)
                if absolute_e:
                    e_prev = ev

            if current is not None and extruding and (nx != x or ny != y):
                current["segments"].append([round(x, 2), round(y, 2), round(nx, 2), round(ny, 2)])
            x, y, z = nx, ny, nz

    if current and current["segments"]:
        layers.append(current)

    # דילול שכבות צפופות — שומר את הצורה הכללית
    for layer in layers:
        segs = layer["segments"]
        if len(segs) > max_segments_per_layer:
            step = len(segs) / max_segments_per_layer
            layer["segments"] = [segs[int(i * step)] for i in range(max_segments_per_layer)]
        layer["z"] = round(layer["z"], 3)

    return layers


def insert_color_changes(gcode_path: Path, layers: list[int]) -> int:
    """הזרקת M600 (עצירה להחלפת חוט) בתחילת השכבות המבוקשות (1-based).

    מחזיר כמה החלפות הוזרקו בפועל. M600 נתמך ב-Prusa/Bambu/Marlin מודרני.
    """
    wanted = sorted({n for n in layers if n >= 1})
    if not wanted:
        return 0
    lines = gcode_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    out: list[str] = []
    layer_idx = 0
    inserted = 0
    for line in lines:
        out.append(line)
        if line.startswith(";LAYER_CHANGE"):
            layer_idx += 1
            if layer_idx in wanted:
                out.append(f"M600 ; Photo2Print color change (layer {layer_idx})\n")
                inserted += 1
    gcode_path.write_text("".join(out), encoding="utf-8")
    return inserted


def render_first_layer_png(gcode_path: Path, out_path: Path, bed: tuple[float, float]):
    """שכבה ראשונה — קריטי לאבחון הצמדות (PRD §5.8)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    layers = parse_layers(gcode_path, max_segments_per_layer=20000)
    if not layers:
        return False
    segs = [[(s[0], s[1]), (s[2], s[3])] for s in layers[0]["segments"]]

    fig, ax = plt.subplots(figsize=(6, 6), facecolor="#131622")
    ax.set_facecolor("#131622")
    ax.add_collection(LineCollection(segs, colors="#8b93ff", linewidths=1.2))
    ax.plot([0, bed[0], bed[0], 0, 0], [0, 0, bed[1], bed[1], 0],
            color="#2a3046", linewidth=1)
    ax.set_xlim(-5, bed[0] + 5)
    ax.set_ylim(-5, bed[1] + 5)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="#131622")
    plt.close(fig)
    return True
