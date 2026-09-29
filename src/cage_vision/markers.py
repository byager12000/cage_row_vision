"""Printable reference markers as a vector PDF (one US-letter page per marker).

Hand-written PDF so there is no extra dependency. PDF units are 1/72 in, so the
black square prints at exactly `markers.size` when printed at 100% / Actual size.
Each page also carries a 6 in check bar: if it does not measure 6.00 in, the
printer scaled the page.
"""

from __future__ import annotations

from pathlib import Path

import cv2

from .config import Config

PAGE_W, PAGE_H = 8.5, 11.0   # in
PT = 72.0                    # points per inch


def _xy(x_in: float, y_top_in: float) -> tuple[float, float]:
    """Inches from the top-left of the page -> PDF points from the bottom-left."""
    return x_in * PT, (PAGE_H - y_top_in) * PT


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _text(x_in: float, y_top_in: float, size_pt: float, s: str) -> str:
    x, y = _xy(x_in, y_top_in)
    return f"BT /F1 {size_pt:g} Tf {x:.2f} {y:.2f} Td ({_esc(s)}) Tj ET"


def _line(x1, y1, x2, y2) -> str:
    a, b = _xy(x1, y1)
    c, d = _xy(x2, y2)
    return f"{a:.3f} {b:.3f} m {c:.3f} {d:.3f} l S"


def page_content(cfg: Config, marker_id: int) -> str:
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, cfg.markers.dictionary))
    n = d.markerSize + 2                                  # data cells + 1-cell border each side
    size_in = cfg.markers.size if cfg.units == "in" else cfg.markers.size / 25.4
    cell = size_in / n
    x0, y0 = (PAGE_W - size_in) / 2, (PAGE_H - size_in) / 2
    cx, cy = PAGE_W / 2, PAGE_H / 2
    bits = cv2.aruco.generateImageMarker(d, marker_id, n, borderBits=1)   # row 0 = top

    ops = ["0 g 0 G"]
    # All black cells in one path + one fill: no hairline seams between cells.
    for r in range(n):
        for c in range(n):
            if bits[r, c] < 128:
                x, y = _xy(x0 + c * cell, y0 + (r + 1) * cell)             # bottom-left of the cell
                ops.append(f"{x:.3f} {y:.3f} {cell * PT:.3f} {cell * PT:.3f} re")
    ops.append("f")

    # Tick marks pointing at the marker center (stay clear of the white quiet zone).
    gap, tick = 0.6, 0.6
    ops.append(f"{0.02 * PT:.2f} w")
    ops += [_line(cx, y0 - gap - tick, cx, y0 - gap), _line(cx, y0 + size_in + gap, cx, y0 + size_in + gap + tick),
            _line(x0 - gap - tick, cy, x0 - gap, cy), _line(x0 + size_in + gap, cy, x0 + size_in + gap + tick, cy)]

    # 6 in scale-check bar near the bottom.
    bx, by, blen = 1.25, 9.6, 6.0
    ops.append(_line(bx, by, bx + blen, by))
    for i in range(int(blen) + 1):
        ops.append(_line(bx + i, by - 0.15, bx + i, by + 0.15))
        ops.append(_text(bx + i - 0.04, by + 0.4, 9, str(i)))

    unit = cfg.units
    ops += [
        _text(0.75, 1.0, 22, f"Marker ID {marker_id}"),
        _text(0.75, 1.35, 10, f"{cfg.markers.dictionary}   |   STK-14 Cage Row Vision reference marker"),
        _text(0.75, 1.75, 11, f"Black square = {cfg.markers.size:g} {unit}. Print at 100% / Actual size - NOT fit to page."),
        _text(0.75, 2.0, 11, "Measure the printed black square and put that value in config.yaml (markers.size)."),
        _text(0.75, 2.25, 11, "Keep at least 1/2 in of white paper around the black square if you trim the page."),
        _text(0.75, 8.6, 11, "Tick marks point to the marker CENTER - that is the point to measure for markers.positions."),
        _text(1.25, 10.25, 11, "This bar must measure exactly 6.00 in. If it does not, printer scaling is on."),
    ]
    return "\n".join(ops)


def write_marker_pdf(cfg: Config, path: str | Path) -> Path:
    path = Path(path)
    ids = sorted(cfg.markers.positions)
    objs: list[bytes] = []                                  # object n is objs[n-1]

    def add(body: bytes) -> int:
        objs.append(body)
        return len(objs)

    catalog = add(b"")                                      # filled in below
    pages = add(b"")
    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    kids = []
    for mid in ids:
        data = page_content(cfg, mid).encode("latin-1")
        stream = add(b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream")
        kids.append(add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %g %g] /Resources << /Font << /F1 %d 0 R >> >> "
                         "/Contents %d 0 R >>" % (pages, PAGE_W * PT, PAGE_H * PT, font, stream)).encode()))
    objs[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages
    objs[pages - 1] = ("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{k} 0 R" for k in kids), len(kids))).encode()

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, catalog, xref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    return path
