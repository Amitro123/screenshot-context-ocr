# Screenshot Context

**צילמת מסך? קפצה שאלה: "לחלץ את הטקסט לעבודה עם קלוד?" - לחיצה אחת, והטקסט בלוח, מוכן להדבקה.**

חילוץ טקסט (עברית ואנגלית) מצילומי מסך, מקומי לגמרי: בלי API, בלי עלות, בלי שליחת התמונה לשום מקום.
טקסט הוא זול ומדויק יותר לקלוד מאשר תמונה, ואפשר לערוך אותו לפני השליחה.

## איך זה נראה

1. מצלמים אזור עם **Win+Shift+S** (Snipping Tool).
2. בפינה הימנית-תחתונה קופצת שאלה: **"האם לחלץ את הטקסט לעבודה עם קלוד?"**
3. לוחצים **"כן, חלץ טקסט"**. תוך שניות מופיע אישור ירוק, והטקסט כבר בלוח.
4. **Ctrl+V** בתוך קלוד. זהו.

אם איכות החילוץ חשודה (למשל עברית שנקראה כרצף אותיות לטיניות), תופיע אזהרה כתומה ובה סיבה.
במקרה כזה הכלי מנסה אוטומטית גם את מנוע ה-OCR של Windows ובוחר את התוצאה הטובה יותר.

## התקנה

### דרך א' - לבקש מקלוד (Claude Code)
פתח את Claude Code בתיקיית הפלאגין והדבק:

> תתקין את זה.

(קלוד קורא לבד את `CLAUDE.md` ו-`INSTALL.md` שבתיקייה. בסיום הוא מריץ `doctor.cmd` כדי לוודא שהכול תקין.)

> **שים לב:** זה עובד כש-Claude רץ ישירות על ה-Windows שלך (Claude Code ב-PowerShell). Claude שרץ בתוך
> סביבה מבודדת (כמו Cowork) לא יכול להתקין על המחשב, ויפנה אותך לדרך ב'.

### דרך ב' - לחיצה כפולה (לכולם)
1. חלץ את ה-ZIP לתיקייה קבועה (למשל `C:\Tools\screenshot-context`).
2. לחץ פעמיים על **`install.cmd`**.
3. אשר את בקשת ההרשאה של Windows אם היא מופיעה (התקנת Tesseract).
4. חכה לשורה `Done.` ולחלון קטן "ה-watcher פעיל". ההתקנה לוקחת 2-5 דקות, בעיקר הורדות.

ההתקנה בטוחה להרצה חוזרת. אם משהו נכשל, מריצים שוב.

**להפעלה אוטומטית עם כל כניסה ל-Windows:** לחץ פעמיים על `add-to-startup.cmd` (אחרי ההתקנה).

## הדלקה וכיבוי

| פעולה | קובץ |
|---|---|
| להדליק | `start-watcher.cmd` (לחיצה כפולה; אין חלון, זה תקין) |
| לכבות | `stop-watcher.cmd` |
| להפעיל עם Windows | `add-to-startup.cmd` |
| לבטל הפעלה עם Windows | `remove-from-startup.cmd` |
| לבדוק מה תקין ומה חסר | `doctor.cmd` |

הדלקה כפולה בטוחה: רק מופע אחד רץ.

## מה מותקן ולאן

| רכיב | מקור | מיקום |
|---|---|---|
| Python 3.10+ | קיים במחשב (או winget) | מערכת |
| Pillow | pip, לפי `requirements.txt` | `.venv` בתיקיית הפלאגין |
| Tesseract 5 | winget (UB-Mannheim) | `C:\Program Files\Tesseract-OCR` |
| מודל עברית (tessdata_best) | GitHub, הורדה חד-פעמית | `%USERPROFILE%\tessdata` |
| OCR של Windows (אופציונלי) | מובנה ב-Windows | דורש חבילת שפה עברית בהגדרות |

## פרטיות ואבטחה

- **הכול מקומי.** רשת נדרשת רק בהתקנה (הורדת החבילות). בזמן שימוש אין שום קריאת רשת.
- ה-watcher בודק רק *אם* בלוח יש תמונה, ופועל רק אחרי שאישרת בלחיצה. תמונה שלא אושרה לא נקראת.
- הטקסט המחולץ **לא נשמר בלוג**. `watcher.log` מכיל רק אירועים (זמן, מנוע, מספר תווים).
- הטקסט נכנס ללוח ובפועל נשאר שם, גם בהיסטוריית הלוח של Windows (Win+V). אל תחלץ צילום עם סיסמאות או מידע רגיש.
- הטקסט המחולץ הוא נתון בלבד. כלי ה-OCR לא מריץ פקודות ולא מפרש הוראות מתוך הצילום.

