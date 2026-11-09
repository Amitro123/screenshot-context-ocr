"""Offline screenshot OCR. No network calls or model API calls."""
import argparse
import copy
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
from PIL import Image, ImageDraw, ImageGrab, ImageOps, ImageStat
from clipboard_win import ClipboardChanged, WindowsClipboard, read_image
from output_checks import hebrew_check, preservation, table_text

HEBREW = re.compile(r'[\u0590-\u05FF]')
LATIN_OR_DIGIT = re.compile(r'[A-Za-z0-9]')
FINAL_FORMS = '\u05da\u05dd\u05df\u05e3\u05e5'  # Hebrew final letter forms
SEPARATORS = re.compile(r'[-\u05be"\'\u05f3\u05f4:/_.,;()\[\]{}<>=+*&|\\]')
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0


def run(command, timeout=90):
    result = subprocess.run(command, capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip())
    return result.stdout.decode('utf-8', errors='replace')


def engine(explicit=None):
    if explicit:
        candidates = [explicit]
    else:
        candidates = [shutil.which('tesseract')]
        for key, suffix in [('ProgramFiles', 'Tesseract-OCR'),
                            ('ProgramFiles(x86)', 'Tesseract-OCR'),
                            ('LOCALAPPDATA', 'Programs/Tesseract-OCR')]:
            if os.environ.get(key):
                candidates.append(str(Path(os.environ[key]) / suffix / 'tesseract.exe'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError('Install Tesseract 5 with eng and heb language data, or pass --tesseract PATH.')


def check_models(exe, langs, tessdata=None):
    """Load each requested model separately; a valid English model cannot hide broken Hebrew."""
    with tempfile.TemporaryDirectory(prefix='ocr-check-') as tmp:
        source = Path(tmp) / 'probe.png'
        probe = Image.new('RGB', (300, 80), 'white')
        ImageDraw.Draw(probe).text((10, 20), 'OCR model load check 123', fill='black')
        probe.save(source)
        for lang in langs.split('+'):
            cmd = [exe, str(source), 'stdout', '-l', lang, '--oem', '1', '--psm', '6']
            if tessdata:
                cmd += ['--tessdata-dir', tessdata]
            run(cmd)


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
        text = clean(base.with_suffix('.txt').read_text(encoding='utf-8')).strip()
        rows = list(csv.DictReader(io.StringIO(base.with_suffix('.tsv').read_text(encoding='utf-8')),
                                   delimiter='\t', quoting=csv.QUOTE_NONE))  # a word starting with " must not swallow rows
        words = [r for r in rows if r.get('level') == '5' and r.get('text', '').strip()]
        low = [{'text': r['text'], 'confidence': float(r['conf'])} for r in words if float(r['conf']) < 60]
        raw_text = text
        layout = {'status': 'not_requested', 'structure_verified': False}
        if getattr(args, 'table', False):
            text, layout = table_text(raw_text, words, args.table_direction)
        return text, {'_words': words,  # consumed (popped) by extract_with_retry; never serialized
                      'schema_version': 1, 'source': 'ocr', 'engine': 'tesseract',
                      'recognition_accuracy': 'not_verified',
                      'languages': args.lang, 'word_count': len(words), 'low_confidence_words': low,
                      'settings': {'scale': args.scale, 'psm': args.psm, 'invert': args.invert},
                      'image_size': list(image.size), 'table': layout,
                      'checks': {'hebrew': hebrew_check(raw_text),
                                 'preservation': preservation(raw_text, text)},
                      'note': 'Heuristics and output preservation are not verification against the image.'}


# ---------------------------------------------------------------- quality gate

COMMON_ACRONYMS = {
    'API', 'CPU', 'GPU', 'URL', 'SQL', 'AWS', 'GCP', 'JSON', 'HTML', 'CSS', 'PDF', 'QA', 'AI', 'ID', 'OK', 'UI', 'UX',
    'SSH', 'DNS', 'HTTP', 'CI', 'CD', 'PR', 'VM', 'IT', 'CIO', 'ROI', 'SDK', 'CLI', 'MCP', 'LLM', 'RAG', 'OCR', 'RTL',
    'LTR', 'TV', 'PC', 'DB', 'OS', 'IP', 'TCP', 'SSO', 'VPN', 'CSV', 'XML', 'YAML', 'GIT', 'NPM', 'PIP', 'RAM', 'SSD',
}
SHORT_UPPER = re.compile(r'^[A-Z]{2,4}[0-9]?$')      # NIN, ON, DY, WINN ...
SHORT_CAPITALIZED = re.compile(r'^[A-Z][a-z]$')       # Da, Yo ...
SHORT_LOWER = re.compile(r'^[a-z]{2}$')               # ee, rr, nr, pe ...
COMMON_LOWER = {'ok', 'id', 'to', 'in', 'on', 'of', 'vs', 'pc', 'ip', 'db', 'os', 'ui', 'ux', 'ci', 'cd', 'pr', 'vm',
                'it', 'is', 'as', 'at', 'be', 'by', 'do', 'if', 'me', 'my', 'no', 'or', 'so', 'up', 'we', 'go'}
BIDI_MARKS = re.compile('[‎‏‪-‮⁦-⁩]')  # invisible direction marks OCR inserts


def clean(text):
    """Drop invisible bidi control characters: they only add noise when the text is pasted into Claude."""
    return BIDI_MARKS.sub('', text)


def is_noise_token(token):
    if SHORT_UPPER.match(token):
        return token.upper().rstrip('0123456789') not in COMMON_ACRONYMS
    if SHORT_CAPITALIZED.match(token):
        return True
    return bool(SHORT_LOWER.match(token)) and token not in COMMON_LOWER


def latin_noise(text):
    """Short Latin tokens inside Hebrew-dominant lines: typical of Hebrew words misread as Latin."""
    noise = 0
    for line in text.splitlines():
        hebrew = len(HEBREW.findall(line))
        latin = len(re.findall(r'[A-Za-z]', line))
        if hebrew < 10 or hebrew < latin:
            continue
        for token in SEPARATORS.split(line.replace(' ', '-')):
            if is_noise_token(token):
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
    if s['mixed'] >= 2 and (s['mixed'] >= 3 or s['mixed'] / max(1, s['tokens']) > 0.04):
        out.append(f"mixed_tokens:{s['mixed']}")
    if s['final_start'] >= 3 and s['final_start'] > s['final_end']:
        out.append('reversed_order')
    script = hebrew_check(text)
    if script['suspicious_midword']:
        out.append('midword_final')
    if report.get('table', {}).get('status') == 'fallback':
        out.append('table_ambiguous')
    words = report.get('word_count', 0)
    low = len(report.get('low_confidence_words', []))
    if words >= 10 and low / words > 0.25:
        out.append(f'low_confidence:{round(100 * low / words)}%')
    return out


RETRY_SETTINGS = {'scale': 2, 'psm': 6}


HEBREW_ONLY = re.compile(r'^[^A-Za-z֐-׿]*[א-ת][^A-Za-z]*$')  # Hebrew + punctuation, no Latin
ASCII_TOKEN = re.compile(r'^(?=.*[A-Za-z])[A-Za-z0-9/._:+\-]{2,}$')  # /context, shift+tab, model:sonnet
MAX_SWAPS = 40
NOISE_TOLERANCE = 5     # a look-alike Latin token yields to a pure-Hebrew reading that is at most this much less sure
STRONG_HEBREW = 85      # other Latin/digit tokens yield only to a confident pure-Hebrew reading ...
HEBREW_MARGIN = 5       # ... that also beats the first reading by this margin
ENGLISH_MIN, ENGLISH_MARGIN, WEAK_HEBREW = 80, 30, 50


def _misread_candidate(token):
    """Short look-alike Latin cluster (DN, ANN, Op) or Hebrew glued to digits: a likely misread Hebrew word."""
    core = token.strip('.,:;!?()"\'')
    return is_noise_token(core) or bool(HEBREW.search(core) and re.search(r'\d', core))


def _english_candidate(token, conf):
    """Junk-looking Hebrew token: Hebrew letters glued to digits/slashes, or a low-confidence Hebrew word."""
    core = token.strip('.,:;!?()"\'')
    if HEBREW.search(core) and re.search(r'[\d/]', core):
        return True
    return bool(HEBREW_ONLY.match(core)) and conf < WEAK_HEBREW


def needs_second_opinion(text, words):
    """True if a Hebrew text still holds a look-alike or junk token a second language pass could settle."""
    return bool(HEBREW.search(text)) and any(
        _misread_candidate(clean(w['text']).strip()) or _english_candidate(clean(w['text']).strip(), float(w['conf']))
        for w in words)


def _read_again(exe, image, args, lang):
    other = copy.copy(args)
    other.lang = lang
    _, report = extract(exe, image, other)
    return [dict(w, text=clean(w['text']).strip()) for w in report.pop('_words', [])]


def _same_box(word, others):
    x, y, width, height = (int(word[k]) for k in ('left', 'top', 'width', 'height'))
    return [o for o in others
            if int(o['left']) < x + width and int(o['left']) + int(o['width']) > x
            and abs(int(o['top']) + int(o['height']) / 2 - (y + height / 2)) < height * 0.5]


def _replace_tokens(text, swaps):
    pieces, pos = [], 0
    for old, new in swaps:
        m = re.search(r'(?<!\S)' + re.escape(old) + r'(?!\S)', text[pos:])  # whole token only
        if m:
            pieces += [text[pos:pos + m.start()], new]
            pos += m.end()
    pieces.append(text[pos:])
    return ''.join(pieces)


def hebrew_second_opinion(exe, image, args, text, words):
    """Re-read the page with `-l heb` only (same scale/psm). A token that contains Latin letters or digits yields to
    the Hebrew-only reading of the same box when that reading is pure Hebrew and Tesseract is more sure of it:
    look-alike clusters (DN, ON) within NOISE_TOLERANCE points, any other Latin/digit token (anid, 921") only if the
    Hebrew reading is confident (STRONG_HEBREW) and better by HEBREW_MARGIN. Real English/code is read with low
    confidence by the Hebrew model and keeps its reading.

    Both readings are genuine Tesseract output: tokens are chosen, never edited or mapped.
    Returns (new_text, candidates, replaced).
    """
    heb_words = _read_again(exe, image, args, 'heb')
    swaps, candidates = [], 0
    for w in words:
        token = clean(w['text']).strip()
        if not token or not LATIN_OR_DIGIT.search(token):
            continue
        candidates += 1
        overlap = _same_box(w, heb_words)
        if not overlap or not all(HEBREW_ONLY.match(h['text']) for h in overlap):
            continue
        heb = sum(float(h['conf']) for h in overlap) / len(overlap)
        first = float(w['conf'])
        better = heb >= first - NOISE_TOLERANCE if is_noise_token(token.strip('.,:;!?()"\'')) \
            else heb >= STRONG_HEBREW and heb >= first + HEBREW_MARGIN
        if better:
            swaps.append((token, ' '.join(h['text'] for h in overlap)))
        if len(swaps) >= MAX_SWAPS:
            break
    return _replace_tokens(text, swaps), candidates, len(swaps)


def english_second_opinion(exe, image, args, text, words):
    """Mirror of hebrew_second_opinion with `-l eng` for the reverse error: English/code read as Hebrew-letter junk.

    Only junk-looking Hebrew tokens are candidates (see _english_candidate). One pure ASCII token (/context) at the
    same box replaces a mixed Hebrew+digit/slash token (never a real Hebrew word) when it is at most NOISE_TOLERANCE less sure; a plain Hebrew word is replaced
    only when it is weak (< WEAK_HEBREW) and the English reading is strong (>= ENGLISH_MIN, ENGLISH_MARGIN better).
    Returns (new_text, candidates, replaced).
    """
    eng_words = None
    swaps, candidates = [], 0
    for w in words:
        token = clean(w['text']).strip()
        first = float(w['conf'])
        if not token or not _english_candidate(token, first):
            continue
        if eng_words is None:
            eng_words = _read_again(exe, image, args, 'eng')
        candidates += 1
        overlap = _same_box(w, eng_words)
        if len(overlap) != 1 or not ASCII_TOKEN.match(overlap[0]['text']):
            continue
        eng = float(overlap[0]['conf'])
        mixed = bool(HEBREW.search(token) and re.search(r'[\d/]', token))
        if (eng >= first - NOISE_TOLERANCE) if mixed else (eng >= ENGLISH_MIN and eng >= first + ENGLISH_MARGIN):
            swaps.append((token, overlap[0]['text']))
        if len(swaps) >= MAX_SWAPS:
            break
    return _replace_tokens(text, swaps), candidates, len(swaps)


def extract_with_retry(exe, image, args, allow_retry):
    """Normal pass; if it has warnings, one second pass (scale 2, psm 6). Keep the one with fewer warnings.

    On a heb+eng read of Hebrew text that still has a `mixed_tokens` warning or a look-alike/junk token
    (needs_second_opinion), a `-l heb` pass and, only if junk-looking Hebrew tokens exist, a `-l eng` pass
    supply second opinions (hebrew_second_opinion, english_second_opinion): at most two extra full passes.
    All results are genuine Tesseract output: nothing is corrected, only chosen. Tie keeps the first.
    Everything extra is skipped when allow_retry is False.
    """
    text, report = extract(exe, image, args)
    warnings = quality_warnings(text, report) if text else []
    retry = {'used': False, 'chosen': 'first'}
    used_args = args
    if allow_retry and text and warnings and not getattr(args, 'table', False):
        retry['used'] = True
        second_args = copy.copy(args)
        second_args.scale, second_args.psm = RETRY_SETTINGS['scale'], RETRY_SETTINGS['psm']
        try:
            text2, report2 = extract(exe, image, second_args)
            warnings2 = quality_warnings(text2, report2) if text2 else None
        except (RuntimeError, ValueError, OSError, subprocess.SubprocessError):
            warnings2 = None
        if warnings2 is not None and len(warnings2) < len(warnings):
            text, report, warnings = text2, report2, warnings2
            used_args = second_args
            retry['chosen'] = 'second'
    words = report.get('_words')
    if (allow_retry and text and words and not getattr(args, 'table', False)
            and 'heb' in args.lang and args.lang != 'heb' and 'eng' in args.lang
            and (any(w.startswith('mixed_tokens') for w in warnings) or needs_second_opinion(text, words))):
        changed = False
        for name, opinion in (('hebrew_pass', hebrew_second_opinion), ('english_pass', english_second_opinion)):
            try:
                new_text, candidates, replaced = opinion(exe, image, used_args, text, words)
            except (RuntimeError, ValueError, OSError, subprocess.SubprocessError):
                new_text, candidates, replaced = text, 0, 0
            retry[name] = {'candidates': candidates, 'replaced': replaced}
            if replaced:
                text, changed = new_text, True
        if changed:
            report['checks'] = {'hebrew': hebrew_check(text), 'preservation': preservation(text, text)}
            warnings = quality_warnings(text, report)
    report.pop('_words', None)
    report['retry'] = retry
    return text, report, warnings


def main():
    p = argparse.ArgumentParser(description=__doc__)
    src = p.add_mutually_exclusive_group()
    src.add_argument('--image', type=Path)
    src.add_argument('--clipboard', action='store_true')
    p.add_argument('--check', action='store_true')
    p.add_argument('--find-engine', action='store_true')
    p.add_argument('--expected-sequence', type=int, help=argparse.SUPPRESS)
    p.add_argument('--lang', choices=['eng', 'heb', 'heb+eng', 'eng+heb'], default='heb+eng')
    p.add_argument('--psm', type=int, choices=[3, 6, 11], default=None)  # effective default 3
    p.add_argument('--scale', type=int, choices=[1, 2, 3], default=None)  # effective default 3
    p.add_argument('--invert', choices=['auto', 'yes', 'no'], default='auto')
    p.add_argument('--tesseract')
    p.add_argument('--tessdata')
    p.add_argument('--out', type=Path)
    p.add_argument('--report', type=Path)
    p.add_argument('--copy', action='store_true')
    p.add_argument('--table', action='store_true', help='Infer a simple table as TSV; fall back to raw text if ambiguous.')
    p.add_argument('--table-direction', choices=['auto', 'ltr', 'rtl'], default='auto')
    p.add_argument('--no-retry', action='store_true',
                   help='Do not re-run OCR with other settings (scale 2, psm 6) when the first pass has warnings.')
    args = p.parse_args()
    allow_retry = not args.no_retry and args.scale is None and args.psm is None
    args.scale = 3 if args.scale is None else args.scale
    args.psm = 3 if args.psm is None else args.psm
    if not args.tessdata:
        user_tessdata = Path.home() / 'tessdata'
        if (user_tessdata / 'heb.traineddata').is_file():
            args.tessdata = str(user_tessdata)
    try:
        exe = engine(args.tesseract)
        if args.find_engine:
            print(exe)
            return 0
        check_languages(exe, args.lang, args.tessdata)
        if args.check:
            check_models(exe, args.lang, args.tessdata)
            print('OK: Tesseract and requested languages available.')
            return 0
        if not args.image and not args.clipboard:
            p.error('Provide --image PATH or --clipboard.')
        for output in [args.out, args.report]:
            if output and (output.exists() or (args.image and output.resolve() == args.image.resolve())):
                raise ValueError('Refusing to overwrite: ' + str(output))
        if args.out and args.report and args.out.resolve() == args.report.resolve():
            raise ValueError('--out and --report must differ.')
        if args.expected_sequence is not None and not args.clipboard:
            p.error('--expected-sequence requires --clipboard.')
        clipboard = WindowsClipboard() if args.copy or (args.clipboard and os.name == 'nt') else None
        sequence = clipboard.sequence() if clipboard else None
        if args.image:
            with Image.open(args.image) as opened:
                image = opened.copy()
        elif clipboard:
            image, sequence = read_image(clipboard, ImageGrab.grabclipboard, args.expected_sequence)
        else:
            image = ImageGrab.grabclipboard()
        if not isinstance(image, Image.Image):
            raise ValueError('Clipboard has no image. Capture a region with Win+Shift+S first.')

        text, report, warnings = extract_with_retry(exe, image, args, allow_retry)
        if not text:
            raise ValueError('No text detected. Crop/zoom the screenshot or try --psm 6.')
        report['warnings'] = warnings
        report['quality_status'] = 'review_required' if warnings else 'no_issue_detected_accuracy_unverified'
        if args.out:
            args.out.write_text(text + '\n', encoding='utf-8')
        if args.report:
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        if args.copy:
            clipboard.copy_text(text, sequence)
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        print(text)
        for warning in warnings:
            print('WARN:' + warning, file=sys.stderr)
        print(f"OCR: {report['word_count']} words; {len(report['low_confidence_words'])} below confidence 60. Verify technical literals.", file=sys.stderr)
        return 0
    except ClipboardChanged as exc:
        print('CLIPBOARD_CHANGED:' + str(exc), file=sys.stderr)
        return 3
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print('OCR error: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
