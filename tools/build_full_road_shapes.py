"""Build shared road geometry for every BusTracker route, using local files only."""
import bisect
import csv
import hashlib
import json
import subprocess
from collections import Counter,defaultdict
from pathlib import Path

from local_roads import RoadGraph,compact,distance,extract,length

ROOT=Path(__file__).resolve().parents[1]
TMP=ROOT/'tmp'
path=TMP/'ulsan-all-roads.json'
if not path.exists():extract(TMP/'gyeongsang.osm.pbf',path,(35.20,35.85,128.85,129.60))
data=json.loads(path.read_text(encoding='utf-8'))
drive=RoadGraph(data,'drive');foot=RoadGraph(data,'foot')
print('GRAPH',len(data['nodes']),len(data['ways']),flush=True)
network=json.loads((ROOT/'shared/observed_network.json').read_text(encoding='utf-8'))
stops={s['id']:s for s in network['stops']}
traces=defaultdict(list)
with (TMP/'jetson-source/gps_replay.csv').open(encoding='utf-8-sig') as f:
    reader=csv.reader(f);next(reader)
    for row in reader:
        if row[4]=='0':continue
        t=int(row[0][11:13])*60+int(row[0][14:16])+int(row[0][17:19])/60
        traces[row[4],row[1]].append((t,(float(row[6]),float(row[5]))))
for values in traces.values():values.sort()
times={key:[t for t,_ in trace] for key,trace in traces.items()}


def simplify(points,tolerance=2):
    if len(points)<=2:return points
    a,b=points[0],points[-1]
    dx=(b[1]-a[1])*91000;dy=(b[0]-a[0])*111000;den=dx*dx+dy*dy
    errors=[]
    for i,p in enumerate(points[1:-1],1):
        px=(p[1]-a[1])*91000;py=(p[0]-a[0])*111000
        fraction=max(0,min(1,(px*dx+py*dy)/den)) if den else 0
        errors.append(((px-fraction*dx)**2+(py-fraction*dy)**2,i))
    error,index=max(errors)
    if error<=tolerance*tolerance:return [a,b]
    return simplify(points[:index+1],tolerance)[:-1]+simplify(points[index:],tolerance)


cache_file=TMP/'full-road-cache.json'
fingerprint=hashlib.sha256((TMP/'jetson-source/route_stops_named.csv').read_bytes()+(TMP/'jetson-source/gps_replay.csv').read_bytes()).hexdigest()
cache={}
if cache_file.exists():
    saved=json.loads(cache_file.read_text(encoding='utf-8'))
    if saved.get('fingerprint')==fingerprint:cache=saved['shapes']


def save():
    temp=cache_file.with_suffix('.tmp')
    temp.write_text(json.dumps({'fingerprint':fingerprint,'shapes':cache},separators=(',',':')),encoding='utf-8');temp.replace(cache_file)


def shape(key,a,b,samples=None,reference=None,walking=False):
    if key in cache:return key
    graph=foot if walking else drive
    start=(stops[a]['lat'],stops[a]['lon']);end=(stops[b]['lat'],stops[b]['lon'])
    try:
        points,error=graph.match([start,*samples,end]) if samples and len(samples)>1 else graph.route(start,end)
        value={'points':compact(simplify(points)),'meters':round(length(points),1),
               'source':'gps_road_matched' if samples and len(samples)>1 and error<=200 else 'road_estimate','maxSnapErrorMeters':round(error,1)}
        if reference:value['referenceRoute'],value['referenceVehicle']=reference
    except ValueError:value={'points':[],'meters':None,'source':'unavailable'}
    cache[key]=value
    if len(cache)%250==0:
        save();print('SHAPES',len(cache),flush=True)
    return key


# Historical build output is an optional speed cache; raw sources remain sufficient.
try:
    old=json.loads(subprocess.check_output(['git','show','HEAD:shared/observed_network.json'],cwd=ROOT))
    for route in old['routes']:
        for a,b,s in zip(route['stops'],route['stops'][1:],route.get('shapeSegments',[])):
            if isinstance(s,dict) and s.get('points'):
                value=dict(s);value['points']=compact(simplify(s['points']))
                cache.setdefault('gps:'+route['familyId']+':'+a+':'+b,value)
except (subprocess.CalledProcessError,KeyError):pass

