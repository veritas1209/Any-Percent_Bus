"""Attach local OSM road shapes to bus GPS and synthetic demonstration corridors.

Inputs are local files. There are no HTTP clients or GPS uploads in this script.
"""
from __future__ import annotations

import bisect
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path

from local_roads import RoadGraph,compact,distance,extract,length

ROOT=Path(__file__).resolve().parents[1]
TMP=ROOT/'tmp'
graph_file=TMP/'ulsan-roads.json'
if not graph_file.exists():extract(TMP/'gyeongsang.osm.pbf',graph_file)
roads=json.loads(graph_file.read_text(encoding='utf-8'))
drive=RoadGraph(roads,'drive');foot=RoadGraph(roads,'foot')
catalog={r['spot_id']:r for r in csv.DictReader((TMP/'jetson-source/route_stops_named.csv').open(encoding='utf-8-sig'))}
traces=defaultdict(list)
with (TMP/'jetson-source/gps_replay.csv').open(encoding='utf-8-sig') as handle:
    reader=csv.reader(handle);next(reader)
    for row in reader:
        if row[4]=='0':continue
        lat,lon=float(row[6]),float(row[5])
        if not (35.40<=lat<=35.72 and 129.10<=lon<=129.55):continue
        date=datetime.strptime(row[0],'%Y-%m-%d %H:%M:%S')
        minute=date.hour*60+date.minute+date.second/60
        traces[row[4],row[1]].append((minute,(lat,lon)))
for trace in traces.values():trace.sort()
counts=Counter();cache={}


def build_shape(start,end,samples=None,reference=None,walking=False):
    key=(tuple(start),tuple(end),tuple(samples or ()),walking)
    if key in cache:return cache[key]
    graph=foot if walking else drive
    source='road_estimate'
    try:
        if samples and len(samples)>1:
            points,error=graph.match([start,*samples,end]);source='gps_road_matched'
        else:points,error=graph.route(start,end)
        # A badly snapped fix is not relabeled as a confident observation.
        if error>200:source='road_estimate'
        shape={'points':compact(points),'source':source,'meters':round(length(points),1),'maxSnapErrorMeters':round(error,1)}
        if reference:shape['referenceRoute'],shape['referenceVehicle']=reference
    except ValueError:
        shape={'points':[],'source':'unavailable','meters':None}
    counts[shape['source']]+=1;cache[key]=shape
    return shape


def point(stop):return (float(stop['lat']),float(stop['lon']))


def corridor(start,end,preferred=None):
    best=None
    for (rid,vehicle),trace in traces.items():
        if preferred and rid!=preferred:continue
        nearest_a=sorted(range(len(trace)),key=lambda i:distance(start,trace[i][1]))[:3]
        nearest_b=sorted(range(len(trace)),key=lambda i:distance(end,trace[i][1]))[:3]
        for a in nearest_a:
            for b in nearest_b:
                if b<=a:continue
                da,db=distance(start,trace[a][1]),distance(end,trace[b][1])
                if da>230 or db>230:continue
                samples=[p for _,p in trace[a:b+1]]
                score=da+db+.01*length(samples)
                if best is None or score<best[0]:best=(score,samples,(rid,vehicle))
    return (best[1],best[2]) if best else (None,None)


def attach(network,observed):
    stops={s['id']:s for s in network['stops']}
    for index,route in enumerate(network['routes']):
        ids=route['stops'];shapes=[]
        if observed:
            trace=traces.get((route['familyId'],route['vehicleId']),[])
            times=[t for t,_ in trace]
        for i,(a,b) in enumerate(zip(ids,ids[1:])):
            start,end=point(stops[a]),point(stops[b])
            if observed:
                begin=route['departures'][0]+route['offsets'][i];finish=route['departures'][0]+route['offsets'][i+1]
                lo,hi=bisect.bisect_left(times,begin-.001),bisect.bisect_right(times,finish+.001)
                samples=[p for _,p in trace[lo:hi]]
                reference=(route['familyId'],route['vehicleId'])
            else:
                preferred='194001240' if route['id'] in ('demo-a','demo-b') else None
                samples,reference=corridor(start,end,preferred)
            shapes.append(build_shape(start,end,samples,reference))
        route['shapeSegments']=shapes
        if index%10==0:print('SHAPES',network.get('dataset','demo'),index+1,'/',len(network['routes']),dict(counts),flush=True)
    for path in network['footpaths']:
        path['shape']=build_shape(point(stops[path['from']]),point(stops[path['to']]),walking=True)
    network['geometryVersion']='local-osm-1'
    network['geometryAttribution']='© OpenStreetMap contributors / OSM Korea'
    network['geometryNote']='GPS는 외부로 전송하지 않고 로컬 도로망에 보정했습니다. GPS가 없는 구간은 도로망 추정이며 공식 노선 확정이 아닙니다.'
    return network


demo=json.loads((ROOT/'shared/network.json').read_text(encoding='utf-8'))
aliases={'uc':'194027121','hwajung':'194027123','station':'1930002200','station-b':'193012314','samsan':'193040418','tower':'193040404','seongnam':'192021606','university':'193030707'}
for stop in demo['stops']:
    if stop['id'] in aliases:
        sid=aliases[stop['id']];stop.update(lat=float(catalog[sid]['lat']),lon=float(catalog[sid]['lon']),bustrackerStopId=sid)
demo=attach(demo,False)
assert all(s['points'] for r in demo['routes'] for s in r['shapeSegments']),'Demo roads are incomplete'
observed=attach(json.loads((ROOT/'shared/observed_network.json').read_text(encoding='utf-8')),True)
for name,network in [('network.json',demo),('observed_network.json',observed)]:
    network['version']=network['version'].split('+roads')[0]+'+roads1'
    for path in (ROOT/'shared'/name,ROOT/'app/assets/data'/name):
        temporary=path.with_suffix('.json.tmp');temporary.write_text(json.dumps(network,ensure_ascii=False,separators=(',',':')),encoding='utf-8');temporary.replace(path)
report={'source':'https://tiles.osm.kr/download/gyeongsang-non-military.osm.pbf','roadFileSha256':hashlib.sha256((TMP/'gyeongsang.osm.pbf').read_bytes()).hexdigest(),
        'graphNodes':len(roads['nodes']),'graphWays':len(roads['ways']),'shapes':dict(counts),
        'gpsExternalTransmission':False,'method':'GPS-constrained local A* on directed OSM roads; no turn-restriction relations or lane-level guarantee.'}
(ROOT/'artifacts/road-geometry.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('DONE',json.dumps(report),flush=True)
subprocess.run([sys.executable,str(ROOT/'tools/update_road_distances.py')],check=True)
