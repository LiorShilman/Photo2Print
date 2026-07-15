"""ספק מקומי ללא GPU וללא API — אקסטרוזיית צללית (רליף).

לא image-to-3D אמיתי: מחלץ את קו המתאר של האובייקט מהתמונה (אחרי הסרת
רקע) ומייצר גוף תלת-ממדי בעובי פרופורציונלי. שימושי לדמו/פסלוני קו-מתאר,
וכ-default כשאין מפתח ענן. ה-confidence מדווח נמוך בכוונה — QG2 יציג אזהרה.
"""
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from ...schemas import GenOptions
from .base import MeshProvider, ProviderError, RawMeshResult


class LocalExtrudeProvider(MeshProvider):
    name = "local_extrude"

    def generate(self, image_path: Path, out_dir: Path, opts: GenOptions,
                 on_progress: Callable[[int, str], None]) -> RawMeshResult:
        import trimesh
        from shapely.geometry import Polygon
        from shapely.ops import unary_union

        on_progress(10, "מחלץ צללית מהתמונה…")
        im = Image.open(image_path).convert("RGBA")
        alpha = np.asarray(im)[:, :, 3]
        mask = (alpha > 40).astype(np.uint8)
        if mask.sum() < 200:
            raise ProviderError("לא נמצאה צללית ברורה בתמונה", retryable=False)

        on_progress(35, "בונה קו מתאר…")
        try:
            from skimage import measure
            contours = measure.find_contours(mask.astype(float), 0.5)
        except ImportError:
            raise ProviderError("חסרה ספריית scikit-image למסלול המקומי", retryable=False)
        if not contours:
            raise ProviderError("כשל בחילוץ קו המתאר", retryable=False)

        polys = []
        for c in contours:
            if len(c) < 20:
                continue
            # find_contours מחזיר (row, col) → (x, y) עם היפוך ציר Y
            pts = np.column_stack([c[:, 1], mask.shape[0] - c[:, 0]])
            p = Polygon(pts)
            if p.is_valid and p.area > 100:
                polys.append(p)
        if not polys:
            raise ProviderError("קו המתאר קטן או לא תקין", retryable=False)

        shape = unary_union(polys)
        if shape.geom_type == "MultiPolygon":
            shape = max(shape.geoms, key=lambda g: g.area)  # האובייקט הראשי בלבד
        shape = shape.simplify(1.5).buffer(0)
        if shape.is_empty:
            raise ProviderError("קו המתאר התרוקן לאחר פישוט", retryable=False)

        on_progress(65, "מבצע אקסטרוזיה לגוף תלת-ממדי…")
        w = shape.bounds[2] - shape.bounds[0]
        h = shape.bounds[3] - shape.bounds[1]
        depth = 0.28 * max(w, h)  # עובי פרופורציונלי
        mesh = trimesh.creation.extrude_polygon(shape, height=depth)
        # פינות מעוגלות קלות ע"י merge — נשאר פשוט: רק מרכוז
        mesh.apply_translation(-mesh.centroid)

        out = out_dir / "model_raw_extrude.stl"
        mesh.export(out)
        on_progress(95, "המודל המקומי מוכן")

        return RawMeshResult(
            mesh_path=out, confidence=0.45, provider=self.name,
            metadata={"note_he": "מודל אקסטרוזיית צללית — לתלת-ממד מלא הגדר מפתח Tripo/Meshy",
                      "faces": int(len(mesh.faces))},
        )
