"""ליתופן — המרת heightmap (גווני אפור) למוצק תלת-ממד אטום, ללא AI.

הטכניקה: מעטפת "extruded heightfield" — משטח עליון (top) שגובהו/רדיוסו
תלוי בבהירות הפיקסל, משטח תחתון קבוע (bottom), ודפנות היקף שסוגרות
ביניהם. הבנייה מבטיחה is_watertight מלכתחילה — אין תלות בשלב mesh_repair.
"""
import numpy as np
import trimesh


def _heights_from_gray(gray: np.ndarray, min_mm: float, max_mm: float, invert: bool) -> np.ndarray:
    """גווני אפור 0..255 -> עובי מ"מ. ברירת מחדל: בהיר=דק, כהה=עבה (שחזור נכון בהארה מאחור)."""
    lum = gray.astype(np.float64) / 255.0
    if invert:
        lum = 1.0 - lum
    return min_mm + (1.0 - lum) * (max_mm - min_mm)


def _shell_from_surfaces(top: np.ndarray, bottom: np.ndarray) -> trimesh.Trimesh:
    """בונה מעטפת אטומה מזוג משטחי HxWx3 תואמים (top/bottom) + דפנות היקף מלבניות."""
    h, w, _ = top.shape
    n = h * w
    vertices = np.vstack([top.reshape(-1, 3), bottom.reshape(-1, 3)])

    def idx_top(i, j):
        return i * w + j

    def idx_bottom(i, j):
        return n + i * w + j

    def quad(a, b, c, d):
        """שני משולשים מריבוע שקודקודיו a-b-c-d מסודרים סביב היקפו."""
        return np.vstack([np.column_stack([a, b, c]), np.column_stack([a, c, d])])

    ii, jj = np.meshgrid(np.arange(h - 1), np.arange(w - 1), indexing="ij")
    ii, jj = ii.ravel(), jj.ravel()

    t00, t01 = idx_top(ii, jj), idx_top(ii, jj + 1)
    t10, t11 = idx_top(ii + 1, jj), idx_top(ii + 1, jj + 1)
    b00, b01 = idx_bottom(ii, jj), idx_bottom(ii, jj + 1)
    b10, b11 = idx_bottom(ii + 1, jj), idx_bottom(ii + 1, jj + 1)

    faces = [quad(t00, t10, t11, t01), quad(b00, b01, b11, b10)]

    def edge_strip(top_seq, bot_seq):
        tris = []
        for k in range(len(top_seq) - 1):
            a, b, c, d = top_seq[k], top_seq[k + 1], bot_seq[k], bot_seq[k + 1]
            tris.append([a, b, d])
            tris.append([a, d, c])
        return tris

    perim = []
    perim += edge_strip([idx_top(0, j) for j in range(w)], [idx_bottom(0, j) for j in range(w)])
    perim += edge_strip([idx_top(h - 1, j) for j in range(w)], [idx_bottom(h - 1, j) for j in range(w)])
    perim += edge_strip([idx_top(i, 0) for i in range(h)], [idx_bottom(i, 0) for i in range(h)])
    perim += edge_strip([idx_top(i, w - 1) for i in range(h)], [idx_bottom(i, w - 1) for i in range(h)])
    faces.append(np.array(perim, dtype=np.int64))

    mesh = trimesh.Trimesh(vertices=vertices, faces=np.vstack(faces), process=True)
    trimesh.repair.fix_normals(mesh)
    trimesh.repair.fix_winding(mesh)
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
        trimesh.repair.fix_normals(mesh)
    if not mesh.is_watertight:
        raise RuntimeError("בניית מעטפת הליתופן לא הצליחה להיסגר לגוף אטום")
    return mesh


def build_flat(gray: np.ndarray, min_thickness_mm: float = 0.8, max_thickness_mm: float = 3.2,
               invert: bool = False, pixel_size_mm: float = 1.0) -> trimesh.Trimesh:
    """פאנל שטוח — פאת עליון בתבליט לפי בהירות, גב שטוח."""
    h, w = gray.shape
    thickness = _heights_from_gray(gray, min_thickness_mm, max_thickness_mm, invert)
    xs, ys = np.arange(w) * pixel_size_mm, np.arange(h) * pixel_size_mm
    x, y = np.meshgrid(xs, ys)
    top = np.stack([x, y, thickness], axis=-1)
    bottom = np.stack([x, y, np.zeros_like(thickness)], axis=-1)
    return _shell_from_surfaces(top, bottom)


def build_cylindrical(gray: np.ndarray, wrap_deg: float = 200.0, min_thickness_mm: float = 0.8,
                      max_thickness_mm: float = 3.2, invert: bool = False,
                      pixel_size_mm: float = 1.0) -> trimesh.Trimesh:
    """גליל פתוח (ללא מכסים) — עטיפת התבליט סביב רדיוס בסיס, בסגנון שקף מנורה."""
    h, w = gray.shape
    thickness = _heights_from_gray(gray, min_thickness_mm, max_thickness_mm, invert)
    wrap_rad = np.radians(max(wrap_deg, 1.0))
    base_radius = (w * pixel_size_mm) / wrap_rad

    theta = (np.arange(w) / max(w - 1, 1) - 0.5) * wrap_rad
    theta = np.tile(theta, (h, 1))
    y = np.tile((np.arange(h) * pixel_size_mm).reshape(-1, 1), (1, w))

    outer_r = base_radius + thickness
    top = np.stack([outer_r * np.sin(theta), y, outer_r * np.cos(theta)], axis=-1)
    bottom = np.stack([base_radius * np.sin(theta), y, base_radius * np.cos(theta)], axis=-1)
    return _shell_from_surfaces(top, bottom)
