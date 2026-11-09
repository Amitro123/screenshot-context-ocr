import ctypes
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import ocr
from clipboard_win import ClipboardChanged, ClipboardPoller, WindowsClipboard, read_image


class FakeClipboard:
    def __init__(self, seq=1, image=True):
        self.seq, self.image = seq, image
        self.value = 'original'
        self.format_reads = 0

    def sequence(self):
        return self.seq

    def has_image(self):
        self.format_reads += 1
        return self.image

    def copy_text(self, text, expected):
        if self.seq != expected:
            raise ClipboardChanged('new content preserved')
        self.value = text


class ClipboardTests(unittest.TestCase):
    def test_stale_consent_never_reads_new_image(self):
        grab = Mock()
        with self.assertRaises(ClipboardChanged):
            read_image(FakeClipboard(2), grab, 1)
        grab.assert_not_called()

    def test_change_during_image_read_is_rejected(self):
        clip = FakeClipboard()
        def grab():
            clip.seq = 2
            return Image.new('RGB', (10, 10))
        with self.assertRaises(ClipboardChanged):
            read_image(clip, grab, 1)

    def test_unchanged_image_is_bound_to_sequence(self):
        image = Image.new('RGB', (10, 10))
        self.assertEqual(read_image(FakeClipboard(), lambda: image), (image, 1))

    def test_busy_change_remains_pending(self):
        clip, poller = FakeClipboard(2), ClipboardPoller(1)
        self.assertIsNone(poller.poll(clip, True, 10))
        self.assertEqual(clip.format_reads, 0)
        self.assertEqual(poller.poll(clip, False, 11), 2)
        self.assertIsNone(poller.poll(clip, False, 20))

    def test_debounce_defers_instead_of_dropping(self):
        clip, poller = FakeClipboard(2), ClipboardPoller(1)
        self.assertEqual(poller.poll(clip, False, 10), 2)
        clip.seq = 3
        self.assertIsNone(poller.poll(clip, False, 11))
        self.assertEqual(poller.poll(clip, False, 13), 3)

    def test_latest_image_wins_and_new_text_cancels_pending(self):
        clip, poller = FakeClipboard(2), ClipboardPoller(1)
        poller.poll(clip, True, 10)
        clip.seq = 3
        self.assertEqual(poller.poll(clip, False, 11), 3)
        clip.seq, clip.image = 4, False
        self.assertIsNone(poller.poll(clip, False, 15))
        self.assertEqual(poller.handled, 4)

    def test_format_check_race_is_retried(self):
        clip, poller = FakeClipboard(2), ClipboardPoller(1)
        def has_image():
            clip.seq = 3
            return True
        clip.has_image = has_image
        self.assertIsNone(poller.poll(clip, False, 10))
        self.assertEqual(poller.poll(clip, False, 11), 3)

    def test_native_copy_checks_after_acquiring_lock(self):
        # Exercise actual copy method with fake Win32 functions, including a change
        # exactly during OpenClipboard. No real desktop or clipboard is touched.
        clipboard = object.__new__(WindowsClipboard)
        clipboard.user, clipboard.kernel = Mock(), Mock()
        buffer = ctypes.create_string_buffer(1000)
        clipboard.kernel.GlobalAlloc.return_value = 123
        clipboard.kernel.GlobalLock.return_value = ctypes.addressof(buffer)
        clipboard.user.CreateWindowExW.return_value = 456
        clipboard.user.GetClipboardSequenceNumber.return_value = 1
        def open_clipboard(_):
            clipboard.user.GetClipboardSequenceNumber.return_value = 2
            return True
        clipboard.user.OpenClipboard.side_effect = open_clipboard
        with self.assertRaises(ClipboardChanged):
            clipboard.copy_text('old OCR', 1)
        clipboard.user.EmptyClipboard.assert_not_called()
        clipboard.user.SetClipboardData.assert_not_called()
        clipboard.user.CloseClipboard.assert_called_once()
        clipboard.user.DestroyWindow.assert_called_once_with(456)
        clipboard.kernel.GlobalFree.assert_called_once_with(123)

    def test_success_transfers_unicode_memory_ownership(self):
        clipboard = object.__new__(WindowsClipboard)
        clipboard.user, clipboard.kernel = Mock(), Mock()
        buffer = ctypes.create_string_buffer(1000)
        clipboard.kernel.GlobalAlloc.return_value = 123
        clipboard.kernel.GlobalLock.return_value = ctypes.addressof(buffer)
        clipboard.user.CreateWindowExW.return_value = 456
        clipboard.user.GetClipboardSequenceNumber.return_value = 1
        clipboard.copy_text('שלום API 😀', 1)
        expected = ('שלום API 😀' + '\0').encode('utf-16-le')
        self.assertEqual(buffer.raw[:len(expected)], expected)
        clipboard.user.SetClipboardData.assert_called_once_with(13, 123)
        clipboard.kernel.GlobalFree.assert_not_called()
        clipboard.user.CloseClipboard.assert_called_once()

    def test_clipboard_busy_does_not_clear_content(self):
        clipboard = object.__new__(WindowsClipboard)
        clipboard.user, clipboard.kernel = Mock(), Mock()
        buffer = ctypes.create_string_buffer(1000)
        clipboard.kernel.GlobalAlloc.return_value = 123
        clipboard.kernel.GlobalLock.return_value = ctypes.addressof(buffer)
        clipboard.user.CreateWindowExW.return_value = 456
        clipboard.user.OpenClipboard.return_value = False
        with patch('clipboard_win.time.sleep'), self.assertRaisesRegex(RuntimeError, 'busy'):
            clipboard.copy_text('text', 1)
        clipboard.user.EmptyClipboard.assert_not_called()
        clipboard.user.CloseClipboard.assert_not_called()
        clipboard.kernel.GlobalFree.assert_called_once()

    def test_cli_change_during_ocr_preserves_new_content(self):
        clip = FakeClipboard()
        def extract(*args):
            clip.seq, clip.value = 2, 'new user content'
            return 'old OCR', {'word_count':2, 'low_confidence_words':[]}
        with patch.object(ocr, 'WindowsClipboard', return_value=clip), \
             patch.object(ocr, 'engine', return_value='fake'), patch.object(ocr, 'check_languages'), \
             patch.object(ocr.ImageGrab, 'grabclipboard', return_value=Image.new('RGB', (10, 10))), \
             patch.object(ocr, 'extract', side_effect=extract), \
             patch.object(sys, 'argv', ['ocr', '--clipboard', '--copy', '--expected-sequence', '1']), \
             redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as error:
            self.assertEqual(ocr.main(), 3)
        self.assertEqual(clip.value, 'new user content')
        self.assertEqual(output.getvalue(), '')
        self.assertIn('CLIPBOARD_CHANGED:', error.getvalue())


