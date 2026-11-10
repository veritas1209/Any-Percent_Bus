import importlib.util
import sys
import threading
import types
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.bustracker import observe,observations
from app.history import generate_history


def test_replay_arrivals_deduplicate_and_separate_cycles(tmp_path):
    network={'stops':[{'id':'s','lat':35.5,'lon':129.4}], 'routes':[{'id':'r','stops':[{'stopId':'s'}]}]}
    vehicle={'vehicleId':'v','routeId':'r','tripId':'1:v','lat':35.5,'lon':129.4,'speedKph':0,'virtualEpochSec':123}
    path=tmp_path/'arrivals.db'
    assert observe(network,{'vehicles':[vehicle]},path)==1
    assert observe(network,{'vehicles':[vehicle]},path)==0
    vehicle['tripId']='2:v'
    assert observe(network,{'vehicles':[vehicle]},path)==1
    assert len(observations(path))==2
    vehicle['tripId']='3:v';vehicle['speedKph']=60
    assert observe(network,{'vehicles':[vehicle]},path)==0


def test_synthetic_history_keeps_vehicle_delay_consistent():
    network={'routes':[{'id':'r','stops':['a','b'],'offsets':[0,8],'departures':[540,560],'delaySamples':[0,2,5]}]}
    rows=generate_history(network,days=21,seed=4)
    assert len(rows)==84
    assert all(r['source']=='simulated' for r in rows)
    for index in range(0,len(rows),2):
        assert rows[index]['delayMinutes']==rows[index+1]['delayMinutes']
        assert rows[index+1]['arrivalMinute']-rows[index]['arrivalMinute']==8


def test_bustracker_readonly_api_auth_snapshot_and_clock():
    source=Path(__file__).resolve().parents[2]/'integration/bustracker/api/integration.py'
    fake_db=types.ModuleType('db');fake_db.get_route_list=lambda:[{'route_id':'r','route_no':'124','display_name':'test'}]
    fake_state=types.ModuleType('state');fake_state.LOCK=threading.Lock()
    fake_state.ROUTES={'r':types.SimpleNamespace(stops=[(1,'s',35.5,129.4)])}
    fake_state.STOP_NAMES={'s':'정류장'};fake_state.valid_coord=lambda lat,lon:True
    fake_state.REPLAY_STATE={'cycle':2,'virtualEpochSec':1000,'speed':3}
    fake_state.TRACKS={'v':types.SimpleNamespace(trail=[(1000,35.5,129.4,0)],is_bus=True,matched_route='r'),
                       'stale':types.SimpleNamespace(trail=[(800,35.5,129.4,0)],is_bus=True,matched_route='r')}
    with patch.dict(sys.modules,{'db':fake_db,'state':fake_state}),patch.dict('os.environ',{'BUSTRACKER_INTEGRATION_KEY':'test-key','BUSTRACKER_MODE':'D'}):
        spec=importlib.util.spec_from_file_location('bt_integration_test',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        app=FastAPI();app.include_router(module.router);client=TestClient(app)
        assert client.get('/integration/v1/network').status_code==401
        headers={'X-Integration-Key':'test-key'}
        snapshot=client.get('/integration/v1/network',headers=headers).json()
        assert snapshot['routes'][0]['stops'][0]['stopId']=='s'
        assert snapshot['stops'][0]['name']=='정류장'
        assert client.get('/integration/v1/status',headers=headers).json()['replay']['cycle']==2
        vehicles=client.get('/integration/v1/vehicles',headers=headers).json()
        assert vehicles['source']=='replay_observed'
        assert len(vehicles['vehicles'])==1
        assert vehicles['vehicles'][0]['tripId']=='2:v:r'
        assert vehicles['vehicles'][0]['speedKph']==0
        assert fake_state.REPLAY_STATE['virtualEpochSec']==1000
        with patch.dict('os.environ',{'BUSTRACKER_INTEGRATION_KEY':''}):
            assert client.get('/integration/v1/status',headers=headers).status_code==503
