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
args = parser.parse_args()
URL = args.url.rstrip('/')
HOUR, MINUTE = map(int, args.departure.split(':'))
DEPARTURE = HOUR * 60 + MINUTE


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
        await page.clock.set_fixed_time(datetime(2026, 11, 11, HOUR, MINUTE, tzinfo=timezone(timedelta(hours=9))))
        errors, requests, resource_urls = [], [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: resource_urls.append(request.url))
        page.on('request', lambda request: requests.append(request.post_data_json)
                if request.method == 'POST' and request.url.endswith('/v1/journeys/search') else None)
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
            await page.get_by_role('textbox').fill('업스퀘어')
            await page.get_by_role('button', name='업스퀘어', exact=False).first.wait_for()
            place_elapsed = round((time.perf_counter() - place_started) * 1000, 1)
            await page.get_by_role('button', name='업스퀘어', exact=False).first.click()
            await page.get_by_role('button', name='나의 경로 만들기', exact=True).click()
            await page.get_by_role('button', name=args.departure, exact=True).wait_for()
            await page.get_by_role('button', name='1회', exact=True).dispatch_event('click')
            await expect(page.get_by_role('button', name='1회', exact=True)).to_have_attribute('aria-current', 'true')
            await page.screenshot(path=str(ROOT / 'artifacts/screenshots/24-official-conditions-mobile.png'))
            started = time.perf_counter()
            async with page.expect_response('**/v1/journeys/search') as pending:
                await page.get_by_role('button', name='경로 비교하기', exact=True).click(force=True)
            response = await pending.value
            result = await response.json()
            assert response.status == 200 and result['journeys']
            await page.get_by_role('button', name=re.compile('^ANY%.*경로 상세 보기')).first.wait_for()
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            query = requests[-1]
            assert query['dataset'] == 'service' and query['departure'] == DEPARTURE and query['max_transfers'] == 1, query
            assert query['max_walk'] == 2000 and query['include_geometry'] and result['geometry']['shapes'], query
            assert query['destination_point']['name'] == '업스퀘어', query
            snapshot = await page.locator('body').aria_snapshot()
            assert '추정' not in snapshot and 'A BETTER WAY' not in snapshot
            await page.screenshot(path=str(ROOT / 'artifacts/screenshots/25-official-upsquare-mobile.png'))
            await page.get_by_role('button', name=re.compile('^ANY%.*경로 상세 보기')).first.dispatch_event('click')
            await page.get_by_role('button', name='현재 위치로 이동', exact=True).wait_for()
            await page.screenshot(path=str(ROOT / 'artifacts/screenshots/26-official-route-mobile.png'))
            await page.get_by_role('button', name='뒤로', exact=True).click()
            await page.get_by_role('button', name='뒤로', exact=True).click()
            await page.get_by_role('button', name='토요일', exact=True).dispatch_event('click')
            await expect(page.get_by_role('button', name='토요일', exact=True)).to_have_attribute('aria-current', 'true')
            async with page.expect_response('**/v1/journeys/search') as pending:
                await page.get_by_role('button', name='경로 비교하기', exact=True).click(force=True)
            saturday = await (await pending.value).json()
            assert requests[-1]['service_day'] == 'saturday' and saturday['journeys']
            assert all(row['arrival'] >= DEPARTURE and row['walkingMeters'] <= 2000 and row['transfers'] <= 1
                       for row in saturday['journeys'])
            assert not any('walk_graph.bin' in url for url in resource_urls)
            assert not any('places.json' in url for url in resource_urls)
            assert any('compact=true' in url for url in resource_urls), [url for url in resource_urls if '/v1/' in url]
            await page.set_viewport_size({'width': 1440, 'height': 900})
            await page.screenshot(path=str(ROOT / 'artifacts/screenshots/27-official-results-desktop.png'))
            assert not errors, errors
            report = {'passed': ['official timetable is the default', 'GPS origin and place destination',
                f'{args.departure} departure, 2km walking and one-transfer condition', 'timed journeys to Upsquare',
                'concise result copy', 'route detail and location control', 'Saturday selection uses the matching service day',
                'web search avoids walking-graph and full place-index downloads', 'compact network with selected road shapes'], 'errors': errors,
                'url': URL, 'queryToVisibleResultsMs': elapsed, 'placeSearchToVisibleResultsMs': place_elapsed,
                'simulatedOrigin': {'lat': args.latitude, 'lon': args.longitude}, 'networkVersion': result['networkVersion'],
                'geolocation': 'Simulated Ulsan campus coordinate; no actual user GPS read', 'tiles': 'Memory PNG fixtures only'}
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
