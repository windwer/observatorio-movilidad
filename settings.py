"""Central, validated runtime configuration for the observatory.

The historic cut-off belongs to the published data release.  It is deliberately
kept separate from the current date so that a new calendar year never rewrites
the meaning of an already approved historic snapshot.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP_VERSION = "1.1.0"
API_SCHEMA_VERSION = "1.1"
METHOD_VERSION = "walk-network-anchors-v2"
DEFAULT_CUTOFF = date(2026, 10, 18)

OPERATOR_CATALOG = {
    "ekialdebus": {"label": "Ekialdebus", "mode": "bus"},
    "irunbus": {"label": "Irunbus", "mode": "bus"},
    "euskotren": {"label": "Euskotren (tren · E1/E2)", "mode": "rail"},
    "errenteria_urbanoa": {"label": "Errenteria bus urbano", "mode": "bus"},
}
CORE_OPERATORS = ("ekialdebus", "irunbus")


def _bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    value = default if raw is None else int(raw)
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} debe estar entre {minimum} y {maximum}")
    return value


@dataclass(frozen=True)
class RuntimeSettings:
    root: Path
    db: Path
    geography_dir: Path
    reference_csv: Path
    state_db: Path
    host: str
    port: int
    cutoff: date
    min_year: int
    max_year: int
    public_read: bool
    reader_username: str
    reader_password: str | None
    admin_username: str
    admin_password: str | None
    cache_entries: int
    rate_limit_per_minute: int
    max_pending_jobs: int
    job_timeout_seconds: int
    immutable_data: bool

    @property
    def loopback(self) -> bool:
        return self.host in {"127.0.0.1", "localhost", "::1"}

    @property
    def writable_local_admin(self) -> bool:
        return self.loopback and not self.admin_password

    def validate(self) -> "RuntimeSettings":
        weak = ("change_me", "password", "admin", "observatorio")
        if not self.loopback:
            if not self.public_read and not self.reader_password:
                raise RuntimeError("OBS_READER_PASSWORD es obligatoria si la lectura remota no es pública")
            if not self.admin_password or len(self.admin_password) < 24 or self.admin_password.lower().startswith(weak):
                raise RuntimeError("OBS_ADMIN_PASSWORD fuerte (mínimo 24 caracteres) es obligatoria fuera de localhost")
        if self.reader_password and len(self.reader_password) < 16:
            raise RuntimeError("OBS_READER_PASSWORD debe tener al menos 16 caracteres")
        if self.admin_password and len(self.admin_password) < 24:
            raise RuntimeError("OBS_ADMIN_PASSWORD debe tener al menos 24 caracteres")
        if self.min_year > self.max_year:
            raise RuntimeError("OBS_MIN_YEAR no puede superar OBS_MAX_YEAR")
        return self


def load_settings() -> RuntimeSettings:
    real_db = ROOT / "data" / "real" / "observatorio_real.sqlite3"
    default_db = real_db if real_db.exists() else ROOT / "data" / "observatorio.sqlite3"
    db = Path(os.environ.get("OBS_DB", default_db)).resolve()
    default_geo = db.parent / "geography"
    bundled_geo = ROOT / "data" / "real" / "geography"
    if db.name.lower() == "observatorio_real.sqlite3" and not default_geo.exists() and bundled_geo.exists():
        default_geo = bundled_geo
    cutoff = date.fromisoformat(os.environ.get("OBS_DATA_CUTOFF", DEFAULT_CUTOFF.isoformat()))
    return RuntimeSettings(
        root=ROOT,
        db=db,
        geography_dir=Path(os.environ.get("OBS_GEOGRAPHY_DIR", default_geo)).resolve(),
        reference_csv=Path(os.environ.get("OBS_REFERENCE_CSV", ROOT / "data" / "references" / "eustat_2025_original.csv")).resolve(),
        state_db=Path(os.environ.get("OBS_STATE_DB", db.parent / "observatorio_state.sqlite3")).resolve(),
        host=os.environ.get("OBS_HOST", "127.0.0.1"),
        port=_int("OBS_PORT", 8765, 1024, 65535),
        cutoff=cutoff,
        min_year=_int("OBS_MIN_YEAR", 2024, 2000, 2100),
        max_year=_int("OBS_MAX_YEAR", 2035, 2000, 2100),
        public_read=_bool("OBS_PUBLIC_READ", True),
        reader_username=os.environ.get("OBS_READER_USERNAME", "analista"),
        reader_password=os.environ.get("OBS_READER_PASSWORD") or os.environ.get("OBS_PASSWORD"),
        admin_username=os.environ.get("OBS_ADMIN_USERNAME", os.environ.get("OBS_USERNAME", "administrador")),
        admin_password=os.environ.get("OBS_ADMIN_PASSWORD") or os.environ.get("OBS_PASSWORD"),
        cache_entries=_int("OBS_ISO_CACHE_ENTRIES", 64, 8, 1024),
        rate_limit_per_minute=_int("OBS_RATE_LIMIT_PER_MINUTE", 3000, 10, 10000),
        max_pending_jobs=_int("OBS_MAX_PENDING_JOBS", 50, 1, 1000),
        job_timeout_seconds=_int("OBS_JOB_TIMEOUT_SECONDS", 900, 30, 86400),
        immutable_data=_bool("OBS_IMMUTABLE_DATA", False),
    ).validate()


SETTINGS = load_settings()
