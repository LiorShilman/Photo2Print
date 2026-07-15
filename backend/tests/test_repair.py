"""בדיקות ליבת התיקון — mesh שבור (חורים, רכיבים צפים) חייב לצאת watertight."""
import numpy as np
import pytest
import trimesh

from app.pipeline.stages.mesh_repair import repair_mesh


def make_box_with_hole() -> trimesh.Trimesh:
    """קופסה שהוסרו ממנה 2 משולשים — לא watertight."""
    box = trimesh.creation.box(extents=[20, 20, 20])
    faces = box.faces[2:]  # מסיר שני משולשים → חור
    broken = trimesh.Trimesh(vertices=box.vertices.copy(), faces=faces.copy(), process=False)
    assert not broken.is_watertight
    return broken


def make_mesh_with_floater() -> trimesh.Trimesh:
    """גוף ראשי + קוביה זעירה צפה (רעש AI טיפוסי)."""
    main = trimesh.creation.icosphere(subdivisions=3, radius=10)
    floater = trimesh.creation.box(extents=[0.3, 0.3, 0.3])
    floater.apply_translation([25, 25, 25])
    return trimesh.util.concatenate([main, floater])


def test_repair_closes_holes():
    broken = make_box_with_hole()
    repaired, steps = repair_mesh(broken)
    assert repaired.is_watertight, "החורים לא נסגרו"
    assert repaired.volume > 0
    assert steps["final_validation"]["is_watertight"]


def test_repair_removes_floaters():
    mesh = make_mesh_with_floater()
    n_components_before = len(mesh.split(only_watertight=False))
    assert n_components_before == 2
    repaired, steps = repair_mesh(mesh)
    assert len(repaired.split(only_watertight=False)) == 1, "הרכיב הצף לא הוסר"
    assert steps["remove_floaters"]["components_removed"] == 1


def test_repair_fixes_inverted_normals():
    box = trimesh.creation.box(extents=[10, 10, 10])
    box.invert()  # נורמלים פנימה → נפח שלילי
    repaired, _ = repair_mesh(box)
    assert repaired.is_watertight
    assert repaired.volume > 0, "הנורמלים לא תוקנו החוצה"


def test_repair_reports_diffs():
    broken = make_box_with_hole()
    _, steps = repair_mesh(broken)
    # F-4.1: כל צעד מחזיר diff
    for step_name in ("merge_vertices", "remove_floaters", "fill_holes",
                      "remove_degenerate", "decimation"):
        assert step_name in steps
        assert "faces" in steps[step_name] or "watertight_after" in steps[step_name]


def test_valid_mesh_passes_through():
    sphere = trimesh.creation.icosphere(subdivisions=3, radius=15)
    repaired, steps = repair_mesh(sphere)
    assert repaired.is_watertight
    # נפח כדור נשמר בקירוב (אין הרס של גיאומטריה תקינה)
    assert abs(repaired.volume - sphere.volume) / sphere.volume < 0.01