pool={};family_edges={}
for index,route in enumerate(network['routes']):
    if route['scheduleSource']!='replay_observed':continue
    trace=traces[route['familyId'],route['vehicleId']];ticks=times[route['familyId'],route['vehicleId']]
    shapes=[]
    for i,(a,b) in enumerate(zip(route['stops'],route['stops'][1:])):
        begin=route['departures'][0]+route['offsets'][i];end=route['departures'][0]+route['offsets'][i+1]
        lo,hi=bisect.bisect_left(ticks,begin-.001),bisect.bisect_right(ticks,end+.001)
        samples=[p for _,p in trace[lo:hi]]
        key=shape('gps:'+route['familyId']+':'+a+':'+b,a,b,samples,(route['familyId'],route['vehicleId']))
        pool[key]=cache[key];shapes.append(key);family_edges[route['familyId'],a,b]=key
    route['shapeSegments']=shapes
    if index%100==0:print('RUNS',index+1,'/',network['observedRuns'],flush=True)
for route in network['routes']:
    if route['scheduleSource']!='catalog_topology':continue
    route['shapeSegments']=[]
    for a,b in zip(route['stops'],route['stops'][1:]):
        if route.get('routeSource')=='gps_proximity_inferred':
            recovery=route['recovery'];events=recovery['events'];i=len(route['shapeSegments'])
            ticks=times[route['familyId'],recovery['vehicleId']];trace=traces[route['familyId'],recovery['vehicleId']]
            lo=bisect.bisect_left(ticks,events[i]['firstMinute']-.001);hi=bisect.bisect_right(ticks,events[i+1]['firstMinute']+.001)
            samples=[p for _,p in trace[lo:hi]]
            key=shape('recovery1:'+route['familyId']+':'+a+':'+b,a,b,samples,(route['familyId'],recovery['vehicleId']))
        else:key=family_edges.get((route['familyId'],a,b)) or shape('road:'+a+':'+b,a,b)
        pool[key]=cache[key];route['shapeSegments'].append(key)
    # Distance is a ranking cost only. These are not estimated timetable offsets.
    route['distanceOffsets']=[0]
    for key,a,b in zip(route['shapeSegments'],route['stops'],route['stops'][1:]):
        meters=pool[key]['meters']
        if meters is None:meters=distance((stops[a]['lat'],stops[a]['lon']),(stops[b]['lat'],stops[b]['lon']))*1.5
        route['distanceOffsets'].append(round(route['distanceOffsets'][-1]+meters,1))
paths=[]
for p in network['footpaths']:
    key=shape('foot:'+p['from']+':'+p['to'],p['from'],p['to'],walking=True)
    if not cache[key]['points']:continue
    pool[key]=cache[key];p['shape']=key;p['meters']=max(1,cache[key]['meters']);p['source']='osm_road_estimate';paths.append(p)
network.update(shapes=pool,footpaths=paths,geometryVersion='local-osm-pool-2',version='jetson-2025-12-31-all+roads2',
               geometryAttribution='© OpenStreetMap contributors / OSM Korea',
               geometryNote='GPS는 외부로 보내지 않고 로컬 도로망에 보정했습니다. 형상은 최대 2m 오차로 단순화하며 공식 최신 노선 확정은 아닙니다.')
if network.get('routeRecoveries'):network['version']+='+recovery1'
for output in (ROOT/'shared/observed_network.json',ROOT/'app/assets/data/observed_network.json'):
    temp=output.with_suffix('.tmp');temp.write_text(json.dumps(network,ensure_ascii=False,separators=(',',':')),encoding='utf-8');temp.replace(output)
save()
report={'source':'https://tiles.osm.kr/download/gyeongsang-non-military.osm.pbf','roadFileSha256':hashlib.sha256((TMP/'gyeongsang.osm.pbf').read_bytes()).hexdigest(),
        'graphNodes':len(data['nodes']),'graphWays':len(data['ways']),'shapes':dict(Counter(s['source'] for s in pool.values())),
        'shapePoolCount':len(pool),'simplificationMeters':2,'gpsExternalTransmission':False,'routeFamilies':network['routeFamilies'],
        'observedRouteFamilies':network['observedRouteFamilies'],'observedRuns':network['observedRuns'],'stopPoints':len(stops),
        'unroutableCatalogIds':[r['familyId'] for r in network['routes'] if r['scheduleSource']=='catalog_topology' and len(r['stops'])<2],
        'method':'Local directed OSM road graph; no turn-restriction relations or lane-level guarantee.'}
(ROOT/'artifacts/road-geometry.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('DONE',report,flush=True)
