"""Icône systray générée à la volée."""

from __future__ import annotations

from PIL import Image, ImageDraw

_COLORS = {
    True: (33, 150, 243, 255),      # bleu actif
    False: (120, 120, 120, 255),    # gris off
    "ok": (67, 160, 71, 255),       # vert corrigé
    "err": (229, 57, 53, 255),      # rouge erreur
    "busy": (251, 168, 37, 255),    # orange en cours
}


def make_icon(enabled: bool = True, size: int = 64, state: str | None = None) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if state in _COLORS:
        fill = _COLORS[state]
    else:
        fill = _COLORS[bool(enabled)]

    margin = size // 10
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=size // 5,
        fill=fill,
    )

    # « Aa »
    ink = (255, 255, 255, 255)
    cx, cy = size // 2, size // 2
    draw.polygon(
        [
            (cx - size * 0.18, cy + size * 0.16),
            (cx, cy - size * 0.18),
            (cx + size * 0.18, cy + size * 0.16),
            (cx + size * 0.10, cy + size * 0.16),
            (cx, cy - size * 0.06),
            (cx - size * 0.10, cy + size * 0.16),
        ],
        fill=ink,
    )
    draw.rectangle(
        (cx - size * 0.08, cy + size * 0.02, cx + size * 0.08, cy + size * 0.07),
        fill=fill,
    )

    if not enabled and state is None:
        draw.line(
            (margin + 2, size - margin - 2, size - margin - 2, margin + 2),
            fill=(220, 60, 60, 255),
            width=max(3, size // 12),
        )
    return img
