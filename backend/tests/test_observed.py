import csv
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.engine import Query
from app.main import app,OBSERVED,ENGINES
from app.replay_feed import ReplayFeed


def test_observed_runs_use_recorded_window_and_no_future_departures():
    engine=ENGINES['observed']
    rows=engine.search(Query(OBSERVED['defaultOrigin'],OBSERVED['defaultDestination'],departure=430,samples=20))
    assert rows
    assert any(j['transfers']<=2 for j in rows)
    assert all(engine.replay(j,Query(OBSERVED['defaultOrigin'],OBSERVED['defaultDestination'],departure=430))['arrival']==j['arrival'] for j in rows)
    assert all(j['source']=='replay_observed' and j['delaySource']=='simulated' for j in rows)
    assert all(len(r['departures'])==1 and 420<=r['departures'][0]<480 for r in OBSERVED['routes'] if r['scheduleSource']=='replay_observed')
    outside=engine.search(Query(OBSERVED['defaultOrigin'],OBSERVED['defaultDestination'],departure=480,samples=20))
    assert outside and all(j['arrival'] is None and j['source']=='catalog_topology' for j in outside)
    client=TestClient(app)
    assert len(client.get('/v1/network?dataset=observed').json()['stops'])==4950
    payload={'dataset':'observed','origin':OBSERVED['defaultOrigin'],'destination':OBSERVED['defaultDestination'],'departure':430,'samples':20}
    response=client.post('/v1/journeys/search',json=payload)
    assert response.status_code==200 and response.json()['journeys']
    assert response.json()['source']=='replay_observed'
    assert client.get('/v1/network?dataset=missing').status_code==422


def test_default_api_uses_bustracker_numbers_and_recorded_routes():
    client=TestClient(app)
    network=client.get('/v1/network').json()
    assert network['source']=='replay_observed'
    assert {'124','114','134','224','741','722','772'}<={r['number'] for r in network['routes']}
    assert network['routeFamilies']==256
    assert all(r['familyId'] and r['vehicleId'] and r['shapeSegments'] for r in network['routes'] if r['scheduleSource']=='replay_observed')
    response=client.post('/v1/journeys/search',json={'origin':network['defaultOrigin'],'destination':network['defaultDestination'],'samples':20})
    assert response.status_code==200
    journeys=response.json()['journeys']
    assert journeys and all(j['source']=='replay_observed' for j in journeys)
    assert all(l['routeId'].startswith('obs:') for j in journeys for l in j['legs'] if l['kind']=='ride')
    assert client.get('/v1/vehicles').json()['positionMethod']=='road_shape_interpolation'


def test_raw_replay_keeps_latest_nonfuture_sample_and_separates_cycles(tmp_path):
    path=tmp_path/'gps.csv'
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(range(12))
        w.writerow(['2025-12-31 07:00:00','v','','','r',129.4,35.5,0,'','','s',1])
        w.writerow(['2025-12-31 07:00:10','v','','','r',129.41,35.51,20,'','','s',1])
    feed=ReplayFeed(path,{'routes':[],'stops':[]})
    first=feed.snapshot(elapsed=5);second=feed.snapshot(elapsed=10);loop=feed.snapshot(elapsed=16)
    assert first['vehicles'][0]['lon']==129.4
    assert second['vehicles'][0]['lon']==129.41
    assert loop['vehicles'][0]['lon']==129.4
    assert first['vehicles'][0]['tripId']!=loop['vehicles'][0]['tripId']
    assert first['virtualEpochSec']>=first['vehicles'][0]['virtualEpochSec']
