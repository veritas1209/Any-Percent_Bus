import json
import sys
from pathlib import Path
from dataclasses import replace

from fastapi.testclient import TestClient
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'tools'))
from app.engine import Engine,Query
from app.main import app
from app.walking import WalkingGraph
from app.geometry import point_on_trace
from local_roads import RoadGraph
from rebuild_motion_traces import match_trace,trace_groups


def test_point_access_obeys_road_connectivity_not_straight_distance():
    g=WalkingGraph((ROOT/'shared/test_walk_graph.bin').read_bytes())
    stops=[{'id':'opposite','lat':35.501,'lon':129.3},{'id':'isolated','lat':35.5005,'lon':129.3}]
    assert g.connections((35.5,129.3),stops,150)==[]
    connected=g.connections((35.5,129.3),stops,350)
    assert [r[0] for r in connected]==['opposite']
    assert connected[0][1]==pytest.approx(293,abs=.2)
    assert any(p[1]==129.301 for p in connected[0][2])
    direct=g.connections((35.5,129.3002),[{'id':'same-edge','lat':35.5,'lon':129.3008}],60)
    assert direct[0][1]==pytest.approx(54.6,abs=.1)


def test_point_search_compares_multiple_stops_and_walk_speed_budget():
    graph=WalkingGraph((ROOT/'shared/test_walk_graph.bin').read_bytes())
    n=json.loads((ROOT/'shared/test_point_network.json').read_text(encoding='utf-8'))
    engine=Engine(n,graph);q=Query('point','target',origin_point={'name':'출발 지점','lat':35.5,'lon':129.3},max_walk=350,walking_speed=1,samples=20)
    fast=next(j for j in engine.search(q) if 'ANY%' in j['tags'])
    assert fast['arrival']==548 and fast['legs'][0]['to']=='far'
    assert fast['legs'][0]['shape']['source']=='osm_pedestrian_access'
    assert fast['places'][0]['id']=='@origin' and fast['walkingMeters']<=350
    for changed in [replace(q,max_walk=200),replace(q,walking_speed=.8)]:
        rows=engine.search(changed);assert min(j['arrival'] for j in rows)==560
    assert engine.search(replace(q,max_walk=0))==[]


def test_place_search_and_point_api_accept_locations_without_a_stop_id():
    client=TestClient(app)
    places=client.get('/v1/places/search',params={'q':'삼산로 288'}).json()['places']
    assert places and all('삼산로' in p['address'] for p in places)
    response=client.post('/v1/journeys/search',json={'origin':'anywhere-a','destination':'anywhere-b','departure':430,'samples':20,
        'origin_point':{'name':'출발 지점','lat':35.499699,'lon':129.417175},'destination_point':{'name':'도착 지점','lat':35.55302,'lon':129.31955}})
    assert response.status_code==200
    rows=response.json()['journeys'];assert rows and rows[0]['places']
    assert all(j['legs'][0]['from']=='@origin' and j['legs'][-1]['to']=='@destination' and j['walkingMeters']<=500 for j in rows)


def test_stationary_gps_and_gaps_are_not_animated_as_uniform_stop_travel():
    n={'shapes':{'s':{'points':[[35.5,129.3],[35.5,129.301],[35.501,129.301]]}}}
    r={'traceChunks':[{'shape':'s','samples':[[420,0],[421,0],[422,91],[423,202]]}]}
    assert point_on_trace(n,r,420.5)==[35.5,129.3]
    assert point_on_trace(n,r,421.5)[1]==pytest.approx(129.3005)
    assert point_on_trace(n,r,425) is None
    samples=[(420,(35.5,129.3),0),(420.5,(35.50001,129.30001),0),(424,(35.501,129.301),20)]
    groups=trace_groups(samples);assert len(groups)==1 and groups[0][0][1]==groups[0][1][1]


def test_motion_match_does_not_force_a_noisy_fix_into_a_side_street():
    data={'nodes':{'1':[35.5,129.3],'2':[35.5,129.301],'3':[35.5,129.302],'4':[35.5005,129.301]},
          'ways':[{'id':1,'pairs':[[1,2],[2,3]],'drive':True,'foot':True,'oneway':'no'},
                  {'id':2,'pairs':[[2,4]],'drive':True,'foot':True,'oneway':'no'}]}
    chunks=match_trace(RoadGraph(data),[(420,(35.5,129.3),20),(420.5,(35.50008,129.301),20),(421,(35.5,129.302),20)])
    assert chunks and max(p[0] for c in chunks for p in c['points'])<35.50004


def test_bundled_vehicle_clock_never_teleports_at_impossible_bus_speed():
    n=json.loads((ROOT/'shared/observed_network.json').read_text(encoding='utf-8'))
    intervals=0
    for route in n['routes']:
        for chunk in route.get('traceChunks',[]):
            for a,b in zip(chunk['samples'],chunk['samples'][1:]):
                intervals+=1
                assert b[0]>a[0] and b[1]>=a[1]
                speed_kmh=(b[1]-a[1])/(b[0]-a[0])*.06
                assert speed_kmh<150,(route['id'],a,b,speed_kmh)
    assert intervals>100000
