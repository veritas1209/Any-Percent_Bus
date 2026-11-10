"""Audit sparse routes and recover only supported, explicitly inferred GPS sections.

Uses authorized local BusTracker copies. No web requests, official timetable
claims, reverse-direction duplication, or production database writes.
"""
import csv
import hashlib
import json
import math
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tmp/jetson-source';EXTRA=ROOT/'tmp/jetson-extra'
IDS=['195000130','195900010','196000041','196000071','196000131','196000613','196000810']


def distance(a,b):
    return math.hypot((a[0]-b[0])*111000,(a[1]-b[1])*91000)


def nearby_events(rows,references,max_distance=30,max_speed=10,min_separation=80):
    """Low-speed GPS proximity is evidence of a possible stop, not proven service."""
    events=[]
    for row in sorted(rows,key=lambda r:r[0]):
        lat,lon=float(row[6]),float(row[5]);speed=float(row[7])
        if not (35<lat<36 and 128<lon<130 and 0<=speed<=max_speed):continue
        reference=min(references,key=lambda s:distance((lat,lon),(float(s['lat']),float(s['lon']))))
        error=distance((lat,lon),(float(reference['lat']),float(reference['lon'])))
        if error>max_distance:continue
        minute=int(row[0][11:13])*60+int(row[0][14:16])+int(row[0][17:19])/60
        if events and reference['stop_id']==events[-1]['referenceStopId']:
            events[-1]['lastMinute']=minute;events[-1]['supportSamples']+=1
            continue
        point=(float(reference['lat']),float(reference['lon']))
        if events and distance(point,(events[-1]['lat'],events[-1]['lon']))<min_separation:continue
        events.append({'id':'ref:'+reference['stop_id'],'referenceStopId':reference['stop_id'],
                       'name':reference['name'],'lat':point[0],'lon':point[1],
                       'firstMinute':minute,'lastMinute':minute,'supportSamples':1,
                       'firstMatchDistanceMeters':round(error,1),'firstMatchKph':speed})
    return events


def main():
    network=json.loads((ROOT/'shared/observed_network.json').read_text(encoding='utf-8'))
    catalog={r['familyId']:r for r in network['routes'] if r['scheduleSource']=='catalog_topology'}
    names={r['route_id']:r['route_no'] for r in csv.DictReader((SOURCE/'route_names_manual.csv').open(encoding='utf-8-sig'))}
    static=defaultdict(list);gps=defaultdict(list)
    for row in csv.DictReader((SOURCE/'route_stops_named.csv').open(encoding='utf-8-sig')):
        if row['route_id'] in IDS:static[row['route_id']].append(row)
    with (SOURCE/'gps_replay.csv').open(encoding='utf-8-sig') as f:
        reader=csv.reader(f);next(reader)
        for row in reader:
            if row[4] in IDS:gps[row[4]].append(row)
    references=list(csv.DictReader((EXTRA/'bus_stops.csv').open(encoding='utf-8-sig')))
    inspection=json.loads((EXTRA/'db-inspection.json').read_text(encoding='utf-8'))
    recoveries=[];details=[]
    for rid in IDS:
        rows=gps[rid];valid=[r for r in static[rid] if r['spot_id']!='0']
        number=names.get(rid)
        related=[r['familyId'] for r in catalog.values() if number and r['number']==number and r['familyId']!=rid and len(r['stops'])>=2]
        events=nearby_events(rows,references)
        # Do not turn an unidentified route or a lone depot point into a route.
        supported=bool(number) and len(events)>=2 and len({e['id'] for e in events})>=2
        if supported:
            recoveries.append({'routeId':rid,'number':number,'vehicleId':rows[0][1],
                'kind':'gps_proximity_inferred','partial':True,'events':events,
                'originalStopIds':[r['spot_id'] for r in valid],
                'disclaimer':'GPS가 정류장 가까이 저속으로 지나간 추정 구간입니다. 실제 정차·탑승 가능 여부와 전체 노선은 미확인입니다.'})
        history=inspection.get('gpsSamples',{}).get(rid,[])
        raw_coordinates={(round(float(r[6]),5),round(float(r[5]),5)) for r in rows}
        new_coordinates={(round(r['lat'],5),round(r['lon'],5)) for r in history}-raw_coordinates
        detail={'routeId':rid,'number':number,'sourceStopCount':len(valid),'rawRows':len(rows),
                'passedPointIds':dict(Counter(r[10] for r in rows)),
                'distinctCoordinates':len({(r[6],r[5]) for r in rows}),
                'databaseStopRows':len(inspection['stops'][rid]),
                'databaseHistorySamples':len(history),'newCoordinatesInHistorySample':len(new_coordinates),
                'sameNumberRoutableIds':related,
                'recovered':supported,'recoveredStopCount':len(events) if supported else 0}
        if rid=='196000041':detail['idRuleNumberSuggestion']='울주04'
        if rid=='195900010':detail['idRuleNumberSuggestion']='순환1'
        details.append(detail)
    hashes=[]
    for path in (SOURCE/'gps_replay.csv',SOURCE/'route_stops_named.csv',EXTRA/'bus_stops.csv',EXTRA/'stop_routes.csv'):
        hashes.append({'name':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    result={'version':1,'method':{'maxGpsDistanceMeters':30,'maxKph':10,'minStopSeparationMeters':80,
            'arrivalTimesInferred':False,'boardingServiceVerified':False},'sourceFiles':hashes,'routes':recoveries,'sparseRouteDetails':details}
    (ROOT/'shared/route_recoveries.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    report=dict(result,investigation={'databaseReadOnly':True,'productionServiceChanged':False,
                'historyScope':'150 rows at each of five indexed positions per device; sampled history, not a full-table scan',
                'databaseStopRowsMatchSparseCsv':True,
                'stopRoutesExtra':'Same-sequence terminal associations do not establish a directional stop sequence',
                'gpsExternalTransmission':False})
    (ROOT/'artifacts/missing-route-investigation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'recoveries':[(r['routeId'],[e['name'] for e in r['events']]) for r in recoveries],
                      'related':{d['routeId']:d['sameNumberRoutableIds'] for d in details}},ensure_ascii=False))


if __name__=='__main__':main()
