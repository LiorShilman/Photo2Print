"""אבסטרקציית ספק יצירת Mesh (ADR-4) — החלפת ספק היא קונפיגורציה, לא קוד."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ...schemas import GenOptions


class ProviderError(Exception):
    """שגיאת ספק מוגדרת — מפעילה retry/fallback לפי F-3.4."""

    def __init__(self, message_he: str, retryable: bool = True):
        super().__init__(message_he)
        self.message_he = message_he
        self.retryable = retryable


@dataclass
class RawMeshResult:
    mesh_path: Path              # GLB/OBJ/STL גולמי
    confidence: float            # 0–1 (F-3.5)
    provider: str
    metadata: dict = field(default_factory=dict)


class MeshProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(
        self,
        image_path: Path,
        out_dir: Path,
        opts: GenOptions,
        on_progress: Callable[[int, str], None],
    ) -> RawMeshResult:
        """מחזיר mesh גולמי + confidence, או זורק ProviderError."""


def get_provider(name: str) -> MeshProvider:
    from .local_extrude import LocalExtrudeProvider
    from .meshy import MeshyProvider
    from .tripo import TripoProvider

    registry: dict[str, type[MeshProvider]] = {
        "tripo": TripoProvider,
        "meshy": MeshyProvider,
        "local_extrude": LocalExtrudeProvider,
    }
    if name not in registry:
        raise ProviderError(f"ספק לא מוכר: {name}", retryable=False)
    return registry[name]()
