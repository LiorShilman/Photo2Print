"""בדיקות אוריינטציה אוטומטית וציון תמונה."""
import numpy as np
import trimesh

from app.pipeline.stages.scale_orient import auto_orient, orientation_score
from app.pipeline.stages.preprocess import image_fitness_score


def test_auto_orient_prefers_flat_face_down():
    """פירמידה הפוכה (חוד למטה) חייבת להתהפך כך שהבסיס יפגוש את המשטח."""
    cone = trimesh.creation.cone(radius=10, height=20)  # בסיס למטה, חוד למעלה
    flipped = cone.copy()
    flipped.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    # אחרי היפוך: חוד למטה — ציון גרוע יותר
    assert orientation_score(flipped) > orientation_score(cone)

    oriented, _ = auto_orient(flipped.copy())
    # האוריינטציה האוטומטית צריכה להחזיר מצב טוב לפחות כמו המקור
    assert orientation_score(oriented) <= orientation_score(flipped) + 1e-6


def test_fitness_score_good_image():
    """אובייקט חד ובולט במרכז — ציון גבוה."""
    rng = np.random.default_rng(42)
    img = np.zeros((256, 256, 4), dtype=np.uint8)
    img[:, :, :3] = 230  # רקע בהיר
    # אובייקט כהה עם טקסטורה (חדות) במרכז, ~35% מהפריים
    obj = slice(64, 192)
    img[obj, obj, 0] = rng.integers(10, 120, (128, 128))
    img[obj, obj, 1] = rng.integers(10, 120, (128, 128))
    img[obj, obj, 2] = rng.integers(10, 120, (128, 128))
    img[obj, obj, 3] = 255
    score, detail = image_fitness_score(img)
    assert score > 40, f"ציון {score} נמוך מדי לתמונה טובה: {detail}"


def test_fitness_score_empty_image():
    """אין אובייקט (אלפא אפס) — ציון נמוך."""
    img = np.zeros((256, 256, 4), dtype=np.uint8)
    img[:, :, :3] = 128
    score, _ = image_fitness_score(img)
    assert score < 25
