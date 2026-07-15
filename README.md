# Photo2Print 🖨️

המרת תמונה דו-ממדית (או קובץ תלת-ממד קיים) לחבילת הדפסת תלת-ממד מלאה:
STL מתוקן ואטום → G-code מוכן למדפסת → דוח עלויות → תצוגה תלת-ממדית — עם
**שערי איכות (Quality Gates)** בכל שלב, לפי מדיניות "אפס ניחושים".

> מימוש של [PRD_Photo2Print.md](PRD_Photo2Print.md) — פריסה מקומית על Windows, **ללא Docker**.

## הפעלה מהירה

```powershell
.\run_dev.ps1
```

הסקריפט מתקין הכל בפעם הראשונה (venv + npm) ופותח:
- **UI:** http://localhost:5173 (עברית RTL, dark mode)
- **API:** http://localhost:8008 (OpenAPI: `/docs`)

דרישות: Python 3.12+, Node 18+. PrusaSlicer CLI כלול ב-`tools/` (מורד אוטומטית).

## ארכיטקטורה (התאמות לפריסה מקומית)

| PRD | כאן | הערה |
|-----|-----|------|
| PostgreSQL | SQLite (WAL) | אותם מודלים — SQLAlchemy 2, החלפה = שינוי `P2P_DB_URL` |
| Redis + RQ | ThreadPool in-process | ג'ובים עדיין אסינכרוניים עם WebSocket progress (ADR-2 נשמר) |
| MinIO/S3 | דיסק מקומי `data/storage` | כל ארטיפקט עם SHA-256 (ADR-5 נשמר) |
| Slicer בקונטיינר | PrusaSlicer CLI מ-`tools/` | תהליך נפרד מבודד (ADR-3 נשמר) |

## ספקי יצירת Mesh (ADR-4)

| ספק | דרישה | איכות |
|------|-------|-------|
| `tripo` | `TRIPO_API_KEY` ב-.env | image-to-3D מלא (מומלץ) |
| `meshy` | `MESHY_API_KEY` ב-.env | image-to-3D מלא (fallback) |
| `local_extrude` | כלום (ברירת מחדל) | אקסטרוזיית צללית — דמו/רליף בלבד |

החלפה: `P2P_MESH_PROVIDER=tripo` ב-.env. Fallback: `P2P_MESH_FALLBACK_PROVIDER=meshy`.

## צנרת העיבוד

```
Ingest → Preprocess (rembg) → MeshGen (ספק) → Repair (trimesh)
   → [קלט משתמש: מידות] → Scale/Orient → [קלט משתמש: מדפסת/פריסט]
   → Slicing (PrusaSlicer CLI) → Package (ZIP+דוח)
```

שערי איכות: QG1 ציון תמונה · QG2 ביטחון AI · QG3 אטימות · QG4 עובי דופן ·
QG5 נפח הדפסה · QG6 תקינות G-code. **שער אדום = עצירה** (נאכף בקוד).

## בדיקות

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -v
```

## מבנה

```
backend/app/            FastAPI + pipeline
  pipeline/stages/      8 שלבי העיבוד
  pipeline/providers/   Tripo / Meshy / LocalExtrude
  routers/              jobs, profiles, artifacts
backend/profiles/       INI למדפסות (נוצר מ-seed.py)
backend/tests/          בדיקות unit על fixtures אמיתיים
frontend/src/           React 18 + TS + R3F viewer
tools/prusaslicer/      PrusaSlicer CLI נייד
data/                   DB + ארטיפקטים (לא ב-git)
```
