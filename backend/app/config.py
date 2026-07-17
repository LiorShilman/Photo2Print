"""תצורת המערכת — נטענת מ-.env / משתני סביבה."""
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="P2P_",
        extra="ignore",
    )

    data_dir: Path = PROJECT_ROOT / "data"
    db_url: str = ""
    max_upload_mb: int = 200
    max_image_mb: int = 20

    mesh_provider: str = "local_extrude"
    mesh_fallback_provider: str = ""
    shape3d_device: str = ""  # ריק=זיהוי אוטומטי, או "cpu"/"cuda" לכפייה (ספק shap_e)

    slicer_path: str = ""

    cloud_timeout: int = 240
    slice_timeout: int = 120

    filament_price_per_kg: float = 90.0
    electricity_price_per_kwh: float = 0.64
    printer_watts: float = 120.0

    # מפתחות ספקים — שמות סביבה מפורשים בלי prefix
    tripo_api_key: str = Field(default="", validation_alias="TRIPO_API_KEY")
    meshy_api_key: str = Field(default="", validation_alias="MESHY_API_KEY")

    @property
    def database_url(self) -> str:
        if self.db_url:
            return self.db_url
        return f"sqlite:///{(self.data_dir / 'photo2print.db').as_posix()}"

    @property
    def storage_dir(self) -> Path:
        return self.data_dir / "storage"

    def find_slicer(self) -> Path | None:
        """איתור prusa-slicer-console.exe: קונפיג → tools/ → התקנות נפוצות."""
        candidates: list[Path] = []
        if self.slicer_path:
            candidates.append(Path(self.slicer_path))
        candidates += list((PROJECT_ROOT / "tools").glob("**/prusa-slicer-console.exe"))
        candidates += [
            Path(r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"),
        ]
        for c in candidates:
            if c.is_file():
                return c
        return None


class _SettingsProxy:
    """מאפשר החלפת settings בבדיקות בלי לשבור ייבואים."""
    _instance: Settings | None = None

    def __getattr__(self, item):
        if _SettingsProxy._instance is None:
            _SettingsProxy._instance = Settings()
        return getattr(_SettingsProxy._instance, item)


settings = _SettingsProxy()
