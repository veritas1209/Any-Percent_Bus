"""Download the public Ulsan ITS route screen's data, with a resumable local cache."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://its.ulsan.kr'
DAY_CODES = {'weekday': 0, 'saturday': 7, 'holiday': 1}


def decode_response(response):
    response.raise_for_status()
    try:
        value = json.loads(response.content)
    except UnicodeDecodeError:
        value = json.loads(response.content.decode('cp949'))
    if str(value.get('resultCode')) != '200':
        raise RuntimeError(f"ITS returned {value.get('resultCode')}")
    return value


def queries(route):
    identity = route['brtid']
    result = [{
        'postData': {'serviceName': 'routeStationService', 'methodName': 'getGridList', 'paging': False},
        'record': {'routeId': identity},
        'sorting': [{'column': 'pntSqno', 'order': 'asc'}],
    }, {
        'postData': {'serviceName': 'routeLinkService', 'methodName': 'getGridList', 'sorting': False},
        'record': {'routeId': identity},
    }]
    for code in DAY_CODES.values():
        result.append({'postData': {
            'serviceName': 'routeBusService', 'methodName': 'getBusTimeInfo',
            'brtNo': route['brtno'], 'brtId': identity,
            'brtClass': route['brtclass'], 'bttDirection': route['brtdirection'], 'dywkVal': code,
        }})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int)
    parser.add_argument('--batch-size', type=int, default=6)
    args = parser.parse_args()
    folder = ROOT / 'tmp/official-bus'
    folder.mkdir(parents=True, exist_ok=True)
    headers = {'Referer': BASE + '/route/route.do', 'User-Agent': 'AnyPercent university transit prototype'}
    with httpx.Client(timeout=45, headers=headers) as client:
        response = client.post(BASE + '/mpng/getList.json', json={
            'postData': {'serviceName': 'routeService', 'methodName': 'getGridList', 'paging': False},
            'record': {'routeNm': [{'value': ''}]},
            'sorting': [{'column': 'routeNm', 'order': 'asc'}],
        })
        routes = decode_response(response)['rows']
        (folder / 'routes.json').write_text(json.dumps(routes, ensure_ascii=False), encoding='utf-8')
        if args.limit:
            routes = routes[:args.limit]
        pending = [r for r in routes if not (folder / f"{r['brtid']}.json").exists()]
        print(f'Public routes {len(routes)}, uncached {len(pending)}', flush=True)
        for start in range(0, len(pending), args.batch_size):
            batch = pending[start:start + args.batch_size]
            payload = [q for route in batch for q in queries(route)]
            response = client.post(BASE + '/mpng/getMultiList.json', json=payload)
            lists = decode_response(response)['list']
            if len(lists) != len(payload):
                raise RuntimeError('ITS batch response does not match the requested routes')
            for index, route in enumerate(batch):
                rows = lists[index * 5:index * 5 + 5]
                # Keep the static transport data needed for planning.
                stops = [{k: s[k] for k in ('stopid', 'stopname', 'stopx2', 'stopy2', 'stopserviceid', 'brsseqno') if k in s}
                         for s in rows[0]]
                shapes = [{k: p[k] for k in ('x2', 'y2', 'breSeqno') if k in p} for p in rows[1]]
                value = {'meta': route, 'stops': stops, 'shape': shapes,
                         'times': {day: [{k: t[k] for k in ('seq', 'brtId', 'bttStarttime', 'flag') if k in t}
                                         for t in rows[i + 2]] for i, day in enumerate(DAY_CODES)},
                         'retrievedAt': datetime.now(timezone.utc).isoformat(),
                         'source': BASE + '/route/timetable.do'}
                path = folder / f"{route['brtid']}.json"
                temporary = path.with_suffix('.tmp')
                temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
                temporary.replace(path)
            print(f'Retrieved {min(start + len(batch), len(pending))}/{len(pending)}', flush=True)
            time.sleep(.25)


if __name__ == '__main__':
    main()
