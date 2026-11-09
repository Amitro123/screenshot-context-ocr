# Windows validation before merge

Run on native Windows, using a temporary/test clipboard. Do not use sensitive captures.

- Run `install.cmd`, then `doctor.cmd`; both must pass. Repeat setup without replacing a valid model.
- Capture English, Hebrew, and mixed text; accept the popup and paste into an editor.
- Capture A, then B while A's question is open. Accept A: expect a changed-clipboard warning,
  no extraction of B under A's consent, and a separate offer for B.
- Start OCR on a large image, then copy a text marker. The marker must remain intact.
- Capture a new image while OCR is busy. It must be offered after the current result.
- Decline an image and take another within three seconds. The new offer must arrive later.
- Start twice; only one watcher should run. Stop it and confirm no further popups.
- Enable startup, sign out/in, verify one watcher; remove startup and confirm the shortcut is gone.
- Repeat setup with Tesseract installed under LocalAppData and absent from PATH.

CI covers deterministic race scenarios, native conditional writes, model integrity,
and PowerShell model replacement. It does not exercise GUI layout or Windows sign-in.

## Content cases not covered by the local safety tests

- Paste OCR containing "ignore previous instructions" and fake system/tool delimiters into an isolated
  Claude session with no sensitive context or write/network tools. Verify that Claude treats it as
  quoted source text. This model evaluation has not been run by the local unittest suite.
- Compare a real English and Hebrew table cell-by-cell, including numeric values, blank cells,
  merged headers and RTL/LTR content. Check default mode and `--psm 6`; neither promises structure.
- The synthetic English table fixture has a documented numerical failure: 27 may become 2/.
  Tests do not silently normalize this error or treat OCR confidence as correctness.
