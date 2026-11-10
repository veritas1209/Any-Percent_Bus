"""Record hashes and extraction assumptions for the authorized historical sample."""
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'tmp/jetson-source'
files=[]
for name in ('gps_replay.csv','route_stops_named.csv','route_names_manual.csv'):
    path=SOURCE/name
    files.append({'name':name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
count=0;vehicles=set();routes=set();first=last=None
with (SOURCE/'gps_replay.csv').open(encoding='utf-8-sig') as f:
    reader=csv.reader(f);next(reader)
    for row in reader:
        count+=1;first=first or row[0];last=row[0];vehicles.add(row[1]);routes.add(row[4])
network=json.loads((ROOT/'shared/observed_network.json').read_text(encoding='utf-8'))
result={'origin':'Authorized read-only copy from the user Jetson BusTracker directory','files':files,
        'recording':{'start':first,'end':last,'timezone':'Asia/Seoul','rows':count,'rawDeviceIds':len(vehicles),'rawRouteIdsIncludingZero':len(routes)},
        'extraction':{'catalogRouteCount':network['catalogRouteCount'],'observedRouteFamilies':network['observedRouteFamilies'],'observedRuns':network['observedRuns'],'stopPointIds':len(network['stops']),
                      'method':'First sample after passed-point ID changes; split duplicate-point loops and gaps over 8 minutes',
                      'ambiguousTimestampsExcluded':network['ambiguousTimestampsExcluded'],
                      'inferredPartialSections':network.get('routeRecoveries',[]),
                      'arrivalQuality':'Passage-time proxy; boarding service at each point is not field-validated',
                      'futureTrips':'Not extrapolated beyond the recording',
                      'walking':'Existing inter-stop links plus query-time access/egress to all reachable stops within cumulative walking budget; local OSM pedestrian graph, not surveyed paths',
                      'places':'37,427 local OSM place/address entries plus arbitrary map pins; incomplete coverage; see location-assets.json',
                      'roadGeometry':'Direction-aware local GPS trace matching without forced stop-centroid anchors; actual sample clock, pauses and explicit gaps; no external GPS transmission; see motion-build.json',
                      'uncertainty':'Synthetic delay samples, not fitted or calibrated to historical prediction errors'},
        'warning':'A replay loop is not a new independent calendar day. The recording is not a current official timetable.'}
(ROOT/'artifacts/provenance.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print('Recorded provenance for',count,'rows')
