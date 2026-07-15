# PRD — מערכת Photo2Print
## המרת תמונה דו-ממדית לקבצי הדפסת תלת-ממד מקצועיים — מ-0 עד 100

**גרסה:** 1.0
**תאריך:** יולי 2026
**מיועד ל:** מימוש באמצעות Claude Code
**שפה ראשית של הממשק:** עברית (RTL) עם תמיכה מלאה באנגלית

---

## 1. חזון המוצר (Vision)

Photo2Print היא מערכת Web מקצה-לקצה שמקבלת **תמונה דו-ממדית אחת או יותר** של חפץ (או לחלופין קובץ תלת-ממד קיים), ומפיקה באופן אוטומטי **חבילת הדפסה מקצועית ומלאה**: מודל תלת-ממדי מתוקן ואטום (watertight), קבצי STL / 3MF / OBJ, קובץ G-code מוכן למדפסת ספציפית, דוח הדפסה מפורט (זמן, משקל חוט, עלות), ותצוגה מקדימה אינטראקטיבית בתלת-ממד.

**עקרון-על ארכיטקטוני — "אפס ניחושים" (Zero-Guess Policy):**
המערכת לעולם לא שולחת להדפסה מודל שלא עבר את כל שערי האיכות (Quality Gates). כל שלב ב-pipeline מייצר ארטיפקט מאומת + מטא-דאטה, וכישלון בשער איכות עוצר את התהליך עם הסבר ברור למשתמש — לא ממשיכים "על עיוור".

---

## 2. מטרות (Goals)

| # | מטרה | מדד הצלחה |
|---|------|-----------|
| G1 | המרת תמונה בודדת ל-mesh ניתן להדפסה | ≥ 90% מהמודלים עוברים בדיקת manifold ללא התערבות ידנית |
| G2 | תהליך מלא (תמונה → G-code) בפחות מ-5 דקות | P95 < 300 שניות במסלול API ענן |
| G3 | תמיכה בפרופילי מדפסות נפוצות | לפחות 6 פרופילים מובנים (Prusa MK4, Bambu X1C/A1, Ender 3, K1, Mini) |
| G4 | ממשק עברית RTL מלא, כהה, מקצועי | כל מסך עובר בדיקת RTL + נגישות בסיסית |
| G5 | שקיפות מלאה למשתמש | דוח pipeline מלא לכל ג'וב, כולל ציוני איכות לכל שלב |

## 2.1 לא-מטרות (Non-Goals) לגרסה 1

