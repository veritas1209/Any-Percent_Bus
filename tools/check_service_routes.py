"""Check geographically varied journeys against the deployed service and source schedules."""
import argparse
import bisect
import json
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.service_calendar import departures_for
CASES = [
    ('taehwa-university', '태화강역 → 울산대학교', '193012313', '193030707', 0),
    ('ktx-university', '울산역 → 울산대학교', '196015414', '193030707', 0),
    ('airport-taehwa', '울산공항 → 태화강역', '195040328', '193012313', 0),
    ('eonyang-ktx', '언양터미널 → 울산역', '196030401', '196015414', 0),
    ('ilsan-taehwa', '일산해수욕장 → 태화강역', '194024234', '193012313', 0),
    ('cityhall-airport', '시청앞 → 울산공항', '193031109', '195040328', 0),
    ('hospital-airport', '울산대병원 → 울산공항', '194060201', '195040328', 2),
    ('namchang-unist', '남창역 → UNIST', '196031532', '196040232', 2),
    ('kkotbawi-eonyang', '꽃바위 → 언양터미널', '194019014', '196030401', 2),
    ('hospital-namchang', '울산대병원 → 남창역', '194060201', '196031532', 2),
]


def check_case(client, url, network, case, departure, day,service_date_override=None):
    key, title, origin, destination, transfers = case
    stops = {s['id']: s for s in network['stops']}
    routes = {r['id']: r for r in network['routes']}
    point = lambda sid: {k: stops[sid][k] for k in ('name', 'lat', 'lon')}
    service_date=service_date_override or {'weekday':'2026-11-11','saturday':'2026-11-14','holiday':'2026-11-15'}[day]
    query = dict(dataset='service', origin=origin, destination=destination,
        origin_point=point(origin), destination_point=point(destination), departure=departure,
        max_walk=None, walking_penalty=1, max_transfers=transfers, samples=300,
        service_day=day,service_date=service_date, include_geometry=True)
    started = time.perf_counter()
    response = client.post(url + '/v1/journeys/search', json=query)
    response.raise_for_status()
    result = response.json()
    elapsed = round((time.perf_counter() - started) * 1000, 1)
    errors, gaps = [], []
    long_walks=[]
    timed = [r for r in result['journeys'] if r.get('arrival') is not None]
    if not timed:
        errors.append('No timed journey during the tested daytime service')
    for row in timed:
        now, current = departure, '@origin'
        ride_count = 0
        for leg in row['legs']:
            if leg['from'] != current or leg['depart'] < now - .001 or leg['arrive'] < leg['depart']:
                errors.append('Disconnected stops or nonmonotone leg times')
            if leg['kind']=='walk' and leg.get('meters',0)>.5:
                shape=leg.get('shape')
                if isinstance(shape,str):shape=result['geometry']['shapes'].get(shape)
                if not shape or len(shape.get('points',[]))<2:errors.append('Missing pedestrian road geometry')
                if ride_count and leg['to']!='@destination' and leg['meters']>250:
                    long_walks.append(dict(fromStop=leg['from'],toStop=leg['to'],meters=leg['meters']))
            if leg['kind'] == 'ride':
                ride_count += 1
                route = routes[leg['routeId']]
                a, b = leg['boardIndex'], leg['alightIndex']
                if not (a < b and route['stops'][a] == leg['from'] and route['stops'][b] == leg['to']):
                    errors.append('Ride disagrees with official stop order')
                if leg['trip'] not in departures_for(route,day,service_date):
                    errors.append('Trip absent from the selected day timetable')
                if abs(leg['depart'] - leg['trip'] - route['offsets'][a]) > .001 or abs(leg['arrive'] - leg['trip'] - route['offsets'][b]) > .001:
                    errors.append('Ride times disagree with source trip and offsets')
                for shape in route['shapeSegments'][a:b]:
                    if len(result['geometry']['shapes'][shape]['points']) < 2:
                        gaps.append(shape)
            now, current = leg['arrive'], leg['to']
        if current != '@destination' or abs(row['arrival'] - now) > .001 or max(0, ride_count - 1) > transfers:
            errors.append('Destination, final time or transfer count mismatch')
    fastest = min(timed, key=lambda row: (row['arrival'], row['walkingMeters'])) if timed else None
    recommended = timed[0] if timed else None
    def describe(row):
        if not row:
            return None
        return dict(arrival=row['arrival'], walkingMeters=row['walkingMeters'], transfers=row['transfers'],
            transferWalkingMeters=[leg['meters'] for leg in row['legs'] if leg['kind']=='walk' and leg['from']!='@origin' and leg['to']!='@destination'],
            buses=[routes[leg['routeId']]['number'] for leg in row['legs'] if leg['kind'] == 'ride'],
            boarding=[stops[leg['from']]['name'] for leg in row['legs'] if leg['kind'] == 'ride'])
    # A separate scan provides a known feasible direct trip without calling the route engine.
    direct = []
    for route in routes.values():
        if 'passengerStops' in route and (origin not in route['passengerStops'] or destination not in route['passengerStops']):
            continue
        for a, sid in enumerate(route['stops']):
            if sid != origin:
                continue
            for b in range(a + 1, len(route['stops'])):
                if route['stops'][b] != destination:
                    continue
                trips = departures_for(route,day,service_date)
                index = bisect.bisect_left(trips, departure - route['offsets'][a] + .5)
                if index < len(trips):
                    direct.append(trips[index] + route['offsets'][b])
    if direct and (not fastest or fastest['arrival'] > min(direct) + .01):
        errors.append('A known feasible direct trip arrives earlier than every returned candidate')
    if transfers and not any(row['transfers'] > 0 for row in timed):
        errors.append('No transfer journey was exercised')
    return dict(case=key, title=title, departure=departure, day=day,serviceDate=service_date,maxTransfers=transfers,
        timedJourneys=len(timed), elapsedMs=elapsed, serverMs=result['elapsedMs'],
        recommended=describe(recommended), fastest=describe(fastest),
        transfersOver250Meters=long_walks,
        missingShapeSegments=sorted(set(gaps)), errors=sorted(set(errors)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='https://hajin-desktop.tailfb939b.ts.net:10000')
    parser.add_argument('--departures', nargs='+', type=int, default=[480, 840, 1080])
    parser.add_argument('--days', nargs='+', default=['weekday'])
    parser.add_argument('--report', default='service-route-matrix.json')
    parser.add_argument('--service-date')
    args = parser.parse_args()
    network = json.loads((ROOT / 'shared/service_network.json').read_text(encoding='utf-8'))
    report = dict(recordedAt=datetime.now(timezone.utc).isoformat(), url=args.url,
        networkVersion=network['version'], location='Public stop coordinates; no user GPS', cases=[])
    with httpx.Client(timeout=120) as client:
        remote = client.get(args.url + '/v1/network', params={'dataset': 'service', 'compact': 'true'})
        remote.raise_for_status()
        assert remote.json()['version'] == network['version']
        for day in args.days:
            for departure in args.departures:
                for case in CASES:
                    row = check_case(client, args.url, network, case, departure, day,args.service_date)
                    report['cases'].append(row)
                    (ROOT / 'artifacts' / args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(json.dumps(row, ensure_ascii=False), flush=True)
    assert all(not row['errors'] for row in report['cases']), 'Inspect the recorded route matrix failures'


if __name__ == '__main__':
    main()
