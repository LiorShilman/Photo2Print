"""שלב 2 — עיבוד תמונה מקדים (F-2.1..F-2.5).

הסרת רקע (rembg), חיתוך + padding, נרמול 1024², תיקון EXIF,
וציון "התאמת תמונה" 0–100 (QG-1).
"""
import numpy as np
from PIL import Image, ImageOps

from ..context import GateFailure, StageContext, set_gate, set_job
from ...storage import artifact_path, latest_artifact, save_artifact


def image_fitness_score(rgba: np.ndarray) -> tuple[float, dict]:
    """ציון 0–100: חדות (Laplacian), ניגודיות אובייקט-רקע, גודל אובייקט יחסי."""
    alpha = rgba[:, :, 3].astype(np.float32) / 255.0
    gray = rgba[:, :, :3].mean(axis=2).astype(np.float32)

    coverage = float(alpha.mean())  # כמה מהפריים הוא אובייקט
    # חדות — שונות של Laplacian באזור האובייקט
    lap = (
        -4 * gray
        + np.roll(gray, 1, 0) + np.roll(gray, -1, 0)
        + np.roll(gray, 1, 1) + np.roll(gray, -1, 1)
    )
    mask = alpha > 0.5
    sharpness = float(lap[mask].var()) if mask.sum() > 100 else 0.0
    sharp_score = min(1.0, sharpness / 250.0)

    # ניגודיות אובייקט מול רקע מקורי
    if mask.sum() > 100 and (~mask).sum() > 100:
        contrast = abs(float(gray[mask].mean()) - float(gray[~mask].mean())) / 255.0
    else:
        contrast = 0.0

    # גודל אובייקט — אידאלי 15%–75% מהפריים
    if coverage < 0.02:
        size_score = 0.0
    elif coverage < 0.15:
        size_score = coverage / 0.15
    elif coverage <= 0.75:
        size_score = 1.0
    else:
        size_score = max(0.0, 1.0 - (coverage - 0.75) / 0.25)

    score = 100.0 * (0.4 * sharp_score + 0.25 * min(1.0, contrast * 3) + 0.35 * size_score)
    detail = {
        "sharpness": round(sharpness, 1),
        "contrast": round(contrast, 3),
        "coverage": round(coverage, 3),
    }
    return round(score, 1), detail


def run(ctx: StageContext) -> dict:
    from ...db import db_session
    from ...models import Job

    with db_session() as s:
        input_type = s.get(Job, ctx.job_id).input_type
    if input_type in ("mesh", "text"):
        ctx.progress(100, "אין תמונה בקלט — מדלג על עיבוד תמונה")
        return {"skipped": True}

    upload = latest_artifact(ctx.job_id, "upload")
    src = artifact_path(upload)

    if input_type == "lithophane":
        ctx.progress(20, "טוען תמונה ומתקן סיבוב EXIF…")
        im = Image.open(src)
        im = ImageOps.exif_transpose(im).convert("L")
        LITHO_MAX_SIDE = 300
        ratio = LITHO_MAX_SIDE / max(im.size)
        im = im.resize((max(1, round(im.width * ratio)), max(1, round(im.height * ratio))), Image.LANCZOS)
        out = ctx.work_dir / "image_processed.png"
        im.save(out)
        save_artifact(ctx.job_id, "image_processed", out)
        ctx.progress(100, f"תמונה מוכנה לליתופן — {im.width}×{im.height}")
        return {"litho_size": [im.width, im.height]}

    ctx.progress(10, "טוען תמונה ומתקן סיבוב EXIF…")
    im = Image.open(src)
    im = ImageOps.exif_transpose(im)
    im = im.convert("RGBA")

    ctx.progress(25, "מסיר רקע (זה עשוי לקחת עד דקה בהרצה ראשונה)…")
    from rembg import remove  # ייבוא עצל — טוען מודל ONNX
    cut = remove(im)

    ctx.progress(60, "חותך סביב האובייקט ומנרמל…")
    alpha = np.asarray(cut)[:, :, 3]
    ys, xs = np.nonzero(alpha > 10)
    if len(xs) < 100:
        raise GateFailure("QG1", "לא זוהה אובייקט בתמונה לאחר הסרת הרקע",
                          ["צלם על רקע אחיד ומנוגד", "ודא שהחפץ ממלא את מרכז הפריים"])
    pad = int(0.06 * max(xs.max() - xs.min(), ys.max() - ys.min())) + 2
    box = (max(0, xs.min() - pad), max(0, ys.min() - pad),
           min(cut.width, xs.max() + pad), min(cut.height, ys.max() + pad))
    cut = cut.crop(box)

    # ריבוע 1024×1024 עם padding שקוף
    side = max(cut.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(cut, ((side - cut.width) // 2, (side - cut.height) // 2))
    canvas = canvas.resize((1024, 1024), Image.LANCZOS)

    ctx.progress(80, "מחשב ציון התאמת תמונה…")
    score, detail = image_fitness_score(np.asarray(canvas))
    set_job(ctx.job_id, image_score=score)

    # QG-1 (PRD §5.6): < 25 חסימה, 25–40 אזהרה
    tips = ["צלם באור טבעי חזק", "רקע אחיד בצבע מנוגד לחפץ",
            "מלא את הפריים בחפץ (ללא חיתוך)", "ייצב את המצלמה"]
    if score < 25:
        set_gate(ctx.job_id, "QG1", "fail", f"ציון התאמה {score} — נמוך מדי", score=score)
        raise GateFailure("QG1", f"ציון התאמת התמונה {score} נמוך מ-25", tips)
    elif score < 40:
        set_gate(ctx.job_id, "QG1", "warn", f"ציון התאמה {score} — התוצאה עלולה להיות חלקית", score=score)
    else:
        set_gate(ctx.job_id, "QG1", "pass", f"ציון התאמה {score}", score=score)

    out = ctx.work_dir / "image_processed.png"
    canvas.save(out)
    save_artifact(ctx.job_id, "image_processed", out)

    ctx.progress(100, f"עיבוד הושלם — ציון התאמה {score}")
    return {"image_score": score, **detail}
