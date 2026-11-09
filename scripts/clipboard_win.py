"""Windows clipboard access. Check and replace under one clipboard lock."""
import ctypes
from ctypes import wintypes as w
import os
import time


class ClipboardChanged(RuntimeError):
    """The screenshot is no longer the current clipboard item."""


class WindowsClipboard:
    def __init__(self):
        if os.name != 'nt':
            raise RuntimeError('Clipboard protection requires native Windows Python.')
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = [
            (self.user, 'GetClipboardSequenceNumber', [], w.DWORD),
            (self.user, 'IsClipboardFormatAvailable', [w.UINT], w.BOOL),
            (self.user, 'RegisterClipboardFormatW', [w.LPCWSTR], w.UINT),
            (self.user, 'CreateWindowExW', [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
             ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
             w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID], w.HWND),
            (self.user, 'DestroyWindow', [w.HWND], w.BOOL),
            (self.user, 'OpenClipboard', [w.HWND], w.BOOL),
            (self.user, 'CloseClipboard', [], w.BOOL),
            (self.user, 'EmptyClipboard', [], w.BOOL),
            (self.user, 'SetClipboardData', [w.UINT, w.HANDLE], w.HANDLE),
            (self.kernel, 'GlobalAlloc', [w.UINT, ctypes.c_size_t], w.HGLOBAL),
            (self.kernel, 'GlobalLock', [w.HGLOBAL], w.LPVOID),
            (self.kernel, 'GlobalUnlock', [w.HGLOBAL], w.BOOL),
            (self.kernel, 'GlobalFree', [w.HGLOBAL], w.HGLOBAL),
        ]
        for dll, name, args, result in signatures:
            function = getattr(dll, name)
            function.argtypes, function.restype = args, result
        self.png_format = self.user.RegisterClipboardFormatW('PNG')

    def sequence(self):
        seq = self.user.GetClipboardSequenceNumber()
        if not seq:
            raise RuntimeError('Cannot read the clipboard sequence number.')
        return seq

    def has_image(self):
        # Metadata only: no pixel retrieval or decoding before consent.
        return any(self.user.IsClipboardFormatAvailable(fmt)
                   for fmt in (2, 8, 17, self.png_format) if fmt)

    def copy_text(self, text, expected_sequence):
        data = (text + '\0').encode('utf-16-le')
        memory = self.kernel.GlobalAlloc(0x0002, len(data))  # GMEM_MOVEABLE
        if not memory:
            raise ctypes.WinError(ctypes.get_last_error())
        window = None
        opened = False
        try:
            pointer = self.kernel.GlobalLock(memory)
            if not pointer:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                ctypes.memmove(pointer, data, len(data))
            finally:
                self.kernel.GlobalUnlock(memory)
            # EmptyClipboard needs a non-null owner for SetClipboardData.
            # STATIC is a built-in window class; HWND_MESSAGE avoids a visible UI.
            window = self.user.CreateWindowExW(0, 'STATIC', '', 0, 0, 0, 0, 0,
                                                w.HWND(-3), None, None, None)
            if not window:
                raise ctypes.WinError(ctypes.get_last_error())
            for _ in range(20):
                if self.user.OpenClipboard(window):
                    opened = True
                    break
                time.sleep(0.025)
            if not opened:
                raise RuntimeError('Clipboard is busy. Please try again.')
            # Atomic with respect to other clipboard writers: compare AFTER locking.
            current = self.sequence()
            if current != expected_sequence:
                raise ClipboardChanged('Clipboard changed (expected sequence %s, now %s); '
                                       'newer content was preserved. Run OCR again.'
                                       % (expected_sequence, current))
            if not self.user.EmptyClipboard():
                raise ctypes.WinError(ctypes.get_last_error())
            if not self.user.SetClipboardData(13, memory):  # CF_UNICODETEXT
                raise ctypes.WinError(ctypes.get_last_error())
            memory = None  # Windows owns the allocation after a successful transfer.
        finally:
            if opened:
                self.user.CloseClipboard()
            if window:
                self.user.DestroyWindow(window)
            if memory:
                self.kernel.GlobalFree(memory)


def read_image(clipboard, grab, expected_sequence=None):
    """Bind an image to a sequence; refuse changes before or during pixel retrieval."""
    sequence = clipboard.sequence() if expected_sequence is None else expected_sequence
    current = clipboard.sequence()
    if current != sequence:
        raise ClipboardChanged('Clipboard changed before extraction (expected sequence %s, now %s); '
                               'capture or confirm the new image.' % (sequence, current))
    image = grab()
    current = clipboard.sequence()
    if current != sequence:
        raise ClipboardChanged('Clipboard changed while reading (expected sequence %s, now %s); '
                               'newer content was preserved.' % (sequence, current))
    return image, sequence


class ClipboardPoller:
    """Offer the latest stable clipboard image without consuming busy events.

    An item is offered only after its sequence number stayed unchanged for
    `settle` seconds: the Windows 11 Snipping Tool / clipboard history may bump
    the sequence several times after an image appears, which would make an
    early offer stale before the user answers.
    """
    def __init__(self, sequence, debounce=3.0, settle=1.0, log=None):
        self.handled = sequence
        self.last_offer = float('-inf')
        self.debounce = debounce
        self.settle = settle
        self.log = log
        self.pending = None        # sequence currently settling
        self.pending_since = 0.0   # when it was first seen

    def poll(self, clipboard, busy, now):
        if busy:
            return None
        sequence = clipboard.sequence()
        if sequence == self.handled:
            self.pending = None
            return None
        if sequence != self.pending:
            if self.log:
                self.log('clipboard sequence %s -> %s' % (self.pending or self.handled, sequence))
            self.pending, self.pending_since = sequence, now
            return None  # new or still-changing item: wait for it to settle
        if now - self.pending_since < self.settle or now - self.last_offer < self.debounce:
            return None
        is_image = clipboard.has_image()
        if clipboard.sequence() != sequence:
            return None  # Retry a stable item on the next poll.
        self.handled, self.pending = sequence, None
        if is_image:
            self.last_offer = now
            return sequence
        return None