class EngineAndQualityTests(unittest.TestCase):
    def test_all_windows_install_locations(self):
        for key, suffix in [('ProgramFiles','Tesseract-OCR'), ('ProgramFiles(x86)','Tesseract-OCR'),
                            ('LOCALAPPDATA','Programs/Tesseract-OCR')]:
            with self.subTest(key=key), tempfile.TemporaryDirectory() as tmp:
                engine = Path(tmp) / suffix / 'tesseract.exe'
                engine.parent.mkdir(parents=True)
                engine.touch()
                with patch.dict(os.environ, {key:tmp}, clear=True), patch.object(ocr.shutil, 'which', return_value=None):
                    self.assertEqual(ocr.engine(), str(engine))

    def test_invalid_explicit_engine_does_not_silently_fallback(self):
        with self.assertRaises(RuntimeError):
            ocr.engine('/does-not-exist/ocr.exe')

    def test_missing_language_fails(self):
        with patch.object(ocr, 'run', return_value='Languages (1):\neng\n'):
            with self.assertRaisesRegex(RuntimeError, 'heb'):
                ocr.check_languages('engine', 'heb+eng')

    def test_models_loaded_separately(self):
        with patch.object(ocr, 'run', side_effect=['ok', RuntimeError('broken heb')]) as run:
            with self.assertRaisesRegex(RuntimeError, 'broken heb'):
                ocr.check_models('engine', 'eng+heb')
        self.assertEqual([c.args[0][c.args[0].index('-l')+1] for c in run.call_args_list], ['eng', 'heb'])

    def test_quality_warnings(self):
        report = {'word_count':10, 'low_confidence_words':[{}, {}, {}]}
        self.assertIn('low_confidence:30%', ocr.quality_warnings('normal text', report))
        self.assertIn('reversed_order', ocr.quality_warnings('םולש ןויסנ ךרד', {}))
        self.assertEqual(ocr.quality_warnings('בדיקת טקסט בעברית עם API תקין', {}), [])
        self.assertEqual(ocr.clean('\u202bשלום\u202c'), 'שלום')


class WatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader('watcher_test', str(ROOT/'clipboard-watcher.pyw'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.module = importlib.util.module_from_spec(spec)
        # Prevent test error events from creating a repository log.
        loader.exec_module(cls.module)

    def test_worker_binds_consent_and_reports_conflict(self):
        m = self.module
        result = SimpleNamespace(returncode=3, stdout=b'', stderr=b'CLIPBOARD_CHANGED:preserved')
        with patch.object(m, 'PYTHON', Path(sys.executable)), patch.object(m, '_results', queue.Queue()), \
             patch.object(m, '_log'), patch.object(m.subprocess, 'run', return_value=result) as run:
            m._run_ocr_bg(42)
            args = run.call_args.args[0]
            self.assertEqual(args[-2:], ['--expected-sequence', '42'])
            self.assertTrue(m._results.get_nowait()['changed'])

    def test_pump_offers_pending_image_after_result(self):
        m = self.module
        clip, poller = FakeClipboard(2), ClipboardPoller(1)
        results = queue.Queue(); results.put({'ok':True})
        def show(*args): m._busy = False
        with patch.object(m, '_busy', True), patch.object(m, '_clipboard', clip), \
             patch.object(m, '_poller', poller), patch.object(m, '_results', results), \
             patch.object(m, '_show_result', side_effect=show), patch.object(m, '_make_toast') as toast:
            root = Mock()
            m._pump(root)
            toast.assert_called_once_with(root, 2)
            root.after.assert_called_once()


@unittest.skipUnless(shutil.which('tesseract'), 'Tesseract is not installed')
class TesseractTests(unittest.TestCase):
    def test_corrupt_model_passes_listing_but_fails_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'heb.traineddata').write_bytes(b'X' * 3_100_000)
            ocr.check_languages(ocr.engine(), 'heb', tmp)
            with self.assertRaises(RuntimeError):
                ocr.check_models(ocr.engine(), 'heb', tmp)

    def test_cli_file_extraction_and_overwrite_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            image, output = Path(tmp)/'input.png', Path(tmp)/'result.txt'
            fixture = Image.new('RGB', (500, 100), 'white')
            ImageDraw.Draw(fixture).text((20, 20), 'TEST OCR 123', font=ImageFont.load_default(size=30), fill='black')
            fixture.save(image)
            command = [sys.executable, str(ROOT/'scripts/ocr.py'), '--image', str(image),
                       '--lang', 'eng', '--out', str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('TEST', output.read_text(encoding='utf-8'))
            original = output.read_bytes()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Refusing to overwrite', result.stderr)
            self.assertEqual(output.read_bytes(), original)

    def test_real_installed_models(self):
        langs = ocr.run([ocr.engine(), '--list-langs']).splitlines()[1:]
        self.assertIn('eng', langs)
        ocr.check_models(ocr.engine(), 'eng')
        if os.environ.get('CI') and os.name != 'nt':
            self.assertIn('heb', langs, 'Linux CI must test both language models')
        if 'heb' in langs:
            ocr.check_models(ocr.engine(), 'heb')


@unittest.skipUnless(os.name == 'nt' and os.environ.get('OCR_NATIVE_CLIPBOARD_TESTS') == '1',
                     'Native clipboard tests require explicit opt-in on an isolated Windows runner')
class NativeClipboardTests(unittest.TestCase):
    def test_unicode_roundtrip_and_stale_write(self):
        clipboard = WindowsClipboard()
        first = clipboard.sequence()
        clipboard.copy_text('שלום API 😀', first)
        with self.assertRaises(ClipboardChanged):
            clipboard.copy_text('must not overwrite', first)
        user = clipboard.user
        user.GetClipboardData.argtypes = [ctypes.c_uint]
        user.GetClipboardData.restype = ctypes.c_void_p
        self.assertTrue(user.OpenClipboard(None))
        try:
            memory = user.GetClipboardData(13)
            self.assertTrue(memory)
            pointer = clipboard.kernel.GlobalLock(memory)
            self.assertTrue(pointer)
            try:
                self.assertEqual(ctypes.wstring_at(pointer), 'שלום API 😀')
            finally:
                clipboard.kernel.GlobalUnlock(memory)
        finally:
            user.CloseClipboard()
        self.assertFalse(clipboard.has_image())


if __name__ == '__main__':
    unittest.main()
