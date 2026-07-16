"""רגרסיה: סקייל חייב לחול אחרי האוריינטציה האוטומטית, לא לפניה.

באג שנתפס בפועל: משתמש ביקש טבעת בגובה 42 מ"מ (ציר Z). הסקייל חל
לפני האוריינטציה, וכשזו סובבה את המודל 90° (כדי למזער תמיכות), הציר
שהמשתמש כיוון אליו הפך לציר אחר — הגובה הסופי בפועל היה 168 מ"מ.
"""
import numpy as np
import trimesh

from app.pipeline.stages.scale_orient import auto_orient


def test_orientation_then_scale_preserves_target_axis():
    """מדמה בדיוק את run(): אוריינטציה קודם, סקייל אחר כך."""
    # טבעת שוכבת: קוטר גדול (48) הרבה יותר מהעובי (12) — בדיוק המקרה שנשבר
    ring = trimesh.creation.torus(major_radius=18, minor_radius=6)

    oriented, _ = auto_orient(ring.copy())
    # האוריינטציה בחרה לעמוד את הטבעת על הצד (למזער overhang) —
    # כלומר ה-Z הפך לממד הקטן (העובי), לא לקוטר
    assert oriented.extents[2] < oriented.extents[0]

    target_mm = 42.0
    factor = target_mm / oriented.extents[2]
    oriented.apply_scale(factor)

    assert abs(oriented.extents[2] - target_mm) < 1e-6, (
        "הציר שהמשתמש ביקש (Z) חייב להיות בדיוק המידה שהתבקשה אחרי הסקייל"
    )


def test_scale_before_orientation_breaks_target_axis():
    """מתעד את ההתנהגות השבורה של הסדר הישן — סקייל לפני אוריינטציה."""
    ring = trimesh.creation.torus(major_radius=18, minor_radius=6)

    target_mm = 42.0
    factor = target_mm / ring.extents[2]  # לפני אוריינטציה, Z הוא העובי (12)
    scaled = ring.copy()
    scaled.apply_scale(factor)
    oriented, _ = auto_orient(scaled)

    # זה בדיוק הבאג: אחרי סיבוב, ה-Z הסופי כבר לא 42 מ"מ אלא פי ~4
    assert abs(oriented.extents[2] - target_mm) > 50, (
        "בדיקה זו מתעדת את הבאג הישן — אם היא נכשלת, ייתכן שהסדר בקוד חזר להיות שבור"
    )
