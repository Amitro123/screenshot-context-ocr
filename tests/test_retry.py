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


if __name__ == '__main__':
    unittest.main()
