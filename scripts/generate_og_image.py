"""Genera docs/og-image.png (1200x630) para link sharing (Open Graph / Twitter).

Diseño: fondo dark (#0e1117), título centrado arriba, subtítulo gris debajo,
mini-chart de 16 velas alternando verde/rojo en la mitad inferior.

Cross-platform (intenta varias TTF). Determinístico (random.seed(42)).
"""
import os
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def load_font(size):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main():
    W, H = 1200, 630
    BG = "#0e1117"
    TITLE_COLOR = "#e6e6e6"
    SUB_COLOR = "#a8b3c7"
    GREEN = "#34d399"
    RED = "#f87171"

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    title = "Análisis técnico de acciones argentinas"
    max_title_w = W - 80
    size = 72
    while size >= 30:
        font_title = load_font(size)
        bbox = draw.textbbox((0, 0), title, font=font_title)
        if bbox[2] - bbox[0] <= max_title_w:
            break
        size -= 2

    font_sub = load_font(32)

    bbox = draw.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) / 2, 160), title, font=font_title, fill=TITLE_COLOR)

    subtitle = "Inversores minoristas argentinos"
    bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
    sw = bbox[2] - bbox[0]
    draw.text(((W - sw) / 2, 240), subtitle, font=font_sub, fill=SUB_COLOR)

    random.seed(42)
    n = 16
    candle_w = 50
    gap = 12
    chart_w = n * (candle_w + gap) - gap
    start_x = (W - chart_w) // 2
    mid_y = 470

    for i in range(n):
        is_up = random.random() > 0.45
        body_h = random.randint(40, 100)
        wick_t = random.randint(10, 30)
        wick_b = random.randint(10, 30)
        color = GREEN if is_up else RED
        x = start_x + i * (candle_w + gap)
        body_top = mid_y - body_h // 2
        body_bot = mid_y + body_h // 2
        draw.rectangle([x, body_top, x + candle_w, body_bot], fill=color)
        wx = x + candle_w // 2 - 1
        draw.rectangle([wx, body_top - wick_t, wx + 2, body_top], fill=color)
        draw.rectangle([wx, body_bot, wx + 2, body_bot + wick_b], fill=color)

    out = Path(__file__).resolve().parents[1] / "docs" / "og-image.png"
    img.save(out, "PNG", optimize=True)
    print(f"Generated {W}x{H} at {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
