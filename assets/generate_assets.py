"""Regenerates the README illustrations in this folder (needs Pillow built with libraqm for Hebrew).

The popup images are drawn with the same colours, sizes and strings as clipboard-watcher.pyw
(locales/en.json). They are illustrations, not screenshots: replace them with real captures if you prefer.

    python assets/generate_assets.py
"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
T = json.loads((HERE.parent / "locales" / "en.json").read_text(encoding="utf-8"))
S = 2  # output scale (retina)

SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

# Same palette as clipboard-watcher.pyw
DARK, TEXT, SUBTLE = "#1e1e2e", "#cdd6f4", "#a6adc8"
BLUE, GREEN, RED, AMBER = "#89b4fa", "#a6e3a1", "#f38ba8", "#f9e2af"
GRAY, BORDER = "#313244", "#45475a"


def font(path, size):
    return ImageFont.truetype(path, int(size * S))


def wrap(text, fnt, max_w):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            trial = (cur + " " + word).strip()
            if fnt.getlength(trial) <= max_w * S or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


# ----------------------------------------------------------------------- popups

def popup(kind):
    """Returns the popup as an RGBA image, matching the real window geometry."""
    spec = {
        "question": (128, None),
        "working": (56, None),
        "active": (80, ("\u25cf", BLUE, T["started"])),
        "success": (80, ("\u2714", GREEN, T["copied"])),
        "warning": (110, ("\u26a0", AMBER, T["warning"].format(reasons=T["reasons"]["mixed_tokens"]))),
    }
    h, result = spec[kind]
    w = 380
    img = Image.new("RGBA", (w * S, h * S), BORDER)
    d = ImageDraw.Draw(img)
    d.rectangle([S, S, (w - 1) * S, (h - 1) * S], fill=DARK)
    pad_x, pad_y = 16, 12
    icon_font = font(SANS, 15)

    if kind == "question":
        d.text((pad_x * S, pad_y * S + 2 * S), "\u2702", font=icon_font, fill=BLUE)
        d.text(((pad_x + 28) * S, pad_y * S + 2 * S), T["toast_title"], font=font(SANS_B, 13.5), fill=TEXT)
        d.text((pad_x * S, (pad_y + 31) * S), T["toast_body"], font=font(SANS, 11.5), fill=SUBTLE)
        yes_f, no_f = font(SANS_B, 11.5), font(SANS, 11.5)
        y0, bh = 76, 28
        yw = int(yes_f.getlength(T["yes"]) / S) + 24
        d.rectangle([pad_x * S, y0 * S, (pad_x + yw) * S, (y0 + bh) * S], fill=BLUE)
        d.text(((pad_x + 12) * S, (y0 + 5) * S), T["yes"], font=yes_f, fill=DARK)
        nx = pad_x + yw + 8
        d.rectangle([nx * S, y0 * S, (nx + 62) * S, (y0 + bh) * S], fill=GRAY)
        tw = no_f.getlength(T["no"]) / S
        d.text(((nx + (62 - tw) / 2) * S, (y0 + 5) * S), T["no"], font=no_f, fill=TEXT)
    elif kind == "working":
        d.text((pad_x * S, (h / 2 - 11) * S), "\u27f3", font=icon_font, fill=SUBTLE)
        d.text(((pad_x + 28) * S, (h / 2 - 8) * S), T["working"], font=font(SANS, 11.5), fill=SUBTLE)
    else:
        icon, color, body = result
        fnt = font(SANS, 11.5)
        lines = wrap(body, fnt, 300)
        y = (h - 17 * len(lines)) / 2 - 1  # Tk centres the label vertically in the popup
        d.text((pad_x * S, (h / 2 - 11) * S), icon, font=icon_font, fill=color)
        for line in lines:
            d.text(((pad_x + 30) * S, y * S), line, font=fnt, fill=color)
            y += 17
    return img


def desktop_scene(kind):
    """Popup placed bottom-right above a taskbar, on a neutral desktop backdrop."""
    pop = popup(kind)
    pw, ph = pop.size
    W, H = 520, ph // S + 150
    scene = Image.new("RGBA", (W * S, H * S))
    px = scene.load()
    top, bottom = (58, 78, 112), (96, 124, 168)
    for y in range(H * S):
        t = y / (H * S)
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
        for x in range(W * S):
            px[x, y] = row
    wins = Image.new("RGBA", scene.size, (0, 0, 0, 0))
    wd = ImageDraw.Draw(wins)
    for (x, y, w, h, a) in [(24, 22, 210, 110, 34), (258, 40, 150, 70, 24)]:  # faint background windows
        wd.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=8 * S, fill=(255, 255, 255, a))
    scene = Image.alpha_composite(scene, wins)
    d = ImageDraw.Draw(scene)
    d.rectangle([0, (H - 48) * S, W * S, H * S], fill=(22, 24, 34, 235))  # taskbar
    for i in range(5):
        cx = W // 2 - 60 + i * 28
        d.rounded_rectangle([cx * S, (H - 36) * S, (cx + 20) * S, (H - 16) * S], radius=5 * S, fill=(120, 130, 160, 200))
    x = (W - 20) * S - pw
    y = (H - 60) * S - ph
    shadow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle([x, y + 6 * S, x + pw, y + ph + 6 * S], fill=(0, 0, 0, 150))
    scene = Image.alpha_composite(scene, shadow.filter(ImageFilter.GaussianBlur(10 * S)))
    scene.alpha_composite(pop, (x, y))
    return scene.convert("RGB")


# ------------------------------------------------------------------------ demo

HEBREW_LINE = "\u05d4\u05e2\u05e8\u05d4: \u05d4\u05d1\u05d3\u05d9\u05e7\u05d4 \u05e0\u05db\u05e9\u05dc\u05ea \u05e8\u05e7 \u05d1\u05e1\u05d1\u05d9\u05d1\u05ea CI"  # sample Hebrew line
CODE_LINES = [
    "PS C:\\proj> pytest tests\\test_sync.py -q",
    "FAILED tests/test_sync.py::test_retry",
    "  TimeoutError: no response after 30s",
    "1 failed, 41 passed in 12.4s",
]


def draw_lines(d, x, y, right_edge, color, size=13, step=21):
    mono = font(MONO, size)
    for line in CODE_LINES:
        d.text((x * S, y * S), line, font=mono, fill=color)
        y += step
    sans = font(SANS, size)
    w = d.textlength(HEBREW_LINE, font=sans, direction="rtl", language="he")
    d.text((right_edge * S - w, y * S), HEBREW_LINE, font=sans, fill=color, direction="rtl", language="he")


def dashed_rect(d, box, color, width=2, dash=8, gap=6):
    x0, y0, x1, y1 = [v * S for v in box]
    step = (dash + gap) * S
    for x in range(int(x0), int(x1), step):
        d.line([x, y0, min(x + dash * S, x1), y0], fill=color, width=width * S)
        d.line([x, y1, min(x + dash * S, x1), y1], fill=color, width=width * S)
    for y in range(int(y0), int(y1), step):
        d.line([x0, y, x0, min(y + dash * S, y1)], fill=color, width=width * S)
        d.line([x1, y, x1, min(y + dash * S, y1)], fill=color, width=width * S)


def demo():
    W, H = 1080, 370
    img = Image.new("RGB", (W * S, H * S), "#f6f8fa")
    d = ImageDraw.Draw(img)
    label, small = font(SANS_B, 14), font(SANS, 12)

    d.text((30 * S, 22 * S), "What you capture (Win+Shift+S)", font=label, fill="#24292f")
    d.text((600 * S, 22 * S), "What Claude receives (Ctrl+V)", font=label, fill="#24292f")

    # left: captured terminal region
    x0, y0, x1, y1 = 30, 56, 480, 300
    d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], radius=8 * S, fill=DARK)
    d.rounded_rectangle([x0 * S, y0 * S, x1 * S, (y0 + 28) * S], radius=8 * S, fill="#181825")
    d.rectangle([x0 * S, (y0 + 18) * S, x1 * S, (y0 + 28) * S], fill="#181825")
    for i, c in enumerate(["#f38ba8", "#f9e2af", "#a6e3a1"]):
        d.ellipse([(x0 + 14 + i * 18) * S, (y0 + 9) * S, (x0 + 24 + i * 18) * S, (y0 + 19) * S], fill=c)
    draw_lines(d, x0 + 18, y0 + 52, x1 - 18, TEXT)
    dashed_rect(d, (x0 - 6, y0 - 6, x1 + 6, y1 + 6), "#0969da")
    d.text((x0 * S, (y1 + 14) * S), "Image: heavier, not searchable, not editable", font=small, fill="#57606a")

    # arrow
    ax0, ax1, ay = 500, 580, 178
    d.line([ax0 * S, ay * S, (ax1 - 8) * S, ay * S], fill="#0969da", width=4 * S)
    d.polygon([(ax1 * S, ay * S), ((ax1 - 16) * S, (ay - 10) * S), ((ax1 - 16) * S, (ay + 10) * S)], fill="#0969da")
    d.text((ax0 * S - 6 * S, (ay - 34) * S), "Click \u201cYes\u201d", font=small, fill="#0969da")
    d.text((ax0 * S - 2 * S, (ay + 16) * S), "local OCR", font=small, fill="#57606a")

    # right: chat input with pasted text
    rx0, ry0, rx1, ry1 = 600, 56, 1050, 300
    d.rounded_rectangle([rx0 * S, ry0 * S, rx1 * S, ry1 * S], radius=14 * S, fill="#ffffff", outline="#d0d7de", width=2 * S)
    d.text(((rx0 + 20) * S, (ry0 + 16) * S), "Reply to Claude\u2026", font=small, fill="#8c959f")
    draw_lines(d, rx0 + 20, ry0 + 52, rx1 - 20, "#24292f")
    d.rounded_rectangle([(rx0 + 20) * S, (ry1 - 44) * S, (rx0 + 168) * S, (ry1 - 16) * S], radius=14 * S, fill="#dafbe1")
    d.text(((rx0 + 32) * S, (ry1 - 38) * S), "\u2714 pasted as text", font=small, fill="#1a7f37")
    d.text((rx0 * S, (ry1 + 14) * S), "Text: light, searchable, editable before sending", font=small, fill="#57606a")

    d.text((30 * S, (H - 30) * S), "Illustration. Extraction runs locally with Tesseract; no screenshot or text leaves your machine.",
           font=small, fill="#8c959f")
    return img


if __name__ == "__main__":
    demo().save(HERE / "demo.png", optimize=True)
    for name in ["question", "working", "active", "success", "warning"]:
        desktop_scene(name).save(HERE / f"popup-{name}.png", optimize=True)
    print("assets written to", HERE)
