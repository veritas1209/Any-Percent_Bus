"""Exercise the official-timetable app through its normal browser entry points."""
import asyncio
import argparse
import json
import re
import struct
import time
import zlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--url', default='https://hajin-desktop.tailfb939b.ts.net:9443')
parser.add_argument('--report', default='browser-acceptance.json')
parser.add_argument('--latitude', type=float, default=35.499699)
parser.add_argument('--longitude', type=float, default=129.417175)
parser.add_argument('--departure', default='10:07')
parser.add_argument('--live-tiles', action='store_true', help='Verify the displayed map using real OSM tiles')
parser.add_argument('--real-clock', action='store_true', help='Use the browser clock; --departure must match the current local minute')
parser.add_argument('--destination',default='업스퀘어')
parser.add_argument('--max-transfers',type=int,choices=(0,1,2),default=1)
parser.add_argument('--require-transfer',action='store_true')
parser.add_argument('--screenshot-prefix',default='')
args = parser.parse_args()
URL = args.url.rstrip('/')
HOUR, MINUTE = map(int, args.departure.split(':'))
DEPARTURE = HOUR * 60 + MINUTE
TRANSFER_LABEL={0:'직행만',1:'1회',2:'2회'}[args.max_transfers]


def shot(name):
    return str(ROOT/'artifacts/screenshots'/(args.screenshot_prefix+name))


def png_chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


TILE = (b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 256, 256, 8, 2, 0, 0, 0)) +
        png_chunk(b'IDAT', zlib.compress((b'\0' + bytes((230, 235, 220)) * 256) * 256)) + png_chunk(b'IEND', b''))


