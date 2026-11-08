"""Offline screenshot OCR. No network calls or model API calls."""
import argparse
import base64
import csv
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from PIL import Image, ImageGrab, ImageOps, ImageStat

HEBREW = re.compile(r'[\u0590-\u05FF]')
LATIN_OR_DIGIT = re.compile(r'[A-Za-z0-9]')
FINAL_FORMS = '\u05da\u05dd\u05df\u05e3\u05e5'  # ך ם ן ף ץ
SEPARATORS = re.compile(r'[-\u05be"\'\u05f3\u05f4:/_.,;()\[\]{}<>=+*&|\\]')
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0


def run(command, timeout=90):
    result = subprocess.run(command, capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip())
    return result.stdout.decode('utf-8', errors='replace')


def engine(explicit=None):
    candidate = explicit or shutil.which('tesseract')
    if not candidate and os.name == 'nt':
        candidate = str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Tesseract-OCR/tesseract.exe')
    if not candidate or not Path(candidate).is_file():
        raise RuntimeError('Install Tesseract 5 with eng and heb language data, or pass --tesseract PATH.')
    return candidate


def check_languages(exe, langs, tessdata=None):
    cmd = [exe, '--list-langs']
    if tessdata:
        cmd += ['--tessdata-dir', tessdata]
    available = set(run(cmd).splitlines()[1:])
    missing = set(langs.split('+')) - available
    if missing:
        raise RuntimeError('Missing OCR languages: ' + ', '.join(sorted(missing)) + '. Install their .traineddata files; no silent English fallback.')


def flatten(image):
    image.load()
    rgba = image.convert('RGBA')
    background = Image.new('RGBA', rgba.size, 'white')
    background.alpha_composite(rgba)
    return background.convert('RGB')


def preprocess(image, scale, invert):
    image.load()
    if image.width * image.height * scale * scale > 80_000_000:
        raise ValueError('Image too large. Crop it or lower --scale.')
    gray = flatten(image).convert('L')
    if invert == 'yes' or (invert == 'auto' and ImageStat.Stat(gray).mean[0] < 100):
        gray = ImageOps.invert(gray)
    return ImageOps.expand(gray.resize((gray.width * scale, gray.height * scale), Image.Resampling.LANCZOS), border=20, fill=255)


def extract(exe, image, args):
    with tempfile.TemporaryDirectory(prefix='screenshot-ocr-') as tmp:
        source = Path(tmp) / 'input.png'
        base = Path(tmp) / 'result'
        preprocess(image, args.scale, args.invert).save(source)
        cmd = [exe, str(source), str(base), '-l', args.lang, '--oem', '1', '--psm', str(args.psm)]
        if args.tessdata:
            cmd += ['--tessdata-dir', args.tessdata]
        cmd += ['-c', 'tessedit_create_txt=1', '-c', 'tessedit_create_tsv=1']
        run(cmd)
        text = base.with_suffix('.txt').read_text(encoding='utf-8').strip()
        rows = list(csv.DictReader(io.StringIO(base.with_suffix('.tsv').read_text(encoding='utf-8')), delimiter='\t'))
        words = [r for r in rows if r.get('level') == '5' and r.get('text', '').strip()]
        low = [{'text': r['text'], 'confidence': float(r['conf'])} for r in words if float(r['conf']) < 60]
        return text, {'languages': args.lang, 'word_count': len(words), 'low_confidence_words': low,
                      'note': 'Confidence is not correctness. Verify commands, paths, numbers and mixed RTL/LTR text.'}


# ---------------------------------------------------------------- quality gate

COMMON_ACRONYMS = {
    'API', 'CPU', 'GPU', 'URL', 'SQL', 'AWS', 'GCP', 'JSON', 'HTML', 'CSS', 'PDF', 'QA', 'AI', 'ID', 'OK', 'UI', 'UX',
    'SSH', 'DNS', 'HTTP', 'CI', 'CD', 'PR', 'VM', 'IT', 'CIO', 'ROI', 'SDK', 'CLI', 'MCP', 'LLM', 'RAG', 'OCR', 'RTL',
    'LTR', 'TV', 'PC', 'DB', 'OS', 'IP', 'TCP', 'SSO', 'VPN', 'CSV', 'XML', 'YAML', 'GIT', 'NPM', 'PIP', 'RAM', 'SSD',
}
SHORT_LATIN = re.compile(r'^[A-Za-z]{2,3}[0-9]?$')


