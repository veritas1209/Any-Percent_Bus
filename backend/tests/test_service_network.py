import json
from pathlib import Path

from app.engine import Engine, Query
from app.main import app
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


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
    assert all(route['id'].startswith('its:') for route in network['routes'])
