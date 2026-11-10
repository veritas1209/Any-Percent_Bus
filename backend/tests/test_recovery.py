import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'tools'))
from app.main import app,OBSERVED,ENGINES
from app.engine import Query
from recover_sparse_routes import nearby_events


def test_recovered_81_is_only_a_partial_candidate_without_timetable():
    route=next(r for r in OBSERVED['routes'] if r['id']=='cat:196000810')
    assert route['partial'] and route['routeSource']=='gps_proximity_inferred'
    assert route['stops']==['ref:31531','ref:31516','ref:31532']
    assert route['departures']==[] and len(route['sourceCatalogStops'])==1
    assert all(OBSERVED['shapes'][key]['points'] for key in route['shapeSegments'])
    rows=ENGINES['observed'].search(Query(route['stops'][0],route['stops'][-1],departure=430,max_walk=0,max_transfers=0,samples=20))
    assert rows and all(j['arrival'] is None and j['successProbability'] is None and j['scheduleAvailable'] is False for j in rows)
    assert all(l['routeId']=='cat:196000810' for j in rows for l in j['legs'])
    coverage=TestClient(app).get('/v1/coverage').json()
    assert coverage['recoveredCatalogIds']==['196000810'] and len(coverage['unroutableCatalogIds'])==6


def test_sparse_variants_are_not_filled_by_copying_another_direction():
    details=json.loads((ROOT/'shared/route_recoveries.json').read_text(encoding='utf-8'))
    assert len(details['sparseRouteDetails'])==7
    assert details['method']['arrivalTimesInferred'] is False and details['method']['boardingServiceVerified'] is False
    catalog={r['familyId']:r for r in OBSERVED['routes'] if r['scheduleSource']=='catalog_topology'}
    for rid,related in [('195000130','195000135'),('196000071','196000070'),('196000131','196000130')]:
        assert len(catalog[rid]['stops'])<2 and len(catalog[related]['stops'])>2
        assert next(d for d in details['sparseRouteDetails'] if d['routeId']==rid)['sameNumberRoutableIds']==[related]
    assert catalog['195900010']['numberKnown'] is False
    assert catalog['196000041']['numberKnown'] is False


def test_proximity_recovery_rejects_driveby_jitter_and_zero_coordinates():
    refs=[{'stop_id':'a','name':'A','lat':'35.50','lon':'129.30'},
          {'stop_id':'b','name':'B','lat':'35.51','lon':'129.30'}]
    def sample(t,lat,speed):return [f'2025-12-31 07:{t}:00','v','','','r','129.30',str(lat),str(speed)]
    assert nearby_events([sample('00',35.50,0),sample('01',35.50001,1),sample('02',35.51,30)],refs)[0]['supportSamples']==2
    assert len(nearby_events([sample('00',35.50,0),sample('02',35.51,30)],refs))==1
    assert nearby_events([sample('00',0,0)],refs)==[]
