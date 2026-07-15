"""בדיקות חיתוך מודלים גדולים לחלקים (Phase 4, F-5.3)."""
import trimesh

from app.pipeline.stages.scale_orient import split_for_bed

BED = (220.0, 220.0, 250.0)


def test_split_oversized_single_axis():
    """מוט ארוך פי 2 מהמשטח → לפחות 2 חלקים, כולם בתחום ואטומים."""
    bar = trimesh.creation.box(extents=[400, 50, 50])
    parts = split_for_bed(bar, BED)
    assert len(parts) >= 2
    for p in parts:
        assert all(p.extents[a] <= BED[a] + 0.5 for a in range(3)), f"חלק חורג: {p.extents}"
        assert p.is_watertight, "cap נכשל — החלק לא אטום"
    # שימור נפח כולל (הפסד קטן מותר מהחיתוך)
    total = sum(p.volume for p in parts)
    assert abs(total - bar.volume) / bar.volume < 0.02


def test_split_oversized_two_axes():
    """לוח שחורג בשני צירים → נחתך בשניהם."""
    plate = trimesh.creation.box(extents=[400, 400, 30])
    parts = split_for_bed(plate, BED)
    assert len(parts) >= 4
    for p in parts:
        assert all(p.extents[a] <= BED[a] + 0.5 for a in range(3))
        assert p.is_watertight


def test_split_fitting_model_untouched():
    """מודל שנכנס למשטח לא נחתך."""
    small = trimesh.creation.box(extents=[100, 80, 60])
    parts = split_for_bed(small, BED)
    assert len(parts) == 1


def test_split_parts_dropped_to_bed():
    """כל חלק מונח על המשטח (z מתחיל מ-0) וממורכז ב-XY."""
    bar = trimesh.creation.box(extents=[500, 40, 40])
    parts = split_for_bed(bar, BED)
    for p in parts:
        assert abs(p.bounds[0][2]) < 1e-6
        assert abs(p.centroid[0]) < 1.0 and abs(p.centroid[1]) < 1.0
