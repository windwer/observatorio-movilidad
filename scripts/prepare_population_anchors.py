"""Precalculate the provincial census-to-walk-network allocation artifact."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import territory


def main():
    directory=ROOT/'data'/'real'/'geography'
    destination=directory/'population_anchors.json'
    if destination.exists():destination.unlink()
    store=territory.TerritoryStore(directory,cache_entries=8)
    result=store.save_population_anchors(destination)
    print(json.dumps({**result,'status':store.status()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