## מגבלות (חשוב לדעת)

- **מזהים טכניים** (פקודות, נתיבים, שמות קבצים, מספרים) נקראים לפעמים לא נכון (`utf8` -> `utf38`). בדוק אותם.
- **עברית משולבת באנגלית באותה שורה** עלולה לשבש סימני פיסוק וכיווניות.
- טקסט קטן מאוד או ברקע צבעוני מתחלף בקלות: צלם אזור קטן יותר או הגדל (Ctrl+פלוס) לפני הצילום.
- אם הטקסט זמין ישירות (טרמינל, קובץ, מסמך), **העתק אותו במקום OCR**. זה תמיד מדויק יותר.
- הסימון "איכות חשודה" הוא היוריסטיקה: היעדר אזהרה אינו הוכחה שהחילוץ מדויק.

## פתרון תקלות

| בעיה | פתרון |
|---|---|
| לא קופצת שאלה אחרי צילום | ודא שה-watcher רץ (`start-watcher.cmd`). אם עדיין לא, הרץ בטרמינל: `.\.venv\Scripts\python.exe clipboard-watcher.pyw` וקרא את `watcher.log`. |
| `HTTP 403` בהתקנה | חסימת פרוקסי ארגוני, לרוב זמנית: הרץ שוב `install.cmd`. אם נמשך, בקש מ-IT mirror פנימי של PyPI. |
| `Missing OCR languages: heb` | הרץ שוב `install.cmd` (מוריד מחדש את מודל העברית). |
| שגיאת OCR אחרי "כן" | הרץ `.\.venv\Scripts\python.exe scripts\ocr.py --check` והעבר את הפלט. |
| `install.cmd` נחסם על ידי מדיניות | הרץ מ-PowerShell: `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1` |

## שימוש מתקדם (CLI)

```powershell
# מהלוח (אחרי Win+Shift+S), עם נפילה אוטומטית ל-OCR של Windows אם האיכות חשודה
.\.venv\Scripts\python.exe scripts\ocr.py --clipboard --copy --engine auto

# מקובץ, אל קובץ
.\.venv\Scripts\python.exe scripts\ocr.py --image "C:\shots\a.png" --out text.txt

# טיפים: --psm 6 לבלוק אחיד (טרמינל), --psm 11 לטקסט פזור, --invert no/yes אם מצב כהה זוהה לא נכון
```

כמו כן, אפשר מתוך Claude Code: `/screenshot-context:ocr clipboard` ו-`/screenshot-context:install`.

## הסרה

1. `stop-watcher.cmd` ואחר כך `remove-from-startup.cmd`.
2. מחק את תיקיית הפלאגין (כולל `.venv`) ואת `%USERPROFILE%\tessdata`.
3. Tesseract: Settings -> Apps -> Tesseract-OCR -> Uninstall (או `winget uninstall UB-Mannheim.TesseractOCR`).

## מבנה התיקייה

```
install.cmd                 התקנה בלחיצה כפולה
start-watcher.cmd / stop-watcher.cmd
add-to-startup.cmd / remove-from-startup.cmd
clipboard-watcher.pyw       ה-watcher והחלון הקופץ
clipboard-to-text.cmd       המרה ידנית של הלוח (בלי watcher)
scripts/ocr.py              מנוע החילוץ ושער האיכות
scripts/winocr.ps1          OCR של Windows (נפילה חלופית)
scripts/setup.ps1, startup.ps1, stop.ps1
commands/                   פקודות Claude Code
INSTALL.md                  הוראות התקנה לקלוד
requirements.txt            תלויות Python (Pillow)
```

## סטטוס בדיקות

נבדק: לוגיקת שער האיכות, הידור הקוד, ורצף OCR מקצה לקצה על Windows 11 (watcher, חילוץ עברית/אנגלית, הדבקה).
לא נבדק בסביבת בדיקות אוטומטית: מנוע ה-OCR של Windows כחלופה, `install.cmd` על מחשב נקי, והפעלה עם Windows.
בדוק אותם בהתקנה ראשונה והחזר משוב.

גרסה 0.2.0 · רישיון: שימוש פנימי
