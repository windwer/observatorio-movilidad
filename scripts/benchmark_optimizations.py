"""Compare v1.1.0 algorithms and current code on identical real data."""
import argparse
import ast
import json
import statistics
import subprocess
import sys
import time
import types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine
import territory


def measured(fn,repeats=3):
    samples=[]
    for _ in range(repeats):
        start=time.perf_counter();value=fn();samples.append((time.perf_counter()-start)*1000)
    return value,round(statistics.median(samples),2)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--geography',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    old_source=subprocess.check_output(['git','show','v1.1.0:engine.py'],text=True,encoding='utf-8')
    old_engine=types.ModuleType('baseline_engine');old_engine.__file__=engine.__file__
    exec(compile(old_source,'baseline_engine.py','exec'),old_engine.__dict__)
    old_geo=subprocess.check_output(['git','show','v1.1.0:territory.py'],text=True,encoding='utf-8')
    tree=ast.parse(old_geo)
    cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='TerritoryStore')
    method=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='network_coverage')
    scope=dict(territory.__dict__);exec(compile(ast.Module(body=[method],type_ignores=[]),'baseline_coverage.py','exec'),scope)
    baseline_coverage=scope['network_coverage']
    conn=engine.connect(args.db,readonly=True,initialize=False)
    report={'baseline':'v1.1.0 algorithms, same optimized immutable database','monthly':[],'coverage':[]}
    try:
        for operator in engine.OPERATORS:
            baseline,old_ms=measured(lambda:old_engine.month_analysis(conn,operator,2026,10,'LJ'))
            current,new_ms=measured(lambda:engine.month_analysis(conn,operator,2026,10,'LJ'))
            assert baseline==current,operator+' monthly result changed'
            report['monthly'].append({'operator':operator,'baseline_ms':old_ms,'optimized_ms':new_ms})
        store=territory.TerritoryStore(args.geography,artifact_path=args.cache)
        for operator,day,route in [('irunbus','2026-10-16','L1'),('ekialdebus','2026-10-16','205'),('errenteria_urbanoa','2026-10-22','')]:
            data=engine.map_data(conn,operator,day,route)
            if not data['stops']:data=engine.map_data(conn,operator,day)
            stops=data['stops']
            store._iso_cache.clear()
            baseline,old_ms=measured(lambda:baseline_coverage(store,stops),repeats=1)
            current,new_ms=measured(lambda:store.network_coverage(stops))
            for field in ('population','units_reached','municipalities','stops_connected','stops_unconnected'):
                assert baseline[field]==current[field],(operator,field,baseline[field],current[field])
            report['coverage'].append({'operator':operator,'stops':len(stops),'baseline_ms':old_ms,
                'optimized_ms':new_ms,'population':current['population'],'equivalent':True})
    finally:conn.close()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))


if __name__=='__main__':main()
