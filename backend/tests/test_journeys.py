import copy
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.engine import Engine,Query
from app.main import app,NETWORK


@pytest.fixture
def engine():
    return Engine(copy.deepcopy(NETWORK))


def test_any_and_safe_are_different_and_replay_matches_timetable(engine):
    query=Query('uc','tower',samples=100)
    results=engine.search(query)
    any_route=next(j for j in results if 'ANY%' in j['tags'])
    safe_route=next(j for j in results if 'SAFE' in j['tags'])
    assert any_route['id'] != safe_route['id']
    assert any_route['arrival'] < safe_route['arrival']
    assert any_route['p90Arrival'] > safe_route['p90Arrival']
    assert safe_route['successProbability'] > any_route['successProbability']
    assert all(engine.replay(j,query)['arrival']==j['arrival'] for j in results)


def test_delay_causes_missed_connection_and_next_vehicle(engine):
    j=next(j for j in engine.search(Query('uc','tower',samples=20)) if 'ANY%' in j['tags'])
    ok=engine.replay(j,Query('uc','tower',delay=0))
    late=engine.replay(j,Query('uc','tower',delay=3))
    assert not ok['missed']
    assert late['missed']==['demo-b']
    assert late['arrival']-ok['arrival']==20
    assert late['legs'][-1]['trip']==pytest.approx(j['legs'][-1]['trip']+20)


def test_walking_and_transfer_constraints(engine):
    no_walk=engine.search(Query('uc','tower',max_walk=0,samples=20))
    assert all(not any(l['kind']=='walk' for l in j['legs']) for j in no_walk)
    direct=engine.search(Query('uc','tower',max_transfers=0,samples=20))
    assert direct and all(j['transfers']==0 for j in direct)
    assert engine.search(Query('tower','remote',samples=20))==[]
    assert engine.search(Query('uc','tower',departure=1430,samples=20))==[]


def test_walking_speed_changes_connection(engine):
    fast=engine.search(Query('uc','tower',walking_speed=1.6,samples=20))
    slow=engine.search(Query('uc','tower',walking_speed=.8,samples=20))
    fast_b=next(j for j in fast if any(l.get('routeId')=='demo-b' for l in j['legs']))
    slow_b=next(j for j in slow if any(l.get('routeId')=='demo-b' for l in j['legs']))
    assert slow_b['arrival']>fast_b['arrival']


def test_reproducibility_and_last_service(engine):
    q=Query('uc','tower',samples=40)
    assert engine.search(q)==engine.search(q)
    j=engine.search(Query('uc','tower',departure=1380,samples=20))[0]
    replay=engine.replay(j,Query('uc','tower',departure=1380,delay=30))
    assert replay['arrival'] is None or replay['arrival']>=j['arrival']


def test_api_inputs_network_and_clock():
    client=TestClient(app)
    assert client.get('/v1/health').json()['status']=='ok'
    assert len(client.get('/v1/network').json()['routes'])==5
    assert {s['id'] for s in client.get('/v1/stops/search',params={'q':'태화강'}).json()['stops']}=={'hwajung','station','station-b'}
    assert client.post('/v1/journeys/search',json={'origin':'uc','destination':'tower','samples':20}).json()['journeys']
    assert client.post('/v1/journeys/search',json={'origin':'uc','destination':'tower','walking_speed':0}).status_code==422
    assert client.post('/v1/journeys/search',json={'origin':'missing','destination':'tower'}).status_code==400
    assert client.get('/v1/vehicles?minute=550').json()['vehicles']
    assert client.post('/v1/integration/sync').status_code==503


def test_final_walk_and_walking_only_journeys_obey_the_total_budget():
    fixture=Path(__file__).resolve().parents[2]/'shared/test_walk_network.json'
    routing=Engine(json.loads(fixture.read_text()))
    results=routing.search(Query('a','c',walking_speed=1,max_walk=120,max_transfers=0,samples=20))
    assert results and results[0]['arrival']==547
    assert results[0]['walkingMeters']==120 and results[0]['transfers']==0
    assert [l['kind'] for l in results[0]['legs']]==['ride','walk']
    assert routing.search(Query('a','c',walking_speed=1,max_walk=119,samples=20))==[]
    walk=routing.search(Query('b','c',walking_speed=1,max_walk=120,samples=20))[0]
    assert walk['arrival']==542 and walk['transfers']==0


def test_monte_carlo_matches_an_analytic_half_success_case():
    fixture=Path(__file__).resolve().parents[2]/'shared/test_probability_network.json'
    routing=Engine(json.loads(fixture.read_text()))
    # First vehicle delay is 0 or 2 with equal chance. The connection at 11
    # succeeds only for delay 0; otherwise next vehicle arrives at 34.
    journey=routing.search(Query('o','d',departure=0,samples=1000))[0]
    assert abs(journey['successProbability']-.5)<.04
    assert abs(journey['expectedArrival']-24.5)<.8
    assert journey['p90Arrival']==34
    assert journey['noServiceProbability']==0
