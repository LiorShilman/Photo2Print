"""בדיקות גיאומטריית ליתופן — המעטפת חייבת לצאת אטומה ותקינה מהבנייה עצמה."""
import numpy as np

from app.pipeline.lithophane import build_cylindrical, build_flat


def gradient_image(h=40, w=60) -> np.ndarray:
    """גרדיאנט אלכסוני פשוט — לא אחיד, כמו תמונה אמיתית."""
    y, x = np.mgrid[0:h, 0:w]
    return (255 * (x / w * 0.6 + y / h * 0.4)).astype(np.uint8)


def checkerboard_image(h=30, w=30) -> np.ndarray:
    """דפוס שח-מט — קפיצות חדות בבהירות, מקרה קצה לתפירת המעטפת."""
    y, x = np.mgrid[0:h, 0:w]
    return (((x // 4 + y // 4) % 2) * 255).astype(np.uint8)


def test_flat_is_watertight_and_valid():
    mesh = build_flat(gradient_image())
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.volume > 0


def test_cylindrical_is_watertight_and_valid():
    mesh = build_cylindrical(gradient_image(), wrap_deg=200.0)
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.volume > 0


def test_flat_checkerboard_edge_case():
    mesh = build_flat(checkerboard_image())
    assert mesh.is_watertight
    assert mesh.is_winding_consistent


def test_cylindrical_checkerboard_edge_case():
    mesh = build_cylindrical(checkerboard_image(), wrap_deg=270.0)
    assert mesh.is_watertight
    assert mesh.is_winding_consistent


def test_invert_flips_thickness_direction():
    gray = gradient_image()
    normal = build_flat(gray, invert=False)
    inverted = build_flat(gray, invert=True)
    # שתי הגרסאות תקינות אך לא זהות בנפח (מיפוי עובי הפוך)
    assert normal.is_watertight and inverted.is_watertight
    assert abs(normal.volume - inverted.volume) > 1e-6


def test_thickness_bounds_respected():
    mesh = build_flat(gradient_image(), min_thickness_mm=1.0, max_thickness_mm=2.0)
    zmin, zmax = mesh.bounds[0][2], mesh.bounds[1][2]
    assert zmin >= -1e-6
    assert zmax <= 2.0 + 1e-6
