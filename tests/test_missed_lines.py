import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ink_check
import ocr


def page(rows, rule=False):
    """White page; each row is a 300x10 strip of letter-like blocks starting at x=10."""
    im = Image.new('RGB', (400, 200), 'white')
    d = ImageDraw.Draw(im)
    for y in rows:
        for x in range(10, 310, 10):
            d.rectangle([x, y, x + 7, y + 9], fill=(120, 90, 200))
    if rule:
        d.rectangle([10, 150, 390, 151], fill=(120, 90, 200))
    return im


def boxes(rows):
    """TSV-like word rows (scale 1, 20 px border) covering each given text row with three words."""
    return [{'left': str(20 + x), 'top': str(20 + y), 'width': '100', 'height': '10'} for y in rows for x in (10, 110, 210)]


class MissedLineTests(unittest.TestCase):
    def test_uncovered_text_row_is_counted(self):
        self.assertEqual(ink_check.missed_line_bands(page([10, 40, 70]), boxes([10, 70]), 1), 1)

    def test_all_rows_covered_is_zero(self):
        self.assertEqual(ink_check.missed_line_bands(page([10, 40, 70]), boxes([10, 40, 70]), 1), 0)

    def test_thin_rule_and_few_words_are_ignored(self):
        self.assertEqual(ink_check.missed_line_bands(page([10, 40], rule=True), boxes([10, 40]), 1), 0)
        self.assertEqual(ink_check.missed_line_bands(page([10, 40]), boxes([10])[:2], 1), 0)  # too few boxes to judge

    def test_warning_code(self):
        self.assertIn('possible_missed_lines:2', ocr.quality_warnings('x y', {'missed_line_bands': 2}))
        self.assertEqual(ocr.quality_warnings('x y', {'missed_line_bands': 0}), [])

    def test_retry_prefers_fewer_missed_bands_and_ties_keep_first(self):
        def run(first, second):
            def fake_extract(exe, image, a):
                missed = first if a.psm == 3 else second
                return f'text{a.psm}', {'word_count': 5, 'low_confidence_words': [], 'missed_line_bands': missed}
            a = SimpleNamespace(scale=3, psm=3, invert='auto', lang='eng', tessdata=None, table=False)
            with patch.object(ocr, 'extract', fake_extract):
                text, report, warnings = ocr.extract_with_retry('tess', Image.new('RGB', (4, 4)), a, True)
            return text, warnings
        self.assertEqual(run(3, 0), ('text6', []))
        self.assertEqual(run(3, 1), ('text6', ['possible_missed_lines:1']))
        self.assertEqual(run(1, 3)[0], 'text3')
        self.assertEqual(run(2, 2)[0], 'text3')

    def test_min_channel_darkens_pale_colour_on_light_page_only(self):
        pale = Image.new('RGB', (20, 20), 'white')
        ImageDraw.Draw(pale).rectangle([5, 5, 14, 14], fill=(170, 150, 235))
        lum = ocr.preprocess(pale, 1, 'auto').getpixel((30, 30))
        dark = ocr.preprocess(pale, 1, 'auto', 'min').getpixel((30, 30))
        self.assertLess(dark, lum)
        night = Image.new('RGB', (20, 20), (20, 20, 30))
        ImageDraw.Draw(night).rectangle([5, 5, 14, 14], fill=(170, 150, 235))
        self.assertEqual(ocr.preprocess(night, 1, 'auto', 'min').tobytes(), ocr.preprocess(night, 1, 'auto').tobytes())


if __name__ == '__main__':
    unittest.main()