async def run():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
        context = await browser.new_context(viewport={'width': 390, 'height': 844}, timezone_id='Asia/Seoul',
            permissions=['geolocation'], geolocation={'latitude': args.latitude, 'longitude': args.longitude, 'accuracy': 15})
        page = await context.new_page()
        if not args.real_clock:
            await page.clock.set_fixed_time(datetime(2026, 11, 11, HOUR, MINUTE, tzinfo=timezone(timedelta(hours=9))))
        errors, requests, resource_urls, tile_responses = [], [], [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('response', lambda response: tile_responses.append(response.status)
                if response.url.startswith('https://tile.openstreetmap.org/') else None)
        page.on('request', lambda request: resource_urls.append(request.url))
        page.on('request', lambda request: requests.append(request.post_data_json)
                if request.method == 'POST' and request.url.endswith('/v1/journeys/search') else None)
        if not args.live_tiles:
            await page.route('https://tile.openstreetmap.org/**', lambda route: route.fulfill(
                status=200, content_type='image/png', body=TILE))
        try:
            await page.goto(URL, wait_until='domcontentloaded', timeout=60000)
            await page.locator('flt-semantics-placeholder').wait_for(timeout=60000)
            await page.locator('flt-semantics-placeholder').dispatch_event('click')
            await page.get_by_role('button', name='현재 위치를 출발지로', exact=True).wait_for(timeout=90000)
            assert '울산 공식 시간표' in await page.locator('body').aria_snapshot()
            await page.get_by_role('button', name='현재 위치를 출발지로', exact=True).dispatch_event('click')
            await page.get_by_role('button', name=re.compile('출발 지점 선택.*현재 위치')).wait_for()
            await page.get_by_role('button', name='도착 지점 선택', exact=False).click()
            place_started = time.perf_counter()
            await page.get_by_role('textbox').fill(args.destination)
            await page.get_by_role('button', name=args.destination, exact=False).first.wait_for()
            place_elapsed = round((time.perf_counter() - place_started) * 1000, 1)
            await page.get_by_role('button', name=args.destination, exact=False).first.click()
            await page.get_by_role('button', name='나의 경로 만들기', exact=True).click()
            await page.get_by_role('button', name=args.departure, exact=True).wait_for()
            await page.get_by_role('button', name=TRANSFER_LABEL, exact=True).dispatch_event('click')
            await expect(page.get_by_role('button', name=TRANSFER_LABEL, exact=True)).to_have_attribute('aria-current', 'true')
            await page.screenshot(path=shot('24-official-conditions-mobile.png'))
            started = time.perf_counter()
            async with page.expect_response('**/v1/journeys/search') as pending:
                await page.get_by_role('button', name='경로 비교하기', exact=True).click(force=True)
            response = await pending.value
            result = await response.json()
            assert response.status == 200 and result['journeys']
            await page.get_by_role('button', name=re.compile('경로 상세 보기')).first.wait_for()
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            query = requests[-1]
            assert query['dataset'] == 'service' and query['departure'] == DEPARTURE and query['max_transfers'] == args.max_transfers, query
            assert query['max_walk'] is None and query['walking_penalty'] == 1 and query['include_geometry'] and result['geometry']['shapes'], query
            assert '추천' in result['journeys'][0]['tags']
            fastest = next(row for row in result['journeys'] if 'ANY%' in row['tags'])
            if args.latitude == 35.4972505 and DEPARTURE == 855:
                ride = next(leg for leg in fastest['legs'] if leg['kind']=='ride')
                assert ride['from'] == '194027121' and fastest['walkingMeters'] < 700
                assert all(result['geometry']['shapes'][key]['points'] for key in result['geometry']['routes'][ride['routeId']]['shapeSegments'][ride['boardIndex']:ride['alightIndex']])
            assert args.destination in query['destination_point']['name'], query
            assert query.get('service_date')
            if args.require_transfer:
                assert fastest['transfers'] >= 1
            if args.max_transfers == 0:
                assert all(row['transfers'] == 0 for row in result['journeys'])
            snapshot = await page.locator('body').aria_snapshot()
            assert '추정' not in snapshot and 'A BETTER WAY' not in snapshot
            await page.screenshot(path=shot('25-official-upsquare-mobile.png'))
            any_card = page.get_by_role('button', name=re.compile('ANY%.*경로 상세 보기')).first
            # Flutter's ListView exposes only mounted rows in the semantics tree.
            for _ in range(40):
                if await any_card.count() and await any_card.is_visible():break
                await page.mouse.wheel(0, 450)
                await page.wait_for_timeout(200)
            await any_card.dispatch_event('click')
            await page.get_by_role('button', name='현재 위치로 이동', exact=True).wait_for()
            if args.live_tiles:
                # The semantics tree can appear before Flutter mounts its tile layer.
                for _ in range(80):
                    if tile_responses:break
                    await page.wait_for_timeout(250)
                await page.wait_for_load_state('networkidle', timeout=30000)
                # Flutter decodes and paints the images after the HTTP requests finish.
                await page.wait_for_timeout(5000)
                assert tile_responses and all(status == 200 for status in tile_responses), tile_responses
            await page.screenshot(path=shot('26-official-route-mobile.png'))
            if args.live_tiles or args.latitude == 35.4972505:
                await page.set_viewport_size({'width': 1440, 'height': 1100})
                await page.wait_for_load_state('networkidle', timeout=30000)
                if args.live_tiles:
                    await page.wait_for_timeout(5000)
                await page.screenshot(path=shot('28-route-desktop.png'))
                await page.set_viewport_size({'width': 390, 'height': 844})
            await page.get_by_role('button', name='뒤로', exact=True).click()
            await page.get_by_role('button', name='뒤로', exact=True).click()
            await page.get_by_role('checkbox', name='적게 걷기', exact=True).dispatch_event('click')
            await page.get_by_role('button', name='토요일', exact=True).dispatch_event('click')
            await expect(page.get_by_role('button', name='토요일', exact=True)).to_have_attribute('aria-current', 'true')
            async with page.expect_response('**/v1/journeys/search') as pending:
                await page.get_by_role('button', name='경로 비교하기', exact=True).click(force=True)
            saturday = await (await pending.value).json()
            assert requests[-1]['service_day'] == 'saturday' and requests[-1]['walking_penalty'] == 2 and saturday['journeys']
            assert all(row['arrival'] >= DEPARTURE and row['transfers'] <= args.max_transfers
                       for row in saturday['journeys'])
            assert not any('walk_graph.bin' in url for url in resource_urls)
            assert not any('places.json' in url for url in resource_urls)
            assert any('compact=true' in url for url in resource_urls), [url for url in resource_urls if '/v1/' in url]
            await page.set_viewport_size({'width': 1440, 'height': 900})
            await page.screenshot(path=shot('27-official-results-desktop.png'))
            assert not errors, errors
            report = {'passed': ['official timetable is the default', 'GPS origin and place destination',
                f'{args.departure} departure, unlimited walking and at most {args.max_transfers} transfers', f'timed journeys to {args.destination}',
                'concise result copy', 'route detail and location control', 'Saturday selection uses the matching service day',
                'web search avoids walking-graph and full place-index downloads', 'compact network with continuous road shapes', 'walking preference changes the request weight'], 'errors': errors,
                'url': URL, 'queryToVisibleResultsMs': elapsed, 'placeSearchToVisibleResultsMs': place_elapsed,
                'simulatedOrigin': {'lat': args.latitude, 'lon': args.longitude}, 'networkVersion': result['networkVersion'],
                'geolocation': 'Simulated public Ulsan coordinate; no actual user GPS read',
                'timingScope': 'Browser flow latency; request caches may be warm. Uncached server measurements are recorded separately.',
                'clock': 'Real browser clock' if args.real_clock else 'Fixed departure clock',
                'tiles': 'Live OpenStreetMap tiles' if args.live_tiles else 'Memory PNG fixtures only',
                'successfulMapTileResponses': len([status for status in tile_responses if status == 200]),
                'fastestJourney': {'arrival': fastest['arrival'], 'walkingMeters': fastest['walkingMeters'],
                    'rides': [{'routeId': leg['routeId'], 'boardingStop': leg['from'],
                        'alightingStop': leg['to'], 'segmentCount': leg['alightIndex'] - leg['boardIndex'],
                        'segmentsWithPoints': sum(bool(result['geometry']['shapes'][key]['points'])
                            for key in result['geometry']['routes'][leg['routeId']]['shapeSegments'][leg['boardIndex']:leg['alightIndex']])}
                        for leg in fastest['legs'] if leg['kind'] == 'ride']}}
            (ROOT / 'artifacts' / args.report).write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report), flush=True)
        except Exception:
            snapshot = await page.locator('body').aria_snapshot()
            (ROOT / 'tmp/service-smoke-state.txt').write_text(snapshot, encoding='utf-8')
            print(snapshot[:5500], flush=True)
            raise
        finally:
            await browser.close()


if __name__ == '__main__':
    asyncio.run(run())