def latin_noise(text):
    """Short Latin tokens inside Hebrew-dominant lines: typical of Hebrew words misread as Latin."""
    noise = 0
    for line in text.splitlines():
        hebrew = len(HEBREW.findall(line))
        latin = len(re.findall(r'[A-Za-z]', line))
        if hebrew < 10 or hebrew < latin:
            continue
        for token in SEPARATORS.split(line.replace(' ', '-')):
            if SHORT_LATIN.match(token) and token.upper().rstrip('0123456789') not in COMMON_ACRONYMS:
                noise += 1
    return noise


def suspicion(text):
    """Cheap, offline heuristics for garbled Hebrew OCR output."""
    tokens = text.split()
    mixed = final_start = final_end = 0
    for token in tokens:
        for part in SEPARATORS.split(token):
            if not part or not HEBREW.search(part):
                continue
            if LATIN_OR_DIGIT.search(part):
                mixed += 1  # Hebrew glued to Latin/digits, e.g. a misread word
                continue
            letters = [c for c in part if HEBREW.match(c)]
            if len(letters) >= 2:
                final_start += letters[0] in FINAL_FORMS  # final forms never start a word
                final_end += letters[-1] in FINAL_FORMS
    mixed += latin_noise(text)
    return {'tokens': len(tokens), 'mixed': mixed, 'final_start': final_start, 'final_end': final_end}


def suspicion_score(text):
    s = suspicion(text)
    return (s['mixed'] + 2 * s['final_start']) / max(1, s['tokens'])


def quality_warnings(text, report):
    """Return warning codes like 'mixed_tokens:3'. Empty list means no concern."""
    out = []
    s = suspicion(text)
    if s['mixed'] >= 2 and s['mixed'] / max(1, s['tokens']) > 0.04:
        out.append(f"mixed_tokens:{s['mixed']}")
    if s['final_start'] >= 3 and s['final_start'] > s['final_end']:
        out.append('reversed_order')
    words = report.get('word_count', 0)
    low = len(report.get('low_confidence_words', []))
    if words >= 10 and low / words > 0.25:
        out.append(f'low_confidence:{round(100 * low / words)}%')
    return out


# ------------------------------------------------------------ Windows built-in OCR

def windows_ocr(image, lang_tags='he-IL,he'):
    """Windows.Media.Ocr via PowerShell. Local only; needs the Hebrew language pack."""
    if os.name != 'nt':
        raise RuntimeError('Windows OCR is only available on Windows.')
    script = Path(__file__).with_name('winocr.ps1').read_text(encoding='utf-8')
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    with tempfile.TemporaryDirectory(prefix='winocr-') as tmp:
        source = Path(tmp) / 'input.png'
        rgb = flatten(image)
        if max(rgb.size) < 2000:
            rgb = rgb.resize((rgb.width * 2, rgb.height * 2), Image.Resampling.LANCZOS)
        rgb.save(source)
        env = os.environ.copy()
        env['WINOCR_IMAGE'] = str(source)
        env['WINOCR_LANG'] = lang_tags
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded],
                                env=env, capture_output=True, timeout=60, creationflags=CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip()[:300])
    return result.stdout.decode('utf-8', errors='replace').strip()


def windows_ocr_available():
    try:
        windows_ocr(Image.new('RGB', (64, 64), 'white'))
        return True
    except Exception:
        return False


