"""Build a planning snapshot from official route geometry and terminal timetables."""
import bisect
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.walking import default_graph, distance
from local_roads import RoadGraph, compact, length

DAY_TYPES = ('weekday', 'saturday', 'holiday')
MOVING_KMH = 22
STOP_SECONDS = 20


def point_distance(a, b):
    return math.hypot((a[0] - b[0]) * 111000, (a[1] - b[1]) * 91000)


def project_stops(points, stops):
    grid = defaultdict(set)
    lengths = [0.0]
    for index, p in enumerate(points):
        grid[(math.floor(p[0] * 1110), math.floor(p[1] * 910))].add(index)
        if index:
            lengths.append(lengths[-1] + point_distance(points[index - 1], p))
    progress = []
    previous = 0.0
    for stop_index, stop in enumerate(stops):
        p = stop['lat'], stop['lon']
        y, x = math.floor(p[0] * 1110), math.floor(p[1] * 910)
        candidates = set()
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                for node in grid.get((y + dy, x + dx), ()):
                    candidates.update((node - 1, node))
        if not candidates:
            candidates = range(max(0, bisect.bisect_left(lengths, previous) - 1), len(points) - 1)
        matches = []
        for index in candidates:
            if index < 0 or index >= len(points) - 1 or lengths[index + 1] < previous - .1:
                continue
            a, b = points[index], points[index + 1]
            dx, dy = (b[1] - a[1]) * 91000, (b[0] - a[0]) * 111000
            denominator = dx * dx + dy * dy
            if denominator == 0:
                continue
            fraction = ((p[1] - a[1]) * 91000 * dx + (p[0] - a[0]) * 111000 * dy) / denominator
            fraction = min(1, max(0, fraction))
            position = lengths[index] + fraction * math.sqrt(denominator)
            if position < previous - .1:
                continue
            snapped = (a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction)
            error = point_distance(p, snapped)
            matches.append((error, position))
        if matches:
            if stop_index == 0:
                tolerance = min(m[0] for m in matches) + 25
                chosen = min((m for m in matches if m[0] <= tolerance), key=lambda m: m[1])
            else:
                prior = stops[stop_index - 1]
                gap = point_distance(p, (prior['lat'], prior['lon']))
                nearby = [m for m in matches if m[1] - previous <= max(2000, gap * 5 + 300)]
                options = nearby or matches
                tolerance = min(m[0] for m in options) + 3
                chosen = min((m for m in options if m[0] <= tolerance), key=lambda m: m[1])
            previous = max(previous, chosen[1])
        progress.append(previous)
    return lengths, progress


def point_at(points, lengths, meters):
    index = max(0, min(len(points) - 2, bisect.bisect_right(lengths, meters) - 1))
    size = lengths[index + 1] - lengths[index]
    fraction = (meters - lengths[index]) / size if size else 0
    return [round(points[index][axis] + (points[index + 1][axis] - points[index][axis]) * fraction, 7) for axis in (0, 1)]


def clip(points, lengths, start, end):
    first, last = bisect.bisect_right(lengths, start), bisect.bisect_left(lengths, end)
    return [point_at(points, lengths, start), *points[first:last], point_at(points, lengths, end)]


