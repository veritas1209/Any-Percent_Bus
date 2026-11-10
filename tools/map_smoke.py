"""Verify one initial real map viewport. Interactive camera tests use memory tiles in Flutter tests."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]


async def run():
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
        page=await browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
        errors=[];tiles=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('response',lambda r:tiles.append({'url':r.url,'status':r.status}) if r.url.startswith('https://tile.openstreetmap.org/') else None)
        await page.goto('http://127.0.0.1:8080',wait_until='networkidle')
        await page.locator('flt-semantics-placeholder').dispatch_event('click')
        await page.get_by_role('button',name='나의 경로 만들기',exact=True).click()
        await page.get_by_role('button',name='경로 비교하기',exact=True).click(force=True)
        await page.get_by_role('button',name='ANY% 경로 상세 보기',exact=False).first.click()
        await page.get_by_text('© OpenStreetMap contributors',exact=False).wait_for()
        await page.wait_for_timeout(3500)
        snapshot=await page.locator('body').aria_snapshot()
        assert tiles and all(t['status']==200 for t in tiles),tiles
        assert '지도 연결을 확인해주세요.' not in snapshot
        assert '정류장 정보:' in snapshot
        assert all(number in snapshot for number in ('124번','722번','772번'))
        assert '기록시각 기준 버스 위치' in snapshot
        assert not errors,errors
        await page.screenshot(path=str(ROOT/'artifacts/screenshots/13-street-map-mobile.png'))
        await browser.close()
        result={'passed':['real map tiles loaded in one initial viewport','visible OpenStreetMap attribution','selected route stop markers','BusTracker bus numbers on map legend and vehicle'],'tileResponses':len(tiles),'statuses':sorted(set(t['status'] for t in tiles)),'errors':errors,
                'note':'No automated live-tile panning/zooming, offline downloads or tile archive. Camera interaction tests use in-memory tiles.'}
        (ROOT/'artifacts/map-acceptance.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))


if __name__=='__main__':asyncio.run(run())
