"""ספק מקומי טקסט-ל-3D — Shap-E (OpenAI), ריצה מקומית ללא API key.

תלות כבדה ואופציונלית (torch + shap-e) — לא מותקנת כברירת מחדל, ראה
backend/requirements-shape3d.txt. ייבוא הספריות נדחה לרגע השימוש בפועל,
כדי שהאפליקציה תעלה תקין גם בלי ההתקנה הזו (שאר הספקים לא מושפעים).
"""
import threading
from pathlib import Path
from typing import Callable

from ...config import settings
from ...schemas import GenOptions
from .base import MeshProvider, ProviderError, RawMeshResult

_lock = threading.Lock()
_cache: dict = {}


def _load_models() -> dict:
    """טעינה חד-פעמית thread-safe — נשמרת בזיכרון התהליך לשימוש חוזר בין ג'ובים."""
    with _lock:
        if _cache:
            return _cache
        try:
            import torch
            from shap_e.diffusion.gaussian_diffusion import diffusion_from_config
            from shap_e.diffusion.sample import sample_latents
            from shap_e.models.download import load_config, load_model
            from shap_e.util.notebooks import decode_latent_mesh
        except ImportError as e:
            raise ProviderError(
                "חסרות ספריות Shap-E — התקן עם: "
                "pip install -r backend/requirements-shape3d.txt",
                retryable=False,
            ) from e

        device_setting = settings.shape3d_device.strip().lower()
        if device_setting == "cuda" and not torch.cuda.is_available():
            raise ProviderError(
                "P2P_SHAPE3D_DEVICE=cuda אך אין GPU זמין (CUDA) במחשב הזה",
                retryable=False,
            )
        if device_setting in ("cpu", "cuda"):
            device = torch.device(device_setting)
        else:
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        xm = load_model("transmitter", device=device)
        model = load_model("text300M", device=device)
        diffusion = diffusion_from_config(load_config("diffusion"))
        _cache.update(
            device=device, xm=xm, model=model, diffusion=diffusion,
            sample_latents=sample_latents, decode_latent_mesh=decode_latent_mesh,
        )
        return _cache


class ShapEProvider(MeshProvider):
    name = "shap_e"

    def generate(self, image_path: Path, out_dir: Path, opts: GenOptions,
                 on_progress: Callable[[int, str], None]) -> RawMeshResult:
        raise ProviderError(
            "shap_e תומך רק בטקסט-ל-3D — עבור תמונות השתמש ב-tripo/meshy/local_extrude",
            retryable=False,
        )

    def generate_from_text(self, prompt: str, out_dir: Path, opts: GenOptions,
                           on_progress: Callable[[int, str], None]) -> RawMeshResult:
        on_progress(5, "טוען ספריות Shap-E…")
        already_loaded = bool(_cache)
        on_progress(
            15,
            "משתמש במודל שכבר נטען בזיכרון…" if already_loaded
            else "טוען משקלי מודל (בפעם הראשונה עשוי לקחת דקות, כולל הורדה)…",
        )
        m = _load_models()

        device_he = "GPU" if m["device"].type == "cuda" else "CPU (איטי)"
        on_progress(30, f"מייצר גיאומטריה על {device_he} (64 צעדי דיפוזיה)…")
        latents = m["sample_latents"](
            batch_size=1,
            model=m["model"],
            diffusion=m["diffusion"],
            guidance_scale=15.0,
            model_kwargs=dict(texts=[prompt]),
            progress=False,
            clip_denoised=True,
            use_fp16=(m["device"].type == "cuda"),
            use_karras=True,
            karras_steps=64,
            sigma_min=1e-3,
            sigma_max=160,
            s_churn=0,
        )

        on_progress(85, "ממיר לרשת משולשים…")
        tri_mesh = m["decode_latent_mesh"](m["xm"], latents[0]).tri_mesh()
        out = out_dir / "model_raw_shape3d.ply"
        with open(out, "wb") as f:
            tri_mesh.write_ply(f)

        on_progress(100, "המודל נוצר (Shap-E מקומי)")
        return RawMeshResult(
            mesh_path=out, confidence=0.55, provider=self.name,
            metadata={
                "note_he": "נוצר מקומית עם Shap-E — איכות נמוכה יותר מספקי ענן "
                          "(Tripo/Meshy); לתוצאות מדויקות יותר הגדר מפתח API.",
            },
        )