def copy_text(text):
    if os.name != 'nt':
        raise RuntimeError('--copy is currently supported on native Windows only; use --out elsewhere.')
    # Pass text through a temporary UTF-8 file, never as executable PowerShell code.
    with tempfile.TemporaryDirectory(prefix='ocr-copy-') as tmp:
        path = Path(tmp) / 'text.txt'
        path.write_text(text, encoding='utf-8')
        env = os.environ.copy()
        env['SCREENSHOT_OCR_COPY_FILE'] = str(path)
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                        "$ErrorActionPreference='Stop'; Set-Clipboard -Value ([IO.File]::ReadAllText($env:SCREENSHOT_OCR_COPY_FILE, [Text.Encoding]::UTF8))"],
                       env=env, check=True, capture_output=True, timeout=20, creationflags=CREATE_NO_WINDOW)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group()
    src.add_argument('--image', type=Path)
    src.add_argument('--clipboard', action='store_true')
    p.add_argument('--check', action='store_true')
    p.add_argument('--lang', choices=['eng', 'heb', 'heb+eng', 'eng+heb'], default='heb+eng')
    p.add_argument('--engine', choices=['tesseract', 'windows', 'auto'], default='tesseract',
                   help='auto = Tesseract, falling back to Windows OCR when the quality gate fires')
    p.add_argument('--psm', type=int, choices=[3, 6, 11], default=3)
    p.add_argument('--scale', type=int, choices=[1, 2, 3], default=3)
    p.add_argument('--invert', choices=['auto', 'yes', 'no'], default='auto')
    p.add_argument('--tesseract')
    p.add_argument('--tessdata')
    p.add_argument('--out', type=Path)
    p.add_argument('--report', type=Path)
    p.add_argument('--copy', action='store_true')
    args = p.parse_args()
    if not args.tessdata:
        user_tessdata = Path.home() / 'tessdata'
        if (user_tessdata / 'heb.traineddata').is_file():
            args.tessdata = str(user_tessdata)
    try:
        exe = None
        if args.engine != 'windows':
            exe = engine(args.tesseract)
            check_languages(exe, args.lang, args.tessdata)
        if args.check:
            if exe:
                print('OK: Tesseract and requested languages available.')
            print('INFO: Windows OCR fallback (Hebrew) is ' +
                  ('available.' if windows_ocr_available() else 'not available (optional: add the Hebrew language pack in Windows settings).'))
            return 0
        if not args.image and not args.clipboard:
            p.error('Provide --image PATH or --clipboard.')
        for output in [args.out, args.report]:
            if output and (output.exists() or (args.image and output.resolve() == args.image.resolve())):
                raise ValueError('Refusing to overwrite: ' + str(output))
        if args.out and args.report and args.out.resolve() == args.report.resolve():
            raise ValueError('--out and --report must differ.')
        image = Image.open(args.image) if args.image else ImageGrab.grabclipboard()
        if not isinstance(image, Image.Image):
            raise ValueError('Clipboard has no image. Capture a region with Win+Shift+S first.')

        engine_used = 'tesseract'
        if args.engine == 'windows':
            text = windows_ocr(image)
            report = {'languages': 'windows', 'word_count': len(text.split()), 'low_confidence_words': [],
                      'note': 'Windows OCR gives no confidence values. Verify commands, paths, numbers.'}
            engine_used = 'windows'
        else:
            text, report = extract(exe, image, args)
            if args.engine == 'auto' and quality_warnings(text, report):
                try:
                    alt = windows_ocr(image)
                    if alt and suspicion_score(alt) < suspicion_score(text):
                        text, engine_used = alt, 'windows'
                        report = {'languages': 'windows', 'word_count': len(alt.split()), 'low_confidence_words': [],
                                  'note': 'Windows OCR gives no confidence values. Verify commands, paths, numbers.'}
                except Exception as exc:  # fallback is best-effort; keep the Tesseract result
                    print('NOTE: Windows OCR fallback unavailable: ' + str(exc), file=sys.stderr)
        if not text:
            raise ValueError('No text detected. Crop/zoom the screenshot or try --psm 6.')
        warnings = quality_warnings(text, report)
        if args.out:
            args.out.write_text(text + '\n', encoding='utf-8')
        if args.report:
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if args.copy:
            copy_text(text)
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        print(text)
        print('ENGINE:' + engine_used, file=sys.stderr)
        for warning in warnings:
            print('WARN:' + warning, file=sys.stderr)
        print(f"OCR: {report['word_count']} words; {len(report['low_confidence_words'])} below confidence 60. Verify technical literals.", file=sys.stderr)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('OCR error: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
