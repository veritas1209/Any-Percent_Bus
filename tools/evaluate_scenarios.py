"""Reproducible demo comparisons. These measure model behavior, not traffic prediction accuracy."""
import json
from dataclasses import replace
from datetime import datetime,timezone
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.engine import Engine,Query

demo=json.loads((ROOT/'shared/network.json').read_text(encoding='utf-8'))
observed=json.loads((ROOT/'shared/observed_network.json').read_text(encoding='utf-8'))
base=Query('uc','tower')
cases=[
    ('default',demo,base),
    ('first_bus_plus_3',demo,replace(base,delay=3)),
    ('walk_slow_0.8',demo,replace(base,walking_speed=.8)),
    ('walk_fast_1.6',demo,replace(base,walking_speed=1.6)),
    ('no_walking',demo,replace(base,max_walk=0)),
    ('direct_only',demo,replace(base,max_transfers=0)),
    ('after_last_service',demo,replace(base,departure=1430)),
    ('disconnected',demo,replace(base,destination='remote')),
    ('recorded_transfers',observed,Query(observed['defaultOrigin'],observed['defaultDestination'],departure=430)),
    ('outside_recording',observed,Query(observed['defaultOrigin'],observed['defaultDestination'],departure=480)),
]
rows=[]
for name,network,query in cases:
    engine=Engine(network)
    results=engine.search(query)
    selected=[j for j in results if j['tags']]
    rows.append({'case':name,'source':network['source'],'candidateCount':len(results),'selected':[
        {'tags':j['tags'],'plannedArrival':j['arrival'],'scenarioArrival':j.get('scenario',{}).get('arrival'),
         'successProbability':j['successProbability'],'noServiceProbability':j['noServiceProbability'],
         'p90Arrival':j['p90Arrival'] if j.get('noServiceProbability') is not None and j['noServiceProbability']<=.1 else None,
         'routes':[engine.routes[l['routeId']]['number'] for l in j['legs'] if l['kind']=='ride'],
         'transfers':j['transfers'],'walkingMeters':j['walkingMeters']} for j in selected]})
result={'generatedAt':datetime.now(timezone.utc).isoformat(),'seed':base.seed,'samples':base.samples,
        'warning':'Simulation and recorded passage-time examples; not measured travel-time prediction accuracy.','cases':rows}
path=ROOT/'artifacts/scenarios.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('Evaluated',len(rows),'scenarios:',path)
