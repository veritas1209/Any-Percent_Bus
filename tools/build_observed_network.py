"""Extract observed vehicle runs from the authorized Jetson GPS sample. No inferred future trips."""
import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tmp/jetson-source'
catalog={r['spot_id']:r for r in csv.DictReader((SOURCE/'route_stops_named.csv').open(encoding='utf-8-sig'))}
names={r['route_id']:r['route_no'] for r in csv.DictReader((SOURCE/'route_names_manual.csv').open(encoding='utf-8-sig'))}
static=defaultdict(list)
for row in csv.DictReader((SOURCE/'route_stops_named.csv').open(encoding='utf-8-sig')):
    if row['route_id']!='0':
        ids=static[row['route_id']]
        if row['spot_id']!='0':ids.append(row['spot_id'])
families=set(static)
raw_vehicles=defaultdict(list)
with (SOURCE/'gps_replay.csv').open(encoding='utf-8-sig') as f:
    rows=csv.reader(f);next(rows)
    for row in rows:
        sid=row[10]
        if row[4] not in families or sid=='0' or sid not in catalog:
            continue
        t=datetime.strptime(row[0],'%Y-%m-%d %H:%M:%S')
        minute=t.hour*60+t.minute+t.second/60
        key=(row[1],row[4])
        raw_vehicles[key].append((sid,minute))
vehicles=defaultdict(list);ambiguous=0
for key,samples in raw_vehicles.items():
    by_time=defaultdict(set)
    for sid,t in samples:by_time[t].add(sid)
    for t,ids in sorted(by_time.items()):
        if len(ids)!=1:
            ambiguous+=1;continue
        sid=next(iter(ids))
        if not vehicles[key] or vehicles[key][-1][0]!=sid:vehicles[key].append((sid,t))
routes=[];used=set();colors=['#C9F65B','#7CB8FF','#F6AA78','#C5A2FF','#61D4BE']
for (vehicle,rid),events in vehicles.items():
    segments=[];current=[];seen=set()
    for sid,t in events:
        if current and (sid in seen or t-current[-1][1]>8):
            if len(current)>=2:segments.append(current)
            current=[];seen=set()
        current.append((sid,t));seen.add(sid)
    if len(current)>=2:segments.append(current)
    for i,segment in enumerate(segments):
        stop_ids=[x[0] for x in segment]
        if segment[-1][1]<=segment[0][1]:continue
        route={'id':f'obs:{rid}:{vehicle}:{i}','familyId':rid,'number':names.get(rid) or rid,'numberKnown':bool(names.get(rid)),
               'name':'GPS 관측 운행','vehicleId':vehicle,'stops':stop_ids,
               'offsets':[round(t-segment[0][1],6) for _,t in segment],
               'departures':[segment[0][1]],'color':colors[sorted(families).index(rid)%len(colors)],
               'delaySamples':[0,0,1,1,2,2,3,4,5,7],'scheduleSource':'replay_observed','delaySource':'simulated'}
        routes.append(route);used.update(stop_ids)
observed_families={r['familyId'] for r in routes}
for rid,ids in sorted(static.items()):
    # Preserve supplied direction and repeated stops; never invent a reverse route.
    ids=[sid for i,sid in enumerate(ids) if i==0 or sid!=ids[i-1]]
    routes.append({'id':'cat:'+rid,'familyId':rid,'number':names.get(rid) or rid,'numberKnown':bool(names.get(rid)),
                   'name':'BusTracker 노선 연결','stops':ids,'offsets':[0]*len(ids),'departures':[],
                   'color':colors[sorted(families).index(rid)%len(colors)],'delaySamples':[],
                   'scheduleSource':'catalog_topology','delaySource':'unavailable'})
stops=[{'id':sid,'name':catalog[sid]['stop_name'] or f'이름 미상 정류장 {sid}','lat':float(catalog[sid]['lat']),'lon':float(catalog[sid]['lon']),
        'direction':f'정류장 ID {sid}','hasRecordedService':sid in used} for sid in sorted(catalog) if sid!='0']

def distance(a,b):
    dx=(a['lon']-b['lon'])*91000;dy=(a['lat']-b['lat'])*111000
    return math.hypot(dx,dy)

footpaths=[];grid=defaultdict(list)
for s in stops:grid[int(s['lat']*1110),int(s['lon']*910)].append(s)
for a in stops:
    x,y=int(a['lat']*1110),int(a['lon']*910)
    nearby=[b for dx in (-1,0,1) for dy in (-1,0,1) for b in grid[x+dx,y+dy]]
    for b in nearby:
        meters=distance(a,b)
        if a['id']!=b['id'] and meters<=100:
            footpaths.append({'from':a['id'],'to':b['id'],'meters':round(max(20,meters*1.5)),'source':'geometric_estimate'})
network={'version':'jetson-2025-12-31-0700','dataset':'observed','source':'replay_observed',
         'description':'BusTracker 전체 노선·정류장과 2025-12-31 07:00~07:59 GPS 기록입니다. 기록 연결이 없으면 운행시각 없는 노선 연결 후보를 안내합니다. 지연은 가상, 보행은 도로망 추정입니다.',
         'defaultOrigin':'194027121','defaultDestination':'192021606','defaultDeparture':430,
         'routeFamilies':len(families),'observedRouteFamilies':len(observed_families),'observedRuns':sum(r['scheduleSource']=='replay_observed' for r in routes),
         'catalogRouteCount':len(static),'catalogFallback':True,'rawRouteIds':len(families)+1,'rawStopPointIds':len(catalog),'ambiguousTimestampsExcluded':ambiguous,
         'excludedSentinels':{'routeIds':['0'],'stopIds':['0']},'stops':stops,'routes':routes,'footpaths':footpaths}
assert network['defaultOrigin'] in used and network['defaultDestination'] in used
for path in (ROOT/'shared/observed_network.json',ROOT/'app/assets/data/observed_network.json'):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(network,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print('OBSERVED',len(routes),'runs',len(stops),'stops',len(footpaths),'walking links')
