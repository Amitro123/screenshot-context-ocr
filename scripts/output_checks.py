"""Local heuristics and conservative layout reconstruction; never certify OCR accuracy.

Inspired by AnyDoc's judged/unknown distinction, number inventories and conservative
column alignment. This operates on OCR word boxes, not a PDF's original text layer.
"""
from collections import Counter
import re
from statistics import median

HEBREW_LETTERS = re.compile(r'[\u05d0-\u05ea]')
FINALS = set('ךםןףץ')
NUMBERS = re.compile(r'[-+]?\d+(?:[.,:/-]\d+)*%?')


def hebrew_check(text):
    words = []
    # Split punctuation boundaries; vowel/cantillation marks do not count as letters.
    for token in re.findall(r'[\u0590-\u05ff]+', text):
        letters = HEBREW_LETTERS.findall(token)
        if len(letters) >= 2:
            words.append(letters)
    leading = sum(w[0] in FINALS for w in words)
    trailing = sum(w[-1] in FINALS for w in words)
    middle = sum(any(c in FINALS for c in w[1:-1]) for w in words)
    judged = len(words) >= 3
    return {'judged': judged, 'sample_words': len(words), 'leading_final': leading,
            'trailing_final': trailing, 'midword_final': middle,
            'possible_reversal': judged and leading >= 3 and leading > trailing,
            'suspicious_midword': judged and middle >= 2 and middle / len(words) > 0.03}


def preservation(before, after):
    """Check output transformation only, NOT whether pixels were read correctly.

    Inventories ignore order: neither check proves correct row/column association.
    """
    numbers_before, numbers_after = Counter(NUMBERS.findall(before)), Counter(NUMBERS.findall(after))
    return {'scope': 'ocr_text_to_output_only',
            'word_inventory_preserved': Counter(before.split()) == Counter(after.split()),
            'number_inventory_preserved': numbers_before == numbers_after,
            'missing_numbers': dict(numbers_before - numbers_after),
            'added_numbers': dict(numbers_after - numbers_before)}


def table_text(raw, words, direction='auto'):
    """Return TSV only for a complete, consistently aligned rectangular word grid.

    Explicit opt-in; whole image must be one simple table. Ambiguity returns raw text.
    No invented headers, blank cells, merged cells, numeric correction or forced RTL.
    """
    def fallback(reason):
        return raw, {'status': 'fallback', 'reason': reason, 'structure_verified': False}
    if not words:
        return fallback('no_word_boxes')
    boxes = []
    try:
        for i, word in enumerate(words):
            x, y, width, height = (int(word[k]) for k in ('left', 'top', 'width', 'height'))
            if width <= 0 or height <= 0:
                return fallback('invalid_word_boxes')
            text = word['text'].strip()
            if not text or any(c in text for c in '\t\r\n'):
                return fallback('invalid_word_text')
            boxes.append({'x': x, 'y': y + height/2, 'right': x+width,
                          'height': height, 'text': text, 'order': i})
    except (KeyError, TypeError, ValueError):
        return fallback('invalid_word_boxes')
    typical = median(b['height'] for b in boxes)
    rows = []
    for box in sorted(boxes, key=lambda b: (b['y'], b['x'])):
        if not rows or abs(box['y'] - median(b['y'] for b in rows[-1])) > typical * 0.55:
            rows.append([])
        rows[-1].append(box)
    cells = []
    for row in rows:
        groups = []
        for box in sorted(row, key=lambda b: b['x']):
            if not groups or box['x'] - max(b['right'] for b in groups[-1]) > typical * 2:
                groups.append([])
            groups[-1].append(box)
        cells.append(groups)
    count = len(cells[0])
    if len(cells) < 3 or not 2 <= count <= 12:
        return fallback('insufficient_grid')
    if any(len(row) != count for row in cells):
        return fallback('unequal_cell_counts')
    # Require separable column bands and consistent left, right OR center alignment.
    for column in range(count):
        starts = [min(b['x'] for b in row[column]) for row in cells]
        ends = [max(b['right'] for b in row[column]) for row in cells]
        centers = [(left+right)/2 for left, right in zip(starts, ends)]
        spread = min(max(v)-min(v) for v in (starts, ends, centers))
        if spread > typical:
            return fallback('misaligned_columns')
        if column + 1 < count:
            next_start = min(min(b['x'] for b in row[column+1]) for row in cells)
            if next_start - max(ends) <= typical * 2:
                return fallback('overlapping_column_bands')
    if direction == 'auto':
        letters = [c for c in raw if c.isalpha()]
        share = len(HEBREW_LETTERS.findall(raw)) / max(1, len(letters))
        direction = 'rtl' if share > 0.3 else 'ltr'
    rendered = []
    for row in cells:
        if direction == 'rtl':
            row = list(reversed(row))
        # Keep Tesseract's original token order within cells (mixed RTL/LTR included).
        rendered.append('\t'.join(' '.join(b['text'] for b in sorted(cell, key=lambda b: b['order']))
                                  for cell in row))
    result = '\n'.join(rendered)
    checks = preservation(raw, result)
    if not checks['word_inventory_preserved'] or not checks['number_inventory_preserved']:
        return fallback('content_inventory_mismatch')
    return result, {'status': 'inferred', 'format': 'tsv', 'rows': len(cells),
                    'columns': count, 'direction': direction, 'structure_verified': False}
