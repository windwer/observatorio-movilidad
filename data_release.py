"""Build, validate and restore immutable local data releases.

The large historic database is intentionally not embedded in the application
image.  This command creates a consistent SQLite backup plus geography and
reference files, writes a SHA-256 manifest, and refuses incomplete releases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_TABLES = {"feeds", "routes", "stops", "trips", "stop_times", "services", "population_reference_meta"}
REQUIRED_FILES = ("observatorio_real.sqlite3", "geography/census.geojson", "geography/walkways.geojson",
                  "geography/population_anchors.json")


def digest(path: Path) -> str:
    value=hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8*1024*1024),b""):value.update(block)
    return value.hexdigest()


def inspect_database(path: Path) -> dict:
    if not path.is_file():raise ValueError(f"No existe la base: {path}")
    uri=f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri,uri=True)) as conn:
        conn.row_factory=sqlite3.Row;conn.execute("PRAGMA query_only=ON")
        tables={row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing=sorted(REQUIRED_TABLES-tables)
        if missing:raise ValueError("Faltan tablas: "+", ".join(missing))
        feeds=int(conn.execute("SELECT COUNT(*) FROM feeds").fetchone()[0])
        if feeds<=0:raise ValueError("La release no puede publicarse sin capturas GTFS")
        operators={row[0]:int(row[1]) for row in conn.execute("SELECT operator,COUNT(*) FROM feeds GROUP BY operator")}
        population=int(conn.execute("SELECT COALESCE(MAX(total),0) FROM population_reference_meta").fetchone()[0])
        captures=[dict(row) for row in conn.execute("SELECT operator,MIN(snapshot_date) first_snapshot,MAX(snapshot_date) last_snapshot,COUNT(*) snapshots FROM feeds GROUP BY operator")]
        fk_issues=[tuple(row) for row in conn.execute("PRAGMA foreign_key_check").fetchmany(50)]
    if fk_issues:raise ValueError(f"La base contiene referencias huérfanas: {fk_issues[:3]}")
    return {"feeds":feeds,"operators":operators,"population":population,"captures":captures,"foreign_key_issues":0}


def sqlite_backup(source: Path,destination: Path) -> None:
    source_uri=f"{source.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(source_uri,uri=True)) as src, closing(sqlite3.connect(destination)) as dst:
        src.execute("PRAGMA query_only=ON");src.backup(dst,pages=8192)


def build(source_db: Path,geography: Path,reference_csv: Path,output: Path,release_id: str) -> dict:
    inspect_database(source_db)
    if output.exists():raise FileExistsError(f"El destino ya existe: {output}")
    output.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix=output.name+".pending-",dir=output.parent))
    try:
        sqlite_backup(source_db,staging/"observatorio_real.sqlite3")
        # Migrations run against the staged copy, never against the source
        # database that may still be serving the local application.
        import engine
        migrated=engine.connect(staging/"observatorio_real.sqlite3",readonly=False,initialize=True)
        migrated.close()
        (staging/"geography").mkdir()
        for name in ("census.geojson","walkways.geojson","buildings.geojson","population_anchors.json"):
            source=geography/name
            if source.is_file():shutil.copy2(source,staging/"geography"/name)
        if reference_csv.is_file():
            (staging/"references").mkdir();shutil.copy2(reference_csv,staging/"references"/reference_csv.name)
        metadata=validate(staging,verify_manifest=False)
        files={}
        for path in sorted(p for p in staging.rglob("*") if p.is_file()):
            relative=path.relative_to(staging).as_posix()
            files[relative]={"bytes":path.stat().st_size,"sha256":digest(path)}
        manifest={"schema":1,"release_id":release_id,"created_at":datetime.now(timezone.utc).isoformat(),
                  "immutable":True,"database":metadata["database"],"files":files}
        (staging/"release-manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(staging,output)
        return manifest
    except Exception:
        shutil.rmtree(staging,ignore_errors=True);raise


def validate(root: Path,verify_manifest=True) -> dict:
    missing=[name for name in REQUIRED_FILES if not (root/name).is_file()]
    if missing:raise ValueError("Release incompleta; faltan: "+", ".join(missing))
    database=inspect_database(root/"observatorio_real.sqlite3")
    try:
        census=json.loads((root/"geography/census.geojson").read_text(encoding="utf-8"))
        walkways=json.loads((root/"geography/walkways.geojson").read_text(encoding="utf-8"))
        anchors=json.loads((root/"geography/population_anchors.json").read_text(encoding="utf-8"))
        if census.get("type")!="FeatureCollection" or walkways.get("type")!="FeatureCollection":
            raise ValueError("La cartografía no es un FeatureCollection")
        if anchors.get("method_version")!="walk-network-anchors-v2" or not anchors.get("anchors"):
            raise ValueError("Los anclajes poblacionales no corresponden al método vigente")
        if int(anchors.get("census_population",-1))!=database["population"]:
            raise ValueError("La población de los anclajes no coincide con la referencia de la base")
    except (OSError,json.JSONDecodeError,TypeError,AttributeError) as exc:
        raise ValueError(f"Cartografía o anclajes inválidos: {exc}") from exc
    checked=0
    if verify_manifest:
        manifest_path=root/"release-manifest.json"
        if not manifest_path.is_file():raise ValueError("Falta release-manifest.json")
        manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
        for relative,expected in manifest.get("files",{}).items():
            path=root/relative
            if not path.is_file() or path.stat().st_size!=expected["bytes"] or digest(path)!=expected["sha256"]:
                raise ValueError(f"Hash o tamaño incorrecto: {relative}")
            checked+=1
    return {"valid":True,"root":str(root.resolve()),"database":database,"files_verified":checked,
            "geography":{"census_features":len(census.get("features",[])),
                         "walkway_features":len(walkways.get("features",[])),
                         "population_anchors":len(anchors.get("anchors",[])),
                         "method_version":anchors.get("method_version")}}


def restore(release: Path,destination: Path) -> dict:
    result=validate(release)
    if destination.exists():raise FileExistsError(f"El destino ya existe: {destination}")
    destination.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix=destination.name+".pending-",dir=destination.parent))
    try:
        for item in release.iterdir():
            if item.is_dir():shutil.copytree(item,staging/item.name)
            else:shutil.copy2(item,staging/item.name)
        validate(staging);os.replace(staging,destination)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True);raise
    return {**result,"restored_to":str(destination.resolve())}


def main():
    parser=argparse.ArgumentParser()
    actions=parser.add_subparsers(dest="action",required=True)
    create=actions.add_parser("build");create.add_argument("--db",type=Path,required=True);create.add_argument("--geography",type=Path,required=True)
    create.add_argument("--reference",type=Path,required=True);create.add_argument("--output",type=Path,required=True);create.add_argument("--release-id",required=True)
    check=actions.add_parser("validate");check.add_argument("root",type=Path)
    recover=actions.add_parser("restore");recover.add_argument("release",type=Path);recover.add_argument("destination",type=Path)
    args=parser.parse_args()
    if args.action=="build":result=build(args.db,args.geography,args.reference,args.output,args.release_id)
    elif args.action=="validate":result=validate(args.root)
    else:result=restore(args.release,args.destination)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
