import json
from pathlib import Path

from app.engine import Engine, Query
from app import engine as engine_module
from app.main import app
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


def test_unlimited_walking_uses_preferences_and_keeps_the_fastest_route():
    network = {'stops':[{'id':s} for s in ('o','near','far','d')], 'routes':[
        {'id':'fast','stops':['far','d'],'offsets':[0,10],'departures':[15],'delaySamples':[0]},
        {'id':'shortwalk','stops':['near','d'],'offsets':[0,10],'departures':[20],'delaySamples':[0]}],
        'footpaths':[{'from':'o','to':'far','meters':800},{'from':'o','to':'near','meters':50}]}
    engine = Engine(network)
    def search(penalty):
        return engine.search(Query('o','d',departure=0,max_walk=None,walking_penalty=penalty,max_transfers=0,samples=20))
    less = search(2)
    willing = search(.25)
    assert next(l['routeId'] for l in less[0]['legs'] if l['kind']=='ride') == 'shortwalk'
    assert next(l['routeId'] for l in willing[0]['legs'] if l['kind']=='ride') == 'fast'
    assert '추천' in less[0]['tags']
    assert next(j for j in less if 'ANY%' in j['tags'])['arrival'] == 25
    network['routes'] = [dict(network['routes'][0],departures=[100])]
    network['footpaths'] = [{'from':'o','to':'far','meters':6000}]
    assert Engine(network).search(Query('o','d',departure=0,max_walk=None,samples=20))[0]['walkingMeters'] == 6000
    assert Engine(network).search(Query('o','d',departure=0,max_walk=5000,samples=20)) == []


def test_1415_campus_route_uses_the_near_stop_and_has_a_continuous_bridge_shape():
    network = json.loads((ROOT/'shared/service_network.json').read_text(encoding='utf-8'))
    rows = Engine(network).search(Query('campus','upsquare',departure=855,max_walk=None,walking_penalty=1,
        max_transfers=1,samples=20,origin_point={'name':'campus','lat':35.4972505,'lon':129.4158209},
        destination_point={'name':'upsquare','lat':35.5412587,'lon':129.3388543}))
    fastest = next(row for row in rows if 'ANY%' in row['tags'])
    ride = next(leg for leg in fastest['legs'] if leg['kind']=='ride')
    stop = next(stop for stop in network['stops'] if stop['id']==ride['from'])
    assert stop['publicId'] == '27121'
    assert fastest['walkingMeters'] < 700
    route = next(route for route in network['routes'] if route['id']=='its:194000091')
    assert all(network['shapes'][key]['points'] for key in route['shapeSegments'])
    bridge = network['shapes'][route['shapeSegments'][61]]
    assert bridge['source'] in ('ulsan_its_osm_connected','naver_bus_route')
    assert len(bridge['points'])>20 and bridge['meters']>5000


def test_deadline_pruning_preserves_wide_walk_two_transfer_results(monkeypatch):
    network = json.loads((ROOT / 'shared/service_network.json').read_text(encoding='utf-8'))
    query = Query('campus', 'upsquare', departure=765, max_walk=5000, max_transfers=2, samples=20,
        origin_point={'name':'campus', 'lat':35.5426092, 'lon':129.2540322},
        destination_point={'name':'upsquare', 'lat':35.5412587, 'lon':129.3388543})
    optimized = Engine(network).search(query)
    monkeypatch.setattr(engine_module, 'latest_departures', lambda *args: None)
    reference = Engine(network).search(query)
    assert len(optimized) == 20
    assert optimized == reference


def test_service_day_has_distinct_schedules_and_no_cross_day_cache():
    route = {'id': 'bus', 'stops': ['o', 'd'], 'offsets': [0, 10], 'departures': [600, 620],
             'departuresByDay': {'weekday': [600, 620], 'saturday': [650], 'holiday': []}, 'delaySamples': [0]}
    network = {'dataset': 'service', 'source': 'official_timetable', 'timetableDays': ['weekday', 'saturday', 'holiday'],
               'stops': [{'id': 'o'}, {'id': 'd'}], 'routes': [route], 'footpaths': []}
    engine = Engine(network)
    assert engine.search(Query('o', 'd', departure=610, samples=20))[0]['arrival'] == 630
    assert engine.search(Query('o', 'd', departure=610, samples=20, service_day='saturday'))[0]['arrival'] == 660
    assert engine.search(Query('o', 'd', departure=610, samples=20, service_day='holiday')) == []
    assert engine.search(Query('o', 'd', departure=610, samples=20))[0]['arrival'] == 630


def test_official_data_connects_the_1007_upsquare_case_and_retains_public_bus_names():
    network = json.loads((ROOT / 'shared/service_network.json').read_text(encoding='utf-8'))
    engine = Engine(network)
    origin = engine.stops[network['defaultOrigin']]
    destination = {'name': '업스퀘어', 'lat': 35.5412587, 'lon': 129.3388543}
    response = TestClient(app).post('/v1/journeys/search', json={
        'dataset': 'service', 'origin': 'location', 'destination': 'upsquare',
        'origin_point': origin, 'destination_point': destination,
        'departure': 607, 'max_transfers': 1, 'max_walk': 500, 'samples': 20,
    })
    assert response.status_code == 200
    rows = response.json()['journeys']
    assert rows and all(row['arrival'] >= 607 for row in rows)
    assert all(row['walkingMeters'] <= 500 and row['transfers'] <= 1 for row in rows)
    assert any('ANY%' in row['tags'] for row in rows)
    assert {'북구08', '울주87', '남구52'} <= {route['number'] for route in network['routes']}
    assert '6408' not in {route['number'] for route in network['routes']}
    assert all(route['id'].startswith(('its:','shared:yangsan:')) for route in network['routes'])


def test_compact_network_and_selected_geometry_preserve_the_1245_campus_routes():
    client = TestClient(app)
    compact_response = client.get('/v1/network?dataset=service&compact=true')
    compact = compact_response.json()
    full = client.get('/v1/network?dataset=service').json()
    assert compact['compact'] and 'shapes' not in compact
    assert len(compact_response.content) < len(json.dumps(full).encode()) / 4
    assert all('shapeSegments' not in route for route in compact['routes'])
    for lat, lon in [(35.4972505, 129.4158209), (35.5426092, 129.2540322)]:
        response = client.post('/v1/journeys/search', json={
            'dataset': 'service', 'origin': 'campus', 'destination': 'upsquare',
            'origin_point': {'name': 'campus', 'lat': lat, 'lon': lon},
            'destination_point': {'name': 'upsquare', 'lat': 35.5412587, 'lon': 129.3388543},
            'departure': 765, 'max_walk': 1000, 'max_transfers': 1, 'samples': 20,
            'include_geometry': True,
        })
        assert response.status_code == 200
        result = response.json()
        assert result['journeys']
        assert all(row['walkingMeters'] <= 1000 and row['transfers'] <= 1 for row in result['journeys'])
        geometry = result['geometry']
        for row in result['journeys']:
            for leg in row['legs']:
                if leg['kind'] == 'ride':
                    shape_ids = geometry['routes'][leg['routeId']]['shapeSegments'][leg['boardIndex']:leg['alightIndex']]
                    assert all(key in geometry['shapes'] for key in shape_ids)
