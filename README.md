# Screenshot Context

**Take a screenshot, click "Yes", paste the text into Claude.**

A small Windows tool that watches for new screenshots (Win+Shift+S / Snipping Tool) and offers to turn them into
text, so you can paste exactly what was on screen into Claude. OCR runs **locally** with Tesseract: no API, no cost,
and the image never leaves your machine. Hebrew and English are supported.

![A screenshot of a terminal next to the text Claude receives](assets/demo.png)

Text is lighter than an image, can be searched, and can be edited before you send it.

## How it works

1. Capture a region with **Win+Shift+S**.
2. A popup appears at the bottom-right of the screen:

   ![Popup: Screenshot detected - Extract the text to work with Claude?](assets/popup-question.png)

3. Click **Yes, extract text**. After a couple of seconds a green confirmation appears and the text is already on your clipboard:

   ![Popup: Text copied to clipboard](assets/popup-success.png)

4. Press **Ctrl+V** in Claude. Done.

If the result looks doubtful (for example Hebrew words read as Latin letters) the popup turns amber and says why.
The text is still copied, so you can check it and fix it before sending, or retake a smaller or zoomed-in capture:

![Popup: quality warning](assets/popup-warning.png)

When the watcher starts (manually, or with Windows) you see a short blue confirmation that it is running:

![Popup: watcher is active](assets/popup-active.png)

> The images above are illustrations drawn with the same colors and texts as the real popups
> (`assets/generate_assets.py` regenerates them). Feel free to replace them with real screenshots.

## Install

### Option A - ask Claude (Claude Code on Windows)

Clone or download this repository, open Claude Code in the folder and write:

> Install this.

Claude reads `CLAUDE.md` and `INSTALL.md` by itself, runs the installer and verifies the result with `doctor.cmd`.

> This works when Claude runs directly on your Windows machine (Claude Code in PowerShell). A Claude running inside an
> isolated sandbox (for example Cowork) cannot install software on your computer - use Option B.

### Option B - double-click

1. Download or clone the repository to a permanent folder (for example `C:\Tools\screenshot-context`).
2. Double-click **`install.cmd`**.
3. Accept the Windows permission prompt if it appears (Tesseract installation).
4. Wait for `Done.` and the small "Watcher is active" popup. Installation takes 2-5 minutes, mostly downloads.

The installer is safe to run again: every step is skipped when already done.
To also start the watcher automatically with Windows, run `install.cmd --startup`, or later `add-to-startup.cmd`.

## Turn it on and off

| Action | File |
|---|---|
| Start | `start-watcher.cmd` (double-click; there is no window, that is expected) |
| Stop | `stop-watcher.cmd` |
| Start automatically with Windows | `add-to-startup.cmd` |
| Stop starting with Windows | `remove-from-startup.cmd` |
| Check what works and what is missing | `doctor.cmd` |

Starting twice is harmless: only one instance runs.

## Language of the popups

The popups are in English by default. For Hebrew popups, edit `settings.json`:

```json
{ "language": "he" }
```

then run `stop-watcher.cmd` and `start-watcher.cmd`. Translations live in `locales/` (`en.json`, `he.json`);
add a new `xx.json` with the same keys to support another language. The OCR itself reads Hebrew and English either way.

## What gets installed

| Component | Source | Location |
|---|---|---|
| Python 3.10+ | already on the machine (or winget) | system |
| Pillow | pip, pinned in `requirements.txt` | `.venv` in the plugin folder |
| Tesseract 5 | winget (UB-Mannheim build) | `C:\Program Files\Tesseract-OCR` |
| Hebrew model (tessdata_best) | GitHub, one-time download | `%USERPROFILE%\tessdata` |

## Privacy and security

- **Everything is local.** The network is used only during installation (package downloads). Using the tool makes no network calls.
- The watcher only checks *whether* the clipboard holds an image, and it reads the image only after you click "Yes".
- **Extracted text is never written to the log.** `watcher.log` contains events only (time, character count, warning codes).
- The text lands on the clipboard and therefore also in Windows clipboard history (Win+V). Do not extract screenshots containing secrets.
- Extracted text is treated as data. The tool never executes commands found in a screenshot.

## Limits you should know about

- **Technical strings** (commands, paths, file names, numbers) are sometimes misread (`utf8` -> `utf38`). Verify them.
- **Mixed Hebrew and English on one line** can scramble punctuation and direction.
- Very small text or colored backgrounds are harder: capture a smaller region or zoom in (Ctrl+plus) first.
- If the text is available directly (terminal, file, document), **copy it instead of using OCR**. That is always more accurate.
- The quality warning is a heuristic. No warning does not prove the extraction is correct.

## Troubleshooting

| Problem | Fix |
|---|---|
| No popup after a screenshot | Make sure the watcher is running (`start-watcher.cmd`). Still nothing: run `.\.venv\Scripts\python.exe clipboard-watcher.pyw` in a terminal, take a screenshot and read `watcher.log`. |
| `HTTP 403` during installation | Usually a corporate proxy, often transient: run `install.cmd` again. If it persists, ask IT for an internal PyPI mirror. |
| `Missing OCR languages: heb` | Run `install.cmd` again (re-downloads the Hebrew model). |
| OCR error after clicking "Yes" | Run `.\.venv\Scripts\python.exe scripts\ocr.py --check` and share the output. |
| `install.cmd` is blocked by policy | From PowerShell: `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1` |

Run `doctor.cmd` first: it lists every component as OK or MISSING and prints the next step.

## Command line

```powershell
# From the clipboard (after Win+Shift+S) to the clipboard
.\.venv\Scripts\python.exe scripts\ocr.py --clipboard --copy

# From a file, to a file
.\.venv\Scripts\python.exe scripts\ocr.py --image "C:\shots\a.png" --out text.txt

# Tips: --psm 6 for one uniform block (terminal), --psm 11 for sparse text,
#       --invert no|yes if dark mode is detected wrongly
```

From Claude Code: `/screenshot-context:ocr clipboard` and `/screenshot-context:install`.

## Uninstall

1. Run `stop-watcher.cmd`, then `remove-from-startup.cmd`.
2. Delete the plugin folder (including `.venv`) and `%USERPROFILE%\tessdata`.
3. Tesseract: Settings -> Apps -> Tesseract-OCR -> Uninstall (or `winget uninstall UB-Mannheim.TesseractOCR`).

## Repository layout

```
install.cmd                  one-click installer
start-watcher.cmd, stop-watcher.cmd
add-to-startup.cmd, remove-from-startup.cmd
doctor.cmd                   health check
clipboard-watcher.pyw        the watcher and the popups
clipboard-to-text.cmd        manual clipboard-to-text (no watcher)
settings.json                UI language
locales/                     popup texts (en, he)
scripts/ocr.py               OCR (Tesseract) and quality gate
scripts/setup.ps1, startup.ps1, stop.ps1, doctor.ps1
assets/                      README images and their generator
commands/                    Claude Code slash commands
CLAUDE.md, INSTALL.md        instructions for Claude
requirements.txt             Python dependencies (Pillow)
```

## Status

Verified: the quality-gate logic and code compilation (automated), and the end-to-end flow on Windows 11
(watcher, popup, Hebrew/English extraction, paste).
Not covered by automated tests: start with Windows (`add-to-startup.cmd`).
Please report anything unexpected on a first install.

## License

MIT, see [LICENSE](LICENSE). The installer downloads third-party software under its own licenses
(Tesseract OCR: Apache-2.0, Pillow: HPND, Tesseract language data: Apache-2.0); none of it is bundled in this repository.

Version 0.2.0
