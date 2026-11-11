"""Derive small, traceable route repairs from inspected public source snapshots."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from build_service_network import clip, point_at, point_distance, project_stops
from local_roads import compact, length

ROOT = Path(__file__).resolve().parents[1]


def main():
    original = ROOT/'tmp/service-network-original.json'
    network = json.loads((original if original.exists() else ROOT/'shared/service_network.json').read_text(encoding='utf-8'))
    assert network.get('geometryVersion') != 'ulsan-multi-source-3', 'Rebuild the original source snapshot first'
    stops = {stop['id']:stop for stop in network['stops']}
    naver = []
    pairs = defaultdict(list)
    for path in sorted((ROOT/'tmp/naver-bus').glob('*.json')):
        if path.name.startswith('search-'):
            continue
        snapshot = json.loads(path.read_text(encoding='utf-8'))
        route = snapshot['data']
        points = [[p['y'],p['x']] for p in route['points']]
        bus_stops = [dict(id=str(s['displayCode']), lat=s['point']['y'], lon=s['point']['x']) for s in route['busStops']]
        lengths, progress = project_stops(points, bus_stops)
        row = dict(snapshot=snapshot, route=route, points=points, lengths=lengths, progress=progress,
            codes=[s['id'] for s in bus_stops], sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        naver.append(row)
        for index in range(len(bus_stops)-1):
            pairs[(route['name'].split('(')[0].strip(),*row['codes'][index:index+2])].append((row,index))
    changes, sources, repaired, stop_changes = {}, {}, [], {}
    reviewed = ROOT/'shared/service_stop_supplements.json'
    if reviewed.exists():
        positions=json.loads(reviewed.read_text(encoding='utf-8'))
        stop_changes=positions['stops']
        sources.update(positions['sources'])
        for identity,patch in stop_changes.items():
            stops[identity].update(patch)
    by_code = defaultdict(list)
    for stop in stops.values():
        by_code[stop['publicId']].append(stop)
    for row in naver:
        if reviewed.exists():
            break
        if row['route'].get('city',{}).get('name') != '울산':
            continue
        for item in row['route']['busStops']:
            for stop in by_code.get(str(item['displayCode']),[]):
                if stop['name'].replace(' ','') != item['name'].replace(' ',''):
                    continue
                point = item['point']['y'],item['point']['x']
                gap = point_distance((stop['lat'],stop['lon']),point)
                if 40<gap<=1000:
                    source_id='naver:'+str(row['route']['id'])
                    sources[source_id]=dict(url=row['snapshot']['url'],retrievedAt=row['snapshot']['retrievedAt'],sha256=row['sha256'],name=row['route']['longName'])
                    stop_changes[stop['id']]=dict(lat=point[0],lon=point[1],locationSource='naver_bus_stop',
                        locationSourceId=source_id,previousLocation=dict(lat=stop['lat'],lon=stop['lon']))
                    stop.update(lat=point[0],lon=point[1])
    for route in network['routes']:
        own = [stops[s]['publicId'] for s in route['stops']]
        poor = []
        for i,key in enumerate(route['shapeSegments']):
            p = network['shapes'][key]['points']
            if not p or any(point_distance(pnt,(stops[s]['lat'],stops[s]['lon']))>80
                            for pnt,s in zip((p[0],p[-1]),route['stops'][i:i+2])):
                poor.append(i)
        if not poor:
            continue
        exact = [row for row in naver if row['codes'] == own]
        if exact:
            row = exact[0]
            lengths, progress = row['lengths'], row['progress']
            errors = [point_distance(point_at(row['points'],lengths,progress[i]),(stops[s]['lat'],stops[s]['lon']))
                      for i,s in enumerate(route['stops'])]
            indices=range(len(own)-1) if max(errors)<=80 and all(b>a+1 for a,b in zip(progress,progress[1:])) else poor
            selected = [(i,row,clip(row['points'],lengths,progress[i],progress[i+1])) for i in indices
                        if errors[i]<=80 and errors[i+1]<=80 and progress[i+1]>progress[i]+1]
            match = 'complete ordered public-stop sequence'
        else:
            selected = []
            for i in poor:
                options = []
                for row,j in pairs.get((route['number'],*own[i:i+2]),[]):
                    # Match surrounding stops as well when the route visits a stop twice.
                    context = sum(0<=i+d<len(own) and 0<=j+d<len(row['codes']) and own[i+d]==row['codes'][j+d]
                                  for d in range(-3,5))
                    line = clip(row['points'],row['lengths'],row['progress'][j],row['progress'][j+1])
                    error = max(point_distance(line[k],(stops[route['stops'][i+side]]['lat'],stops[route['stops'][i+side]]['lon']))
                                for k,side in ((0,0),(-1,1)))
                    if error<=80 and length(line)>1:
                        options.append((-context,error,row['route']['id'],row,line))
                if options:
                    chosen = min(options,key=lambda value:value[:3])
                    selected.append((i,chosen[3],chosen[4]))
            match = 'ordered adjacent public-stop pair and surrounding stop context'
        for i,row,line in selected:
            source_id = 'naver:'+str(row['route']['id'])
            sources[source_id] = dict(url=row['snapshot']['url'], retrievedAt=row['snapshot']['retrievedAt'],
                sha256=row['sha256'], name=row['route']['longName'])
            changes[route['shapeSegments'][i]] = dict(points=compact(line),meters=round(length(line),1),
                source='naver_bus_route',sourceId=source_id)
        if selected:
            repaired.append(dict(routeId=route['id'],number=route['number'],segments=len(selected),match=match))
    reviewed_roads = ROOT/'shared/service_road_connections.json'
    if reviewed_roads.exists():
        roads=json.loads(reviewed_roads.read_text(encoding='utf-8'))
        for key,shape in roads['shapes'].items():
            expected=hashlib.sha256(json.dumps(network['shapes'][key],sort_keys=True,separators=(',',':')).encode()).hexdigest()
            assert expected==shape['proof']['baseShapeSha256'], 'Reviewed road source changed'
            changes[key]=shape
        sources.update(roads['sources'])
    result = dict(version=1, sources=sources, shapes=changes, stops=stop_changes,routes={}, geometryRepairs=repaired)
    schedules = ROOT/'shared/service_schedule_supplements.json'
    if schedules.exists():
        data=json.loads(schedules.read_text(encoding='utf-8'))
        result['sources'].update(data['sources'])
        result['routes']=data['routes']
        result['extraRoutes']=data['extraRoutes']
    (ROOT/'shared/service_supplements.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps(dict(repairedRoutes=len(repaired),segments=len(changes),sources=len(sources)),ensure_ascii=False))


if __name__=='__main__':
    main()
