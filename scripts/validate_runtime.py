"""Read real local data, exercise queue/cancellation, and record reproducible QA."""
import argparse,json,time,urllib.request,urllib.error
from pathlib import Path
from shapely.geometry import shape


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8874');parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    report={};started=time.monotonic()
    def request(path,body=None):
        data=json.dumps(body).encode() if body is not None else None
        with urllib.request.urlopen(urllib.request.Request(args.base+path,data=data,headers={'Content-Type':'application/json'}),timeout=120) as response:return json.load(response)
    def poll(job):
        deadline=time.monotonic()+920
        while job['status'] in ('pending','running'):
            assert time.monotonic()<deadline,job
            time.sleep(.5);job=request('/api/analysis/jobs/'+job['id'])
        assert job['status']=='complete',job
        return job['result']
    assert request('/api/version')['version']=='1.3.0'
    ready=request('/api/ready');assert ready['analysis_ready'],ready
    assert ready['checks']['population_total']==724797,ready
    assert not request('/api/capabilities')['mutable']
    maps={op:request('/api/map?operator='+op+'&day=2026-10-22') for op in ('irunbus','ekialdebus','euskotren','errenteria_urbanoa')}
    report['operators']={op:{'routes':len(data['routes']),'stops':len(data['stops'])} for op,data in maps.items()}
    assert all(d['routes'] and d['stops'] for d in maps.values()),report
    combined=request('/api/map/both?scope=all&day=2026-10-22')
    assert all(r['visual_id']==r['operator']+':'+r['id'] for r in combined['routes'])
    route=maps['irunbus']['routes'][0]['id']
    params={'operator':'irunbus','day':'2026-10-22','route_id':route,'minutes':10}
    # Cancel a distinct request while the worker is loading the provincial graph.
    cancelled=request('/api/analysis/jobs',{**params,'day':'2026-10-21'})
    deadline=time.monotonic()+15
    while cancelled['status']=='pending' and time.monotonic()<deadline:
        time.sleep(.1);cancelled=request('/api/analysis/jobs/'+cancelled['id'])
    if cancelled['status']=='running':
        cancelled=request('/api/analysis/jobs/'+cancelled['id']+'/cancel',{})
        assert cancelled['status']=='cancelled'
    report['cancellation_status']=cancelled['status']
    job=request('/api/analysis/jobs',params);result=poll(job)
    assert result['status']=='estimated' and 0<result['population']<=724797,result
    report['route_coverage']={'route_id':route,**result}
    reused=request('/api/analysis/jobs',params);assert reused['reused'] and reused['status']=='complete'
    local=request('/api/map?operator=irunbus&day=2026-10-22&route_id='+route)
    # Pick a connected stop; no requirement that every real GTFS coordinate is walk-connected.
    for stop in local['stops']:
        prefix='/api/geo/stop?operator=irunbus&day=2026-10-22&stop_id='+stop['id']
        ten=request(prefix+'&minutes=10')
        if ten['status']=='calculated' and ten.get('population',0)>0:
            five=request(prefix+'&minutes=5');break
    else:raise AssertionError('No connected populated stop')
    assert 0<=five['population']<=ten['population']<=result['population']
    a,b=shape(five['geometry']),shape(ten['geometry']);assert a.is_valid and b.is_valid and a.within(b.buffer(1e-8))
    report['stop']={'id':stop['id'],'population_5':five['population'],'population_10':ten['population'],'nested':True,'valid_geometry':True}
    for kind in ('compare_routes','compare_stops','service_coverage'):
        params={'kind':kind,'operator':'irunbus','day':'2026-10-22','old_day':'2025-10-16','new_day':'2026-10-15','territorial_scope':False}
        value=poll(request('/api/tasks',params));report[kind]={'status':value.get('status'),'comparable':value.get('comparable')}
    report['duration_seconds']=round(time.monotonic()-started,2)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
