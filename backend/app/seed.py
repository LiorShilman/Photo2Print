"""פרופילי מדפסות מובנים (F-7.2) — מקור אמת יחיד שמייצר INI + רשומות DB.

ה-INI הם בסיס שמרני; PrusaSlicer משלים ברירות מחדל לכל מפתח שלא הוגדר,
ומוסיף פקודות חימום אוטומטית כשה-start gcode לא כולל אותן.
"""
from .config import PROJECT_ROOT
from .db import db_session
from .models import PrinterProfile

PROFILES_DIR = PROJECT_ROOT / "backend" / "profiles"

# הגדרות print/filament משותפות — שמרניות ובטוחות
COMMON = """\
# --- Photo2Print generated base profile ---
filament_diameter = 1.75
skirts = 1
skirt_distance = 3
brim_width = 0
support_material = 1
support_material_auto = 1
support_material_threshold = 50
fill_pattern = grid
top_solid_layers = 4
bottom_solid_layers = 3
seam_position = nearest
avoid_crossing_perimeters = 1
travel_speed = 150
perimeter_speed = 45
infill_speed = 80
first_layer_speed = 20
retract_length = 0.8
retract_speed = 35
min_skirt_length = 4
"""

BUILTIN_PRINTERS = [
    # name, vendor, bed_x, bed_y, bed_z, nozzle, flavor, extra
    ("Prusa MK4",     "Prusa",    250, 210, 220, 0.4, "marlin2", ""),
    ("Prusa Mini+",   "Prusa",    180, 180, 180, 0.4, "marlin2", ""),
    ("Bambu Lab X1C", "Bambu",    256, 256, 256, 0.4, "marlin2", "retract_length = 0.5\n"),
    ("Bambu Lab A1",  "Bambu",    256, 256, 256, 0.4, "marlin2", "retract_length = 0.5\n"),
    ("Ender 3 V3",    "Creality", 220, 220, 250, 0.4, "marlin2", ""),
    ("Creality K1",   "Creality", 220, 220, 250, 0.4, "klipper", ""),
]


def _ini_name(name: str) -> str:
    return name.lower().replace(" ", "_").replace("+", "plus") + ".ini"


def _build_ini(bed_x, bed_y, bed_z, nozzle, flavor, extra) -> str:
    return (
        COMMON
        + f"bed_shape = 0x0,{bed_x}x0,{bed_x}x{bed_y},0x{bed_y}\n"
        + f"max_print_height = {bed_z}\n"
        + f"nozzle_diameter = {nozzle}\n"
        + f"gcode_flavor = {flavor}\n"
        + extra
    )


def seed_profiles():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    # פרופיל גנרי לפרופילים מותאמים אישית
    generic = PROFILES_DIR / "generic_fdm.ini"
    generic.write_text(_build_ini(220, 220, 250, 0.4, "marlin2", ""), encoding="utf-8")

    with db_session() as s:
        for name, vendor, bx, by, bz, nozzle, flavor, extra in BUILTIN_PRINTERS:
            ini_file = _ini_name(name)
            (PROFILES_DIR / ini_file).write_text(
                _build_ini(bx, by, bz, nozzle, flavor, extra), encoding="utf-8")
            existing = s.query(PrinterProfile).filter_by(name=name).first()
            if existing is None:
                s.add(PrinterProfile(
                    name=name, vendor=vendor, bed_x=bx, bed_y=by, bed_z=bz,
                    nozzle_mm=nozzle, slicer_ini_base=ini_file, is_builtin=True,
                ))