def main():
    folder = ROOT / 'tmp/official-bus'
    metadata = json.loads((folder / 'routes.json').read_text(encoding='utf-8'))
    sources = []
    stops, routes, shapes = {}, [], {}
    omitted, excluded, skipped_times = [], [], []
    roads = RoadGraph(json.loads((ROOT / 'tmp/ulsan-all-roads.json').read_text(encoding='utf-8')))
    road_connections = {}

    def connect_sparse_line(line):
        connected = []
        repaired = False
        for a, b in zip(line, line[1:]):
            if not connected:
                connected.append(a)
            if point_distance(a, b) > 300:
                key = tuple(a), tuple(b)
                if key not in road_connections:
                    try:
                        road, error = roads.route(a, b, limit=max(2000, point_distance(a, b) * 3))
                        road_connections[key] = road if error <= 40 and length(road) <= point_distance(a, b) * 1.5 + 100 else None
                    except ValueError:
                        road_connections[key] = None
                road = road_connections[key]
                if road:
                    connected.extend(road)
                    repaired = True
            connected.append(b)
        return compact(connected) if connected else [], repaired
    for meta in metadata:
        identity = str(meta['brtid'])
        path = folder / f'{identity}.json'
        if not path.exists():
            raise RuntimeError(f'Official route {identity} has not been fetched')
        raw = path.read_bytes()
        source = json.loads(raw)
        sources.append({'routeId': identity, 'sha256': hashlib.sha256(raw).hexdigest(), 'retrievedAt': source['retrievedAt']})
        if meta['brttype'] == '40':
            excluded.append({'routeId': identity, 'number': meta['brtno'], 'reason': 'Tour service requires a separate operating-date calendar'})
            continue
        sequence = []
        for stop in sorted(source['stops'], key=lambda s: s['brsseqno']):
            sid = str(stop['stopid'])
            if sequence and sequence[-1] == sid:
                continue
            lat, lon = float(stop['stopy2']), float(stop['stopx2'])
            if not (33 < lat < 39 and 124 < lon < 132):
                continue
            stops[sid] = {'id': sid, 'name': stop['stopname'], 'lat': lat, 'lon': lon,
                          'publicId': str(stop.get('stopserviceid', sid)),
                          'direction': f"정류소 {stop.get('stopserviceid', sid)}", 'source': 'ulsan_its'}
            sequence.append(sid)
        if len(sequence) < 2:
            omitted.append(identity)
            continue
        times = {}
        for day in DAY_TYPES:
            values = []
            for row in source['times'][day]:
                text = str(row.get('bttStarttime', ''))
                if str(row.get('brtId')) != identity or not re.fullmatch(r'\d{4}', text):
                    skipped_times.append({'routeId': identity, 'day': day, 'value': text})
                    continue
                hour, minute = int(text[:2]), int(text[2:])
                if hour < 30 and minute < 60:
                    values.append(hour * 60 + minute)
            times[day] = sorted(set(values))
        points = []
        for p in source['shape']:
            value = [float(p['y2']), float(p['x2'])]
            if not points or points[-1] != value:
                points.append(value)
        valid_shape = len(points) > 1
        lengths, progress = project_stops(points, [stops[s] for s in sequence]) if valid_shape else ([], [])
        offsets, distances, segments = [0.0], [0.0], []
        for index, (a, b) in enumerate(zip(sequence, sequence[1:])):
            key = f'its:{identity}:{index}'
            meters = progress[index + 1] - progress[index] if valid_shape else 0
            line = clip(points, lengths, progress[index], progress[index + 1]) if valid_shape and meters > 1 else []
            repaired = False
            if line:
                line, repaired = connect_sparse_line(line)
                meters = length(line)
            if not line:
                line = []
                meters = point_distance((stops[a]['lat'], stops[a]['lon']), (stops[b]['lat'], stops[b]['lon'])) * 1.3
            shapes[key] = {'points': line, 'meters': round(meters, 1), 'source': 'ulsan_its_osm_connected' if repaired else 'ulsan_its' if line else 'unavailable'}
            segments.append(key)
            distances.append(round(distances[-1] + meters, 1))
            offsets.append(round(offsets[-1] + meters / (MOVING_KMH * 1000 / 60) + STOP_SECONDS / 60, 4))
        available = any(times.values())
        public_number = str(meta.get('searchBrtNo') or meta['brtname'].split('(')[0]).strip()
        routes.append({'id': 'its:' + identity, 'familyId': identity, 'number': public_number, 'numberKnown': True,
                       'name': f"{meta['stopstname']} → {meta['stopedname']}", 'stops': sequence,
                       'offsets': offsets, 'distanceOffsets': distances, 'departures': times['weekday'], 'departuresByDay': times,
                       'scheduleSource': 'official_terminal_estimated_stops' if available else 'catalog_topology',
                       'stopTimeSource': 'distance_speed_model', 'shapeSegments': segments,
                       'color': ['#7CB8FF', '#CEF75F', '#C5A2FF', '#61D4BE', '#F6AA78'][len(routes) % 5],
                       'delaySamples': [0, 0, 1, 1, 2, 2, 3, 4, 5, 7], 'delaySource': 'simulated'})
    used = {sid for r in routes for sid in r['stops']}
    stops = {sid: s for sid, s in stops.items() if sid in used}
    graph = default_graph()
    grid = defaultdict(list)
    for s in stops.values():
        grid[(math.floor(s['lat'] * 444), math.floor(s['lon'] * 364))].append(s)
    paths = []
    for index, stop in enumerate(stops.values()):
        y, x = math.floor(stop['lat'] * 444), math.floor(stop['lon'] * 364)
        neighbors = [s for dy in (-1, 0, 1) for dx in (-1, 0, 1) for s in grid.get((y + dy, x + dx), ()) if s['id'] != stop['id']]
        point = stop['lat'], stop['lon']
        nearby = [s for s in neighbors if distance(point, (s['lat'], s['lon'])) <= 250]
        if nearby:
            for sid, meters, line in graph.connections(point, nearby, 250):
                key = f"itswalk:{stop['id']}:{sid}"
                shapes[key] = {'points': line, 'meters': meters, 'source': 'osm_pedestrian_access'}
                paths.append({'from': stop['id'], 'to': sid, 'meters': meters, 'shape': key})
        if index % 500 == 0:
            print('Walking transfers', index, '/', len(stops), flush=True)
    def default_stop(name, point):
        matches = [s for s in stops.values() if name in s['name'] and point_distance(point, (s['lat'], s['lon'])) < 500]
        return min(matches or stops.values(), key=lambda s: point_distance(point, (s['lat'], s['lon'])))['id']
    stamp = datetime.now(timezone.utc).date().isoformat()
    network = {'version': 'ulsan-its-' + stamp + '+shape2', 'dataset': 'service', 'source': 'official_timetable',
               'description': '울산교통관리센터 공식 노선·기점 시간표입니다. 중간 정류장 시각은 도로 거리와 속도로 추정하며 지연은 가상 표본입니다.',
               'defaultOrigin': default_stop('울산과학', (35.499699, 129.417175)),
               'defaultDestination': default_stop('성남동', (35.55302, 129.31955)), 'defaultDeparture': 540,
               'routeFamilies': len(routes), 'routeNumbers': len({r['number'] for r in routes}),
               'catalogFallback': True, 'stops': list(stops.values()), 'routes': routes, 'footpaths': paths, 'shapes': shapes,
               'geometryVersion': 'ulsan-its-2', 'geometryAttribution': '울산교통관리센터 / © OpenStreetMap contributors',
               'timetableDays': list(DAY_TYPES), 'retrievedDate': stamp,
               'estimation': {'movingKmh': MOVING_KMH, 'dwellSecondsPerStop': STOP_SECONDS},
               'sourceUrl': 'https://its.ulsan.kr/route/timetable.do'}
    supplements = ROOT/'shared/service_supplements.json'
    (ROOT/'tmp/service-network-original.json').write_text(json.dumps(network,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    if supplements.exists():
        from service_supplements import apply_supplements
        apply_supplements(network,json.loads(supplements.read_text(encoding='utf-8')))
        routes = network['routes']
    encoded = json.dumps(network, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    for destination in (ROOT / 'shared/service_network.json', ROOT / 'app/assets/data/service_network.json'):
        destination.write_bytes(encoded)
    report = {'sourceUrl': network['sourceUrl'], 'retrievedDate': stamp, 'routes': len(routes),
              'officialRouteCount': len(routes)-len([r for r in routes if r.get('serviceGrouping')]),
              'supplementalServiceGroups': len([r for r in routes if r.get('serviceGrouping')]),
              'derivedNetworkVersion': network['version'],
              'supplementalSources': network.get('supplementalSources',{}),
              'busNumbers': network['routeNumbers'], 'stops': len(stops), 'footpaths': len(paths),
              'departuresByDay': {day: sum(len(r['departuresByDay'][day]) for r in routes) for day in DAY_TYPES},
              'routesMissingAllTimetables': [r['familyId'] for r in routes if r['scheduleSource'] == 'catalog_topology'],
              'omittedRoutesWithoutTwoStops': omitted, 'excludedSpecialCalendarRoutes': excluded,
              'skippedTimeValues': skipped_times, 'sha256': hashlib.sha256(encoded).hexdigest(),
              'estimatedStopTimes': network['estimation'], 'files': sources}
    (ROOT / 'artifacts/official-data.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('files', 'skippedTimeValues')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
