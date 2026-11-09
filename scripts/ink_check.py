"""Pillow-only check for text lines the OCR engine silently dropped. Heuristic: never certifies accuracy.

Ink = pixels that differ clearly from the page background. Everything under an OCR word box is erased; what remains
in text-height bands (wide enough, dense enough, not a thin rule) is ink no recognized word accounts for.
"""
from statistics import median
from PIL import Image, ImageDraw

INK_DELTA = 40        # gray distance from the background that counts as ink
PAD = 3               # px of margin erased around each word box (anti-aliasing, italic overhang)
MIN_BAND = 5          # px: thinner bands are rules, underlines or borders
MIN_SPAN = 5.0        # band must be at least this many text-heights wide
MIN_INK = 0.8         # ... and hold at least this many ink pixels per row, in text-heights, on average
MAX_BAND = 3.0        # taller bands (photos, diagrams, blocks) are not judged: this check is for text lines


def _background(gray):
    hist = gray.histogram()
    return max(range(256), key=hist.__getitem__)


def missed_line_bands(image, words, scale, border=20):
    """Count text-height bands of ink with no OCR word on them. `words` are Tesseract TSV rows (level 5) read from
    an image that was scaled by `scale` and padded by `border` px. Returns 0 when there is too little to judge."""
    heights = []
    boxes = []
    try:
        for w in words:
            x, y, bw, bh = (int(w[k]) for k in ('left', 'top', 'width', 'height'))
            boxes.append(((x - border) / scale, (y - border) / scale, (x - border + bw) / scale, (y - border + bh) / scale))
            heights.append(bh / scale)
    except (KeyError, TypeError, ValueError):
        return 0
    if len(heights) < 3:
        return 0
    text_h = median(heights)
    gray = image.convert('L')
    bg = _background(gray)
    lut = [255 if abs(v - bg) > INK_DELTA else 0 for v in range(256)]
    mask = gray.point(lut)
    draw = ImageDraw.Draw(mask)
    for left, top, right, bottom in boxes:
        draw.rectangle([left - PAD, top - PAD, right + PAD, bottom + PAD], fill=0)
    width, height = mask.size
    column = mask.resize((1, height), Image.Resampling.BOX)  # row ink share, 0..255
    ink = [v * width / 255 for v in column.tobytes()]
    bands, start = [], None
    for y, count in enumerate(ink + [0]):
        if count >= 2 and start is None:
            start = y
        elif count < 2 and start is not None:
            bands.append([start, y])
            start = None
    merged = []
    for band in bands:  # bridge 1-2 px gaps inside one line
        if merged and band[0] - merged[-1][1] <= 2:
            merged[-1][1] = band[1]
        else:
            merged.append(band)
    missed = 0
    for top, bottom in merged:
        band_h = bottom - top
        if band_h < max(MIN_BAND, 0.5 * text_h) or band_h > MAX_BAND * text_h:
            continue
        box = mask.crop((0, top, width, bottom)).getbbox()
        if not box or box[2] - box[0] < MIN_SPAN * text_h:
            continue
        if sum(ink[top:bottom]) < MIN_INK * text_h * band_h:
            continue
        missed += 1
    return missed