- אין יומרה לדיוק הנדסי (סיבולות < 0.5 מ"מ). המערכת מיועדת לחפצים דקורטיביים, פסלונים, אבזרים, דגמים — לא לחלקי מכונה מדויקים.
- אין הדפסת שרף (SLA) בגרסה 1 — FDM בלבד. SLA מתוכנן ל-v2.
- אין עריכת mesh ידנית מלאה (sculpting) — רק כלי תיקון/חיתוך/סקייל בסיסיים.
- אין ניהול חוות מדפסות / שליחה ישירה למדפסת דרך רשת (v2: Klipper/Moonraker, Bambu LAN).

---

## 3. משתמשי יעד ותרחישים (Personas & Use Cases)

**פרסונה A — "היוצר הביתי":** יש לו מדפסת Ender/Bambu, רוצה להדפיס פסלון של הכלב שלו מתמונה. לא מבין ב-Blender. צריך אשף פשוט: העלאה → סקייל → הדפסה.

**פרסונה B — "המייקר המתקדם":** מכיר סלייסרים, רוצה שליטה בפרמטרים (layer height, infill, supports) אבל רוצה לחסוך את שלב המידול. משתמש במצב Advanced.

**פרסונה C — "בעל עסק קטן":** מדפיס מוצרים בהתאמה אישית ללקוחות. צריך batch, דוחות עלות מדויקים, והיסטוריית ג'ובים.

**תרחישים מרכזיים:**
1. **UC-1:** תמונה בודדת של חפץ → מודל AI → תיקון → סקייל → slicing → הורדת ZIP מלא.
2. **UC-2:** 20–50 תמונות מזוויות שונות → פוטוגרמטריה → מודל מדויק → המשך זהה.
3. **UC-3:** העלאת STL/OBJ/3MF קיים → דילוג על שלב ה-AI → תיקון + slicing בלבד.
4. **UC-4:** צפייה בהיסטוריה, שכפול ג'וב עם פרופיל מדפסת אחר.

---

## 4. ארכיטקטורת המערכת (High-Level Architecture)

```
┌──────────────────────────────────────────────────────────────┐
│                     Frontend — React 18 + TS                  │
│   RTL Hebrew UI · Dark Mode · Three.js Viewer · Wizard Flow   │
└───────────────▲──────────────────────────────┬───────────────┘
                │ REST + WebSocket (progress)   │
┌───────────────┴──────────────────────────────▼───────────────┐
│                  API Gateway — FastAPI (Python)               │
│        Auth · Jobs API · Files API · Profiles API             │
└───────────────┬──────────────────────────────────────────────┘
                │  Redis Queue (RQ / Celery)
┌───────────────▼──────────────────────────────────────────────┐
│                        Worker Pipeline                        │
│                                                               │
│  Stage 1: Ingest & Validate  (Pillow, filetype)               │
│  Stage 2: Image Preprocess   (rembg — הסרת רקע, normalize)    │
│  Stage 3: Mesh Generation                                     │
│           ├─ מסלול ענן:  Tripo3D API / Meshy API              │
│           ├─ מסלול מקומי: TRELLIS / Hunyuan3D-2 (GPU)         │
│           └─ מסלול פוטוגרמטריה: Meshroom CLI (ריבוי תמונות)   │
│  Stage 4: Mesh Repair        (trimesh + PyMeshLab)            │
│  Stage 5: Scale & Orient     (קלט משתמש + אופטימיזציה)        │
│  Stage 6: Printability Check (Quality Gates)                  │
│  Stage 7: Slicing            (PrusaSlicer CLI / OrcaSlicer)   │
│  Stage 8: Package & Report   (ZIP + JSON + PNG previews)      │
└───────────────┬──────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│  Storage: PostgreSQL (jobs, users, profiles) + S3/MinIO       │
│  (קבצים: uploads, meshes, gcode, previews, reports)           │
└──────────────────────────────────────────────────────────────┘
```

**החלטות ארכיטקטוניות מרכזיות (ADRs):**

- **ADR-1 — Python בצד השרת:** כל אקוסיסטם עיבוד ה-mesh (trimesh, PyMeshLab, rembg, numpy-stl) הוא Python-native. FastAPI נותן async + OpenAPI אוטומטי.
- **ADR-2 — תור עבודות חובה:** יצירת mesh אורכת 30–180 שניות. אסור לחסום HTTP. כל ג'וב הוא אסינכרוני עם עדכוני התקדמות ב-WebSocket.
- **ADR-3 — Slicer כ-CLI חיצוני, לא ספרייה:** PrusaSlicer/OrcaSlicer רצים כתהליך נפרד עם קונפיג .ini/.json. זה מבודד קריסות ומאפשר עדכון סלייסר בלי לגעת בקוד.
- **ADR-4 — אבסטרקציית ספק (Provider Abstraction) ליצירת mesh:** ממשק אחיד `MeshProvider` עם מימושים Tripo / Meshy / Local. החלפת ספק = קונפיגורציה, לא קוד.
- **ADR-5 — כל ארטיפקט נשמר:** תמונה מקורית, תמונה מעובדת, mesh גולמי, mesh מתוקן, G-code — הכל ב-storage עם hash. מאפשר debug, שכפול ו-audit מלא.

---

## 5. דרישות פונקציונליות — פירוט לפי מודול

### 5.1 מודול קלט (Ingest)

| ID | דרישה | קדימות |
|----|-------|--------|
| F-1.1 | העלאת תמונה בודדת: JPG/PNG/WEBP/HEIC, עד 20MB, מינימום 512×512 | Must |
| F-1.2 | העלאת סט תמונות (2–100) לפוטוגרמטריה, גרירה מרובה + מיון | Should |
| F-1.3 | ייבוא קובץ תלת-ממד קיים: STL/OBJ/3MF/PLY/GLB עד 200MB | Must |
| F-1.4 | צילום ישיר ממצלמת המכשיר (mobile) עם מדריך זוויות מצולם | Could |
| F-1.5 | ולידציה: פורמט, גודל, רזולוציה, תמונה לא ריקה/שחורה | Must |
| F-1.6 | זיהוי אוטומטי של מסלול: תמונה אחת / ריבוי תמונות / mesh קיים | Must |

### 5.2 מודול עיבוד תמונה מקדים (Preprocess)

| ID | דרישה | קדימות |
|----|-------|--------|
| F-2.1 | הסרת רקע אוטומטית (rembg / BiRefNet) עם תצוגת לפני/אחרי | Must |
| F-2.2 | אפשרות ביטול הסרת רקע או תיקון ידני עם מברשת (v1.5) | Should |
| F-2.3 | חיתוך אוטומטי סביב האובייקט + padding אחיד | Must |
| F-2.4 | נרמול: resize ל-1024×1024, תיקון EXIF rotation | Must |
| F-2.5 | ציון "התאמת תמונה" (0–100): חדות, ניגודיות אובייקט-רקע, אובייקט יחיד. מתחת ל-40 — אזהרה למשתמש עם טיפים לצילום טוב יותר | Must |

### 5.3 מודול יצירת Mesh (הליבה)

ממשק אחיד:

```python
class MeshProvider(ABC):
    async def generate(self, image: ProcessedImage,
                       opts: GenOptions) -> RawMeshResult:
        """מחזיר GLB/OBJ + confidence + metadata או שגיאה מוגדרת"""

class GenOptions(BaseModel):
    quality: Literal["draft", "standard", "high"] = "standard"
    target_polycount: int = 100_000
    texture: bool = False          # v1: גיאומטריה בלבד להדפסה
    symmetry_hint: bool | None     # רמז סימטריה משפר צד נסתר
```

| ID | דרישה | קדימות |
|----|-------|--------|
| F-3.1 | ספק ענן ראשי: Tripo3D API (image-to-3D). Fallback: Meshy API | Must |
| F-3.2 | מסלול מקומי אופציונלי: Hunyuan3D-2 / TRELLIS על GPU מקומי (קונפיג) | Should |
| F-3.3 | מסלול פוטוגרמטריה: Meshroom CLI בקונטיינר, לריבוי תמונות | Should |
| F-3.4 | Retry אוטומטי (עד 2) עם backoff; מעבר fallback אחרי כשל ספק | Must |
| F-3.5 | שמירת confidence score מהספק + הצגתו למשתמש | Must |
| F-3.6 | Timeout קשיח: 240 שניות לענן, 600 לפוטוגרמטריה | Must |

### 5.4 מודול תיקון Mesh (Repair)

צנרת תיקון דטרמיניסטית ב-trimesh + PyMeshLab, כל צעד מתועד:

1. **טעינה ונרמול** — המרה ל-mesh יחיד, איחוד vertices כפולים (merge threshold 1e-6).
2. **הסרת רכיבים צפים** — מחיקת components שמסתם < 1% מהראשי (רעש AI טיפוסי).
3. **סגירת חורים** — hole filling עד היקף מוגדר; חורים גדולים → Poisson reconstruction.
4. **תיקון נורמלים** — reorientation עקבי כלפי חוץ.
5. **הסרת self-intersections ו-degenerate faces.**
6. **Decimation חכם** — יעד 150K–500K משולשים לפי גודל פיזי; שימור פרטים (quadric edge collapse).
7. **אימות סופי:** `is_watertight == True`, `is_winding_consistent == True`, `euler_number` תקין, נפח > 0.

| ID | דרישה | קדימות |
|----|-------|--------|
| F-4.1 | כל צעד מחזיר diff (כמה vertices/faces שונו) לדוח | Must |
| F-4.2 | אם אחרי כל הצעדים המודל אינו watertight → כשל Gate עם הצעה: "נסה תמונה אחרת / הפעל Poisson אגרסיבי" | Must |
| F-4.3 | מצב "Poisson אגרסיבי" — reconstruction מלא (מאבד פרטים, מציל מודלים בעייתיים) | Should |

### 5.5 מודול סקייל וכיוון (Scale & Orient)

זה השלב היחיד שבו **חובה** קלט משתמש, כי מתמונה אין מידע ממדי.

| ID | דרישה | קדימות |
|----|-------|--------|
| F-5.1 | קלט מידה: המשתמש בוחר ציר (גובה/רוחב/עומק) ומזין מ"מ. שאר הצירים מחושבים פרופורציונלית | Must |
| F-5.2 | הצגת bounding box חי בתלת-ממד עם מידות בזמן אמת | Must |
| F-5.3 | בדיקת התאמה למשטח ההדפסה של הפרופיל הנבחר; חריגה → הצעת סקייל מקסימלי או חיתוך לחלקים (v2) | Must |
| F-5.4 | אוריינטציה אוטומטית: אלגוריתם שממזער שטח supports + ממקסם שטח מגע עם המשטח (בדיקת 26 כיוונים + fine-tune) | Must |
| F-5.5 | סיבוב ידני ב-viewer (gizmo) עם snap ל-15° | Must |
| F-5.6 | "השטחת בסיס" אופציונלית — חיתוך planar עדין לשיפור הצמדות שכבה ראשונה | Should |

### 5.6 שערי איכות (Quality Gates) — לב מדיניות אפס-ניחושים

| Gate | בדיקה | סף כשל |
|------|-------|--------|
| QG-1 | ציון התאמת תמונה | < 25 → חסימה; 25–40 → אזהרה |
| QG-2 | Confidence של ספק ה-AI | < 0.35 → אזהרה בולטת + המלצה לתמונות נוספות |
| QG-3 | Watertight + winding אחרי Repair | כשל → עצירה |
| QG-4 | עובי דופן מינימלי (בדיקת ray-based sampling) | דופן < 2×nozzle → אזהרה + הצעת סקייל/הגדלה |
| QG-5 | התאמה לנפח הדפסה | חריגה → עצירה עם פתרונות |
| QG-6 | G-code sanity: זמן > 0, חוט > 0, אין פקודות מחוץ לתחום | כשל → עצירה |

### 5.7 מודול Slicing

| ID | דרישה | קדימות |
|----|-------|--------|
| F-7.1 | הרצת PrusaSlicer CLI (`--export-gcode`) עם פרופיל .ini שנבנה דינמית | Must |
| F-7.2 | פרופילי מדפסת מובנים: Prusa MK4/Mini, Bambu X1C/A1/A1-Mini, Ender 3 V3, Creality K1 | Must |
| F-7.3 | שלושה פריסטים: Draft (0.28), Standard (0.2), Quality (0.12) + חומרים PLA/PETG/TPU | Must |
| F-7.4 | מצב Advanced: עריכת layer height, infill (%+pattern), supports (auto/tree/off), brim/raft, walls, טמפרטורות | Must |
| F-7.5 | חילוץ מטא-דאטה מה-G-code: זמן משוער, אורך/משקל חוט, מספר שכבות | Must |
| F-7.6 | חישוב עלות: משקל × מחיר ק"ג (מוגדר בהגדרות) + חשמל משוער | Should |
| F-7.7 | Preview שכבות: רנדור G-code ב-viewer עם slider שכבות | Should |

### 5.8 מודול אריזה ופלט (Package)

תוצר סופי — **ZIP אחד להורדה** + גישה פרטנית לכל קובץ:

```
photo2print_job_<id>/
├── model/
│   ├── model_repaired.stl        # ה-mesh הסופי
│   ├── model_repaired.3mf        # כולל אוריינטציה וסקייל
│   └── model_original_raw.glb    # הפלט הגולמי מה-AI (שקיפות)
├── print/
│   ├── print_<printer>_<preset>.gcode
│   └── slicer_config_used.ini    # שחזור מלא של ההגדרות
├── previews/
│   ├── model_turntable.gif       # סיבוב 360°
│   ├── views_[front|side|top].png
│   └── first_layer.png           # שכבה ראשונה — קריטי לאבחון
└── report/
    ├── print_report.html         # דוח עברית RTL, dark mode
    └── pipeline_metadata.json    # כל שלב, ציון, זמן, גרסאות
```

---

## 6. מפרט UI/UX

### 6.1 עקרונות עיצוב

- **עברית RTL מלאה** — `dir="rtl"` גלובלי; רכיבי תלת-ממד וקוד נשארים LTR באיים מבודדים.
- **Dark Mode כברירת מחדל** — רקע `#0d1117`, משטחים `#161b22`, טקסט `#e6edf3`, Accent טורקיז `#2dd4bf`, אזהרות ענבר `#f59e0b`, שגיאות `#ef4444`.
- **טיפוגרפיה:** Heebo / Assistant לעברית, JetBrains Mono לנתונים טכניים.
- אשף (Wizard) לינארי למתחילים; מצב Advanced פותח פאנלים נוספים באותם מסכים — לא ממשק נפרד.

### 6.2 מסכים

**S-1 · דף בית / העלאה:** אזור גרירה גדול, שלושה טאבים (תמונה בודדת / ריבוי תמונות / קובץ 3D), גלריית "נוצרו לאחרונה", טיפים לצילום מוצלח.

**S-2 · עיבוד תמונה:** לפני/אחרי הסרת רקע (slider השוואה), ציון התאמה עם הסבר, כפתור "המשך ליצירת מודל".

**S-3 · יצירה (מסך המתנה חכם):** progress אמיתי לפי שלבי pipeline דרך WebSocket — "מייצר גיאומטריה… מתקן רשת… בודק אטימות…" עם אנימציית שלד תלת-ממד.

**S-4 · צפייה וכיוונון (המסך המרכזי):**
- Viewer מבוסס **Three.js + React Three Fiber**: OrbitControls, תאורת סטודיו, משטח הדפסה וירטואלי בגודל אמיתי של המדפסת הנבחרת, gizmo סיבוב, מדידות.
- פאנל צד: סקייל (קלט מ"מ + slider), בחירת מדפסת/חומר/פריסט, מתג supports, כפתור "אוריינטציה אוטומטית".
- שורת Quality Gates: שישה צ'יפים ירוק/ענבר/אדום עם tooltip הסבר לכל אחד.

**S-5 · Slicing ותוצאות:** preview שכבות עם slider, כרטיסי סיכום (זמן ⏱ · חוט 🧵 · עלות ₪ · שכבות), כפתור הורדת ZIP, הורדות פרטניות, "שכפל עם פרופיל אחר".

**S-6 · היסטוריה:** טבלת ג'ובים — thumbnail, תאריך, מדפסת, סטטוס, פעולות (הורדה/שכפול/מחיקה).

**S-7 · הגדרות:** ניהול פרופילי מדפסות (כולל ייבוא פרופיל מותאם), מחירי חומרים, ספק AI מועדף, שפה.

### 6.3 WebSocket — חוזה עדכוני התקדמות

```json
{
  "job_id": "j_8f3a",
  "stage": "mesh_repair",
  "stage_index": 4,
  "total_stages": 8,
  "progress_pct": 62,
  "message_he": "סוגר חורים ברשת (3 מתוך 5)…",
  "gates": { "QG1": "pass", "QG2": "warn", "QG3": "pending" }
}
```

---

## 7. API — נקודות קצה עיקריות

| Method | Path | תיאור |
|--------|------|-------|
| POST | `/api/v1/jobs` | יצירת ג'וב (multipart: קבצים + JSON אפשרויות) |
| GET | `/api/v1/jobs/{id}` | סטטוס מלא + קישורי ארטיפקטים |
| POST | `/api/v1/jobs/{id}/scale` | קביעת סקייל ואוריינטציה, משחרר את שלב ה-slicing |
| POST | `/api/v1/jobs/{id}/slice` | הרצת slicing עם פרמטרים (תומך הרצה חוזרת) |
| GET | `/api/v1/jobs/{id}/download` | ZIP מלא |
| GET | `/api/v1/profiles` | פרופילי מדפסות + פריסטים |
| POST | `/api/v1/profiles` | פרופיל מותאם אישית |
| WS | `/ws/jobs/{id}` | עדכוני התקדמות |

**מודל נתונים מרכזי (PostgreSQL):**

```sql
jobs(id, user_id, status, input_type, source_provider,
     image_score, ai_confidence, created_at, ...)
job_stages(job_id, stage_name, status, started_at, finished_at,
           metrics_json, error_json)
artifacts(id, job_id, kind, s3_key, sha256, size_bytes)
printer_profiles(id, name, bed_x, bed_y, bed_z, nozzle_mm,
                 slicer_ini_base, is_builtin)
```

---

## 8. סטאק טכנולוגי — סיכום

| שכבה | טכנולוגיה | הערות |
|------|-----------|-------|
| Frontend | React 18 + TypeScript + Vite | RTL, dark mode |
| 3D Viewer | Three.js + React Three Fiber + drei | STL/GLB loaders, G-code preview |
| State | Zustand + TanStack Query | פשוט ויעיל לג'ובים אסינכרוניים |
| Backend | Python 3.12 + FastAPI + Pydantic v2 | OpenAPI אוטומטי |
| Queue | Redis + RQ | worker נפרד לכל pipeline |
| Mesh | trimesh, PyMeshLab, numpy-stl, rembg | ליבת העיבוד |
| AI 3D | Tripo3D API (ראשי), Meshy (fallback), Hunyuan3D-2 (מקומי) | אבסטרקציית Provider |
| Photogrammetry | Meshroom CLI (Docker) | v1.5 |
| Slicer | PrusaSlicer 2.8+ CLI (ראשי), OrcaSlicer (v2) | תהליך מבודד |
| DB / Files | PostgreSQL 16 + MinIO (S3-compatible) | |
| Deploy | Docker Compose: web, api, worker, redis, db, minio | GPU worker אופציונלי |

---

## 9. דרישות לא-פונקציונליות

- **ביצועים:** UC-1 מלא P50 < 150s, P95 < 300s (מסלול ענן). Slicing בלבד < 30s למודל 300K משולשים.
- **אמינות:** ג'וב שנכשל ניתן לחידוש (resume) מהשלב האחרון שהצליח — כל שלב idempotent על בסיס הארטיפקטים השמורים.
- **אבטחה:** סניטציה של כל קובץ עולה (magic bytes, לא סיומת), הרצת סלייסר ו-Meshroom בקונטיינר ללא רשת, הגבלת קצב, מפתחות API של ספקים בצד שרת בלבד.
- **עלויות:** מונה עלות API לספקי AI פר ג'וב; תקרת שימוש יומית ניתנת להגדרה.
- **פרטיות:** מחיקת ג'וב מוחקת את כל הארטיפקטים; אופציית retention אוטומטי (30 יום).

---

## 10. תוכנית מימוש בשלבים (עבור Claude Code)

### Phase 0 — שלד (יום-יומיים)
Docker Compose מלא, FastAPI + React בסיסי, חיבור DB/Redis/MinIO, ג'וב "hello pipeline" עם WebSocket progress.
**DoD:** העלאת קובץ נשמרת ב-MinIO ומופיע progress חי ב-UI.

### Phase 1 — MVP מסלול קיים-3D (שבוע)
UC-3 במלואו: ייבוא STL → Repair → Scale/Orient ב-viewer → Slicing (פרופיל אחד, Prusa MK4) → ZIP + דוח.
**DoD:** STL "שבור" (עם חורים) הופך ל-G-code תקין שמודפס בהצלחה.

### Phase 2 — מסלול תמונה (שבוע-שבועיים)
UC-1: preprocess + rembg, אינטגרציית Tripo API + fallback Meshy, Quality Gates מלאים, ציון תמונה.
**DoD:** תמונת חפץ פשוט → פסלון מודפס, ≥ 8/10 תמונות מבחן עוברות ללא התערבות.

### Phase 3 — מקצועיות (שבוע)
כל פרופילי המדפסות, מצב Advanced, אוריינטציה אוטומטית, preview שכבות, דוח HTML מלא, היסטוריה, חישוב עלויות.

### Phase 4 — הרחבות (v1.5–v2)
פוטוגרמטריה (Meshroom), מודל מקומי על GPU, חיתוך לחלקים גדולים, שליחה ישירה למדפסת (Moonraker/Bambu), SLA.

---

## 11. בדיקות וקבלה (Acceptance)

- **סט מבחן קבוע:** 20 תמונות ייחוס (חפצים פשוטים/בינוניים/קשים) + 10 קבצי STL בעייתיים ידועים. כל שינוי ב-pipeline רץ מולם (regression).
- **A-1:** 100% מקבצי ה-G-code שנוצרו עוברים ולידציה חיצונית (למשל בדיקת klipper `--check`).
- **A-2:** אף ג'וב לא מסתיים "בהצלחה" עם gate אדום — נאכף בקוד, לא רק ב-UI.
- **A-3:** בדיקת RTL ידנית לכל מסך + snapshot tests.
- **A-4:** הדפסה פיזית של 5 מודלים מייצגים על 2 מדפסות שונות — קריטריון האמת.

## 12. סיכונים ומיטיגציות

| סיכון | חומרה | מיטיגציה |
|-------|-------|----------|
| איכות AI לא עקבית לצד הנסתר | גבוהה | ציון confidence שקוף, המלצת ריבוי תמונות, מסלול פוטוגרמטריה |
| שינוי/מחיר API של ספק | בינונית | Provider abstraction + מסלול מקומי |
| G-code פוגע במדפסת | גבוהה | QG-6, פרופילים שמרניים מובנים, בדיקות פיזיות |
| זמני GPU במסלול מקומי | בינונית | ברירת מחדל ענן; מקומי כ-opt-in |
| קבצים עוינים בהעלאה | בינונית | סניטציה, sandbox, הגבלות גודל |

---

## 13. נספח — פקודות ייחוס

```bash
# Slicing עם PrusaSlicer CLI
prusa-slicer --export-gcode --load profile_mk4_standard.ini \
  --output out.gcode model_repaired.stl

# בדיקת watertight מהירה (python)
import trimesh
m = trimesh.load("model.stl")
assert m.is_watertight and m.is_winding_consistent and m.volume > 0

# הסרת רקע
rembg i input.jpg output.png
```

**הנחיה ל-Claude Code:** יש לממש לפי סדר ה-Phases. כל Phase מסתיים ב-commit עם בדיקות עוברות. אין לעבור Phase לפני עמידה ב-DoD. כל קוד עיבוד mesh חייב unit tests עם קבצי fixture אמיתיים.

— סוף מסמך —
