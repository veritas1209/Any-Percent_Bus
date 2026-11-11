import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.engine import Engine, Query
from app.main import app
from app.service_calendar import departures_for

ROOT=Path(__file__).resolve().parents[2]


def test_market_route_is_not_offered_on_an_ordinary_day_or_without_a_date():
    network={'hasServiceCalendars':True,'timetableDays':['weekday','saturday','holiday'],
        'stops':[{'id':'o'},{'id':'d'}],'footpaths':[],
        'routes':[{'id':'market','stops':['o','d'],'offsets':[0,10],'departures':[420],
            'departuresByDay':{'weekday':[420],'saturday':[420],'holiday':[420]},
            'serviceCalendar':{'onlyMonthDays':[3,8,13,18,23,28]},'delaySamples':[0]}]}
    engine=Engine(network)
    query=dict(departure=400,max_transfers=0,samples=20)
    assert engine.search(Query('o','d',**query))==[]
    assert engine.search(Query('o','d',service_date='2026-11-11',**query))==[]
    assert engine.search(Query('o','d',service_date='2026-11-13',**query))[0]['arrival']==430
    assert engine.search(Query('o','d',service_date='2026-11-11',**query))==[]


def test_joint_service_expires_and_never_boards_a_nonshared_stop():
    route={'id':'joint','stops':['outside','o','d'],'offsets':[0,10,20],'departures':[420],
        'departuresByDay':{'weekday':[420]},'passengerStops':['o','d'],
        'serviceCalendar':{'startDate':'2026-10-06','endDate':'2026-11-22'},'delaySamples':[0]}
    network={'hasServiceCalendars':True,'timetableDays':['weekday'],'stops':[{'id':s} for s in route['stops']],
        'routes':[route],'footpaths':[]}
    engine=Engine(network)
    assert engine.search(Query('o','d',departure=400,service_date='2026-11-11',samples=20))[0]['arrival']==440
    assert engine.search(Query('outside','d',departure=400,service_date='2026-11-11',samples=20))==[]
    assert engine.search(Query('o','d',departure=400,service_date='2026-11-23',samples=20))==[]
    assert engine.search(Query('o','d',departure=400,samples=20))==[]


def test_sourced_schedules_and_road_repairs_are_complete():
    network=json.loads((ROOT/'shared/service_network.json').read_text(encoding='utf-8'))
    routes={r['id']:r for r in network['routes']}
    assert all(len(network['shapes'][key]['points'])>=2 for r in routes.values() for key in r['shapeSegments'])
    assert [len(routes['its:193000059']['departuresByDay'][day]) for day in ('weekday','saturday','holiday')]==[32,18,18]
    assert departures_for(routes['its:196000764'],'weekday','2026-11-13')==[420,550,680,890,1020]
    assert departures_for(routes['its:196000764'],'weekday','2026-11-11')==[]
    assert departures_for(routes['its:196000760'],'weekday','2026-11-12')==[1050]
    assert departures_for(routes['its:196000762'],'saturday','2026-11-14')==[420,540,660,890,1020]
    assert departures_for(routes['its:196000762'],'saturday','2026-11-21')==[540,660,1020]
    for route in routes.values():
        if route['id'].startswith('shared:yangsan:'):
            assert route['number']=='2100·2300'
            assert route['passengerStops'] and all(s.startswith('19') for s in route['passengerStops'])


def test_api_rejects_an_impossible_calendar_date():
    response=TestClient(app).post('/v1/journeys/search',json={'origin':'o','destination':'d','service_date':'2026-02-30'})
    assert response.status_code==422


def test_same_trip_pruning_keeps_near_boarding_and_an_earlier_alighting_stop():
    network={'stops':[{'id':s} for s in ('o','a','x','b','d')],'footpaths':[
        {'from':'o','to':'b','meters':0},{'from':'o','to':'a','meters':80}],
        'routes':[{'id':'bus','stops':['a','x','b','d'],'offsets':[0,2,4,10],
                   'departures':[15],'delaySamples':[0]}]}
    engine=Engine(network)
    def search(destination):
        return engine.search(Query('o',destination,departure=0,max_walk=None,walking_penalty=1,max_transfers=0,samples=20))
    assert search('d')[0]['legs'][-1]['from']=='b'
    assert search('x')[0]['legs'][-1]['from']=='a'
    assert search('x')[0]['arrival']==17
