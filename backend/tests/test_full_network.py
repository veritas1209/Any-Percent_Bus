import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.engine import Engine,Query
from app.main import app,OBSERVED,ENGINES


def test_full_inventory_and_search_include_every_non_sentinel_id():
    raw=json.loads((Path(__file__).resolve().parents[2]/'shared/bustracker_catalog.json').read_text(encoding='utf-8'))
    catalog=[r for r in OBSERVED['routes'] if r['scheduleSource']=='catalog_topology']
    assert {r['familyId'] for r in catalog}=={r['id'] for r in raw['routes']}-{'0'}
    raw_ids={s['id'] for s in raw['stops']}-{'0'}
    assert raw_ids<={s['id'] for s in OBSERVED['stops']}
    assert {s['id'] for s in OBSERVED['stops']}-raw_ids=={'ref:31531','ref:31516','ref:31532'}
    assert len(catalog)==256 and len(OBSERVED['stops'])==4953
    client=TestClient(app)
    assert client.get('/v1/coverage').json()['observedRouteFamilies']==247
    assert len(client.get('/v1/routes/search').json()['routes'])==256
    route=next(r for r in catalog if r['number']=='722')
    matches=client.get('/v1/stops/search',params={'q':'722번'}).json()['stops']
    assert set(route['stops'])<={s['id'] for s in matches}
    sid=route['stops'][0]
    assert any(s['id']==sid for s in client.get('/v1/stops/search',params={'q':sid}).json()['stops'])


def test_all_recorded_runs_have_valid_time_and_resolvable_road_geometry():
    stops={s['id'] for s in OBSERVED['stops']};pool=OBSERVED['shapes']
    recorded=[r for r in OBSERVED['routes'] if r['scheduleSource']=='replay_observed']
    assert len(recorded)==OBSERVED['observedRuns']==1187 and len({r['familyId'] for r in recorded})==247
    for r in recorded:
        assert set(r['stops'])<=stops
        assert len(r['shapeSegments'])==len(r['stops'])-1
        assert all(k in pool and len(pool[k]['points'])>=2 for k in r['shapeSegments'])
        assert all(b>a for a,b in zip(r['offsets'],r['offsets'][1:]))
        assert r['departures'][0]+r['offsets'][-1]<480


def test_catalog_only_connection_never_invents_times_or_probabilities():
    engine=ENGINES['observed']
    rows=engine.search(Query(OBSERVED['defaultOrigin'],OBSERVED['defaultDestination'],departure=480,samples=20))
    assert rows and all(j['scheduleAvailable'] is False for j in rows)
    assert all(j['arrival'] is None and j['successProbability'] is None for j in rows)
    assert all('trip' not in l and 'depart' not in l and 'arrive' not in l for j in rows for l in j['legs'])
    assert all(l['routeId'].startswith('cat:') for j in rows for l in j['legs'] if l['kind']=='ride')
    assert all(j['transfers']<=2 and j['walkingMeters']<=500 for j in rows)


def test_late_transfer_stop_is_not_lost_to_a_global_500_state_beam():
    ids=[f's{i}' for i in range(610)]
    network={'stops':[{'id':s} for s in ['o','d',*ids]],'footpaths':[],
             'routes':[{'id':'long','stops':['o',*ids],'departures':[0],'offsets':list(range(611)),'delaySamples':[0]},
                       {'id':'connection','stops':[ids[-1],'d'],'departures':[611],'offsets':[0,1],'delaySamples':[0]}]}
    result=Engine(network).search(Query('o','d',departure=0,max_transfers=1,max_walk=0,samples=20))
    assert result and result[0]['arrival']==612
