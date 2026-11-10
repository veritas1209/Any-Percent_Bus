"""Exercise one directed catalog edge per routable route with no invented timetable."""
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.engine import Engine,Query

network=json.loads((ROOT/'shared/observed_network.json').read_text(encoding='utf-8'))
engine=Engine(network);passed=[];missing=[];started=time.perf_counter()
for r in network['routes']:
    if r.get('scheduleSource')!='catalog_topology':continue
    if len(r['stops'])<2:
        missing.append({'routeId':r['familyId'],'number':r['number'],'reason':'Fewer than two non-sentinel stop points in source'})
        continue
    result=engine.search(Query(r['stops'][0],r['stops'][1],departure=480,max_transfers=0,max_walk=0,samples=20))
    assert result and all(j['arrival'] is None for j in result),r['familyId']
    passed.append(r['familyId'])
report={'catalogRoutes':network['catalogRouteCount'],'stopPointIds':len(network['stops']),
        'recordedFamilies':network['observedRouteFamilies'],'recordedRuns':network['observedRuns'],
        'routableCatalogRoutesChecked':len(passed),'passedIds':passed,'missingSourceConnections':missing,
        'inferredPartialSections':network.get('routeRecoveries',[]),
        'elapsedSeconds':round(time.perf_counter()-started,2),
        'scope':'One directed catalog edge per usable route; not every origin/destination pair or real-world route validation.'}
(ROOT/'artifacts/full-network-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('passedIds','missingSourceConnections')}))
