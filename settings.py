"""Central, validated runtime configuration for the observatory.

The historic cut-off belongs to the published data release.  It is deliberately
kept separate from the current date so that a new calendar year never rewrites
the meaning of an already approved historic snapshot.
"""
from __future__ import annotations

import os
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
APP_VERSION = "1.3.0"
API_SCHEMA_VERSION = "1.3"
from model import METHOD_VERSION
DEFAULT_CUTOFF = date(2026, 10, 18)

OPERATOR_CATALOG = {
    "ekialdebus": {"label": "Ekialdebus", "mode": "bus"},
    "irunbus": {"label": "Irunbus", "mode": "bus"},
    "euskotren": {"label": "Euskotren (tren · E1/E2)", "mode": "rail", "route_names":["E1","E2"]},
    "errenteria_urbanoa": {"label": "Errenteria bus urbano", "mode": "bus"},
}
CORE_OPERATORS = ("ekialdebus", "irunbus")

def active_release():
    pointer=os.environ.get('OBS_ACTIVE_RELEASE_FILE')
    if pointer:
        data=json.loads(Path(pointer).read_text(encoding='utf-8'))
        return Path(data['release_dir']).resolve(),data
    db=Path(os.environ.get('OBS_DB',ROOT/'data'/'real'/'observatorio_real.sqlite3'))
    return db.resolve().parent,{}

RELEASE_ROOT,ACTIVE_POINTER=active_release()
MANIFEST=json.loads((RELEASE_ROOT/'release-manifest.json').read_text(encoding='utf-8')) if (RELEASE_ROOT/'release-manifest.json').is_file() else {}
catalog_path=os.environ.get('OBS_CATALOG_FILE')
catalog=json.loads(Path(catalog_path).read_text(encoding='utf-8')) if catalog_path else MANIFEST.get('operator_catalog',{})
for code,entry in catalog.items():
    if not re.fullmatch(r'[a-z0-9_]{1,64}',code) or not isinstance(entry,dict) or not entry.get('label'):
        raise RuntimeError('Catálogo de operadores inválido')
    if not isinstance(entry['label'],str) or len(entry['label'])>160:
        raise RuntimeError('Etiqueta de operador inválida')
    if 'route_names' in entry and (not isinstance(entry['route_names'],list) or not all(isinstance(name,str) and 0<len(name)<=128 for name in entry['route_names'])):
        raise RuntimeError('Filtro de líneas inválido')
    OPERATOR_CATALOG[code]=entry


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
    release_id: str = 'local-unversioned'
    history_start: date = date(2025,1,1)
    trusted_proxies: str = '127.0.0.1,::1'
    retention_days: int = 30

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
    db = (RELEASE_ROOT/'observatorio_real.sqlite3') if ACTIVE_POINTER else Path(os.environ.get("OBS_DB", default_db)).resolve()
    default_geo = db.parent / "geography"
    bundled_geo = ROOT / "data" / "real" / "geography"
    if db.name.lower() == "observatorio_real.sqlite3" and not default_geo.exists() and bundled_geo.exists():
        default_geo = bundled_geo
    cutoff = date.fromisoformat(os.environ.get("OBS_DATA_CUTOFF", MANIFEST.get('cutoff',DEFAULT_CUTOFF.isoformat())))
    return RuntimeSettings(
        root=ROOT,
        db=db,
        geography_dir=Path(os.environ.get("OBS_GEOGRAPHY_DIR", default_geo)).resolve(),
        reference_csv=Path(os.environ.get("OBS_REFERENCE_CSV", (RELEASE_ROOT/'references'/'eustat_2025_original.csv') if MANIFEST else ROOT / "data" / "references" / "eustat_2025_original.csv")).resolve(),
        state_db=Path(os.environ.get("OBS_STATE_DB", ACTIVE_POINTER.get('state_db',db.parent / "observatorio_state.sqlite3"))).resolve(),
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
        immutable_data=_bool("OBS_IMMUTABLE_DATA", bool(ACTIVE_POINTER)),
        release_id=MANIFEST.get('release_id',os.environ.get('OBS_DATA_RELEASE','local-unversioned')),
        history_start=date.fromisoformat(MANIFEST.get('history_start','2025-01-01')),
        trusted_proxies=os.environ.get('FORWARDED_ALLOW_IPS','127.0.0.1,::1'),
        retention_days=_int('OBS_RETENTION_DAYS',30,1,3650),
    ).validate()


SETTINGS = load_settings()
