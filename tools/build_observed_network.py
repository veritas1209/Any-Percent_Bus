"""Extract observed vehicle runs from the authorized Jetson GPS sample. No inferred future trips."""
import csv
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tmp/jetson-source'
families={'194001240','194001140','194001340','195012240','195007410'}
catalog={r['spot_id']:r for r in csv.DictReader((SOURCE/'route_stops_named.csv').open(encoding='utf-8-sig'))}
names={r['route_id']:r['route_no'] for r in csv.DictReader((SOURCE/'route_names_manual.csv').open(encoding='utf-8-sig'))}
vehicles=defaultdict(list)
with (SOURCE/'gps_replay.csv').open(encoding='utf-8-sig') as f:
    rows=csv.reader(f);next(rows)
    for row in rows:
        sid=row[10]
        if row[4] not in families or sid=='0' or sid not in catalog or not catalog[sid]['stop_name']:
            continue
        t=datetime.strptime(row[0],'%Y-%m-%d %H:%M:%S')
        minute=t.hour*60+t.minute+t.second/60
        key=(row[1],row[4])
        if not vehicles[key] or vehicles[key][-1][0]!=sid:
            vehicles[key].append((sid,minute))
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
        route={'id':f'obs:{rid}:{vehicle}:{i}','familyId':rid,'number':names.get(rid,rid),
               'name':'GPS 관측 운행','vehicleId':vehicle,'stops':stop_ids,
               'offsets':[round(t-segment[0][1],6) for _,t in segment],
               'departures':[segment[0][1]],'color':colors[sorted(families).index(rid)],
               'delaySamples':[0,0,1,1,2,2,3,4,5,7],'scheduleSource':'replay_observed','delaySource':'simulated'}
        routes.append(route);used.update(stop_ids)
stops=[{'id':sid,'name':catalog[sid]['stop_name'],'lat':float(catalog[sid]['lat']),'lon':float(catalog[sid]['lon']),
        'direction':f'관측 정류장 {sid}'} for sid in sorted(used)]

def distance(a,b):
    dx=(a['lon']-b['lon'])*91000;dy=(a['lat']-b['lat'])*111000
    return math.hypot(dx,dy)

footpaths=[]
for a in stops:
    for b in stops:
        meters=distance(a,b)
        if a['id']!=b['id'] and meters<=100:
            footpaths.append({'from':a['id'],'to':b['id'],'meters':round(max(20,meters*1.5)),'source':'geometric_estimate'})
network={'version':'jetson-2025-12-31-0700','dataset':'observed','source':'replay_observed',
         'description':'Jetson의 2025-12-31 07:00~07:59 GPS에서 통과지점 변경을 추출했습니다. 정차시각 근사치이며 미래 운행은 외삽하지 않습니다. 지연 표본은 가상, 보행거리는 기하 추정입니다.',
         'defaultOrigin':'194027121','defaultDestination':'192021606','defaultDeparture':430,
         'routeFamilies':len(families),'stops':stops,'routes':routes,'footpaths':footpaths}
assert network['defaultOrigin'] in used and network['defaultDestination'] in used
for path in (ROOT/'shared/observed_network.json',ROOT/'app/assets/data/observed_network.json'):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(network,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
print('OBSERVED',len(routes),'runs',len(stops),'stops',len(footpaths),'walking links')
