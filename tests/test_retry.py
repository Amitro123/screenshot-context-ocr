import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ocr


def args(**kw):
    base = dict(scale=3, psm=3, invert='auto', lang='heb+eng', tessdata=None, table=False)
    base.update(kw)
    return SimpleNamespace(**base)


class RetryTests(unittest.TestCase):
    def run_retry(self, warn_first, warn_second, allow=True, **kw):
        """Mock extract and quality_warnings: results are keyed by the pass's psm."""
        calls = []

        def fake_extract(exe, image, a):
            calls.append((a.scale, a.psm))
            return f'text{a.psm}', {'word_count': 1, 'low_confidence_words': []}

        def fake_warnings(text, report):
            n = warn_first if text == 'text3' else warn_second
            return ['w'] * n

        with patch.object(ocr, 'extract', fake_extract), patch.object(ocr, 'quality_warnings', fake_warnings):
            out = ocr.extract_with_retry('tess', Image.new('RGB', (4, 4)), args(**kw), allow)
        return out, calls

    def test_no_warnings_no_retry(self):
        (text, report, warnings), calls = self.run_retry(0, 0)
        self.assertEqual(calls, [(3, 3)])
        self.assertEqual(report['retry'], {'used': False, 'chosen': 'first'})

    def test_fewer_warnings_second_wins(self):
        (text, report, warnings), calls = self.run_retry(2, 1)
        self.assertEqual(calls, [(3, 3), (2, 6)])
        self.assertEqual((text, len(warnings)), ('text6', 1))
        self.assertEqual(report['retry'], {'used': True, 'chosen': 'second'})

    def test_more_warnings_keeps_first(self):
        (text, report, warnings), _ = self.run_retry(1, 3)
        self.assertEqual((text, report['retry']['chosen']), ('text3', 'first'))

    def test_tie_keeps_first(self):
        (text, report, warnings), calls = self.run_retry(2, 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual((text, report['retry']), ('text3', {'used': True, 'chosen': 'first'}))

    def test_disabled_does_not_retry(self):
        (_, report, _), calls = self.run_retry(2, 0, allow=False)
        self.assertEqual(calls, [(3, 3)])
        self.assertFalse(report['retry']['used'])

    def test_table_mode_does_not_retry(self):
        (_, report, _), calls = self.run_retry(2, 0, table=True)
        self.assertEqual(len(calls), 1)

    def test_main_flags_control_allow_retry(self):
        seen = []

        def fake_retry(exe, image, a, allow):
            seen.append((allow, a.scale, a.psm))
            return 'x', {'word_count': 1, 'low_confidence_words': [], 'retry': {}}, []

        tmp = Path(__import__('tempfile').mkdtemp())
        img = tmp / 'a.png'
        Image.new('RGB', (4, 4)).save(img)
        cases = [([], (True, 3, 3)), (['--no-retry'], (False, 3, 3)),
                 (['--scale', '2'], (False, 2, 3)), (['--psm', '6'], (False, 3, 6))]
        for extra, expected in cases:
            with patch.object(ocr, 'extract_with_retry', fake_retry), patch.object(ocr, 'engine', lambda e=None: 'tess'), \
                    patch.object(ocr, 'check_languages', lambda *a: None), \
                    patch.object(sys, 'argv', ['ocr.py', '--image', str(img)] + extra), \
                    patch('sys.stdout'), patch('sys.stderr'):
                self.assertEqual(ocr.main(), 0)
            self.assertEqual(seen[-1], expected, extra)


def word(text, conf, left, top=10, width=40, height=20):
    return {'text': text, 'conf': str(conf), 'left': str(left), 'top': str(top),
            'width': str(width), 'height': str(height)}


class HebrewSecondOpinionTests(unittest.TestCase):
    LATIN = [word('DN', 78, 0), word('cli.py', 90, 100), word('NN', 95, 200), word('ON', 80, 300)]
    HEB = [word('אם', 93, 2), word('קלי', 40, 100),
           word('ממנו', 91, 201), word('Latin', 99, 300)]

    def run_pass(self, allow=True, warnings=('mixed_tokens:3',), lang='heb+eng'):
        calls = []

        def fake_extract(exe, image, a):
            calls.append(a.lang)
            words = self.HEB if a.lang == 'heb' else self.LATIN
            return 'DN cli.py NN ON', {'_words': list(words), 'word_count': 4, 'low_confidence_words': []}

        with patch.object(ocr, 'extract', fake_extract), \
                patch.object(ocr, 'quality_warnings', lambda t, r: list(warnings) if t.startswith('DN') else []):
            out = ocr.extract_with_retry('tess', Image.new('RGB', (4, 4)), args(lang=lang), allow)
        return out, calls

    def test_swaps_only_suspicious_tokens_with_higher_pure_hebrew_confidence(self):
        (text, report, warnings), calls = self.run_pass()
        # DN -> Hebrew (93 > 78); cli.py not a candidate; NN -> Hebrew (91 < 95, kept); ON -> Latin overlap, kept
        self.assertEqual(text, 'אם cli.py NN ON')
        self.assertEqual(report['retry']['hebrew_pass'], {'candidates': 3, 'replaced': 1})
        self.assertNotIn('_words', report)
        self.assertEqual(warnings, [])

    def test_swap_matches_whole_tokens_only(self):
        words = [word('NN', 50, 0)]
        heb = [word('אני', 90, 0)]

        def fake_extract(exe, image, a):
            return '', {'_words': list(heb)}

        with patch.object(ocr, 'extract', fake_extract):
            text, candidates, replaced = ocr.hebrew_second_opinion('tess', None, args(), 'NANNY NN', words)
        self.assertEqual((text, replaced), ('NANNY אני', 1))

    def test_no_retry_disables_hebrew_pass(self):
        (text, report, _), calls = self.run_pass(allow=False)
        self.assertEqual(calls, ['heb+eng'])
        self.assertEqual(text, 'DN cli.py NN ON')
        self.assertNotIn('hebrew_pass', report['retry'])
        self.assertNotIn('_words', report)

    def test_no_mixed_tokens_warning_no_hebrew_pass(self):
        (_, report, _), calls = self.run_pass(warnings=('midword_final',))
        self.assertNotIn('heb', calls)
        self.assertNotIn('hebrew_pass', report['retry'])

    def test_english_only_or_hebrew_only_lang_skips_hebrew_pass(self):
        for lang in ('heb', 'eng'):
            (_, report, _), calls = self.run_pass(lang=lang)
            self.assertNotIn('hebrew_pass', report['retry'], lang)


if __name__ == '__main__':
    unittest.main()
