"""Browser acceptance run against locally served Flutter, using real accessibility controls."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/screenshots'
OUT.mkdir(parents=True,exist_ok=True)


async def run():
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True,args=['--disable-gpu'])
        page=await browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1,record_video_dir=str(ROOT/'artifacts/video'),record_video_size={'width':390,'height':844})
        errors=[]
        external=[]
        blocked_tiles=[]
        searches=[]
        page.on('request',lambda r:searches.append(r.post_data_json) if r.method=='POST' and r.url.endswith('/v1/journeys/search') else None)
        async def block_external(route):
            if route.request.url.startswith('https://tile.openstreetmap.org/'):
                blocked_tiles.append(route.request.url)
            else:
                external.append(route.request.url)
            await route.abort()
        await page.route('https://**/*',block_external)
        page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto('http://127.0.0.1:8080',wait_until='networkidle',timeout=60000)
        await page.wait_for_timeout(2500)
        placeholder=page.locator('flt-semantics-placeholder')
        if await placeholder.count():
            await placeholder.dispatch_event('click')
        await page.wait_for_timeout(1000)
        initial=await page.locator('body').aria_snapshot()
        assert 'BusTracker 운행 기록' in initial
        assert '성남동' in initial and '가상 시연' not in initial
        await page.screenshot(path=str(OUT/'01-search-mobile.png'))
        await page.get_by_role('button',name='나의 경로 만들기',exact=True).click()
        await page.wait_for_timeout(700)
        assert '07:10' in await page.locator('body').aria_snapshot()
        await page.screenshot(path=str(OUT/'02-conditions-mobile.png'))
        await page.get_by_role('button',name='경로 비교하기',exact=True).click(force=True)
        await page.get_by_role('button',name='ANY% 경로 상세 보기',exact=False).first.wait_for(timeout=30000)
        results=await page.locator('body').aria_snapshot()
        assert all(number in results for number in ('124번','741번','114번'))
        assert '07:48' in results and '07:52' in results
        assert 'A · 동구 연결' not in results and 'B · 도심 급행' not in results
        await page.screenshot(path=str(OUT/'03-results-mobile.png'))
        await page.get_by_role('button',name='ANY% 경로 상세 보기',exact=False).first.click()
        await page.wait_for_timeout(700)
        details=await page.locator('body').aria_snapshot()
        assert all(number in details for number in ('124번','741번','114번'))
        try:
            await page.get_by_role('button',name='개략도로 보기',exact=True).wait_for(timeout=10000)
        except Exception:
            print('MAP_FAILURE_STATE',json.dumps({'blockedTiles':blocked_tiles,'aria':await page.locator('body').aria_snapshot()},ensure_ascii=False),flush=True)
            await page.screenshot(path=str(OUT/'map-failure-debug.png'))
            raise
        await page.get_by_role('button',name='개략도로 보기',exact=True).click()
        await page.screenshot(path=str(OUT/'04-details-mobile.png'))
        await page.get_by_role('button',name='버스가 늦는다면?',exact=True).click(force=True)
        await page.wait_for_timeout(700)
        slider=page.get_by_role('slider').first
        await slider.focus()
        for _ in range(3):
            await page.keyboard.press('ArrowRight')
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT/'05-simulation-mobile.png'))
        assert '관측 범위 밖입니다.' in await page.locator('body').aria_snapshot()
        await page.reload(wait_until='networkidle')
        await page.locator('flt-semantics-placeholder').dispatch_event('click')
        await page.wait_for_timeout(600)
        await page.get_by_role('button',name='데이터 연결 설정',exact=True).click()
        await page.get_by_role('textbox').fill('http://100.119.23.4:8001')
        await page.get_by_role('button',name='백엔드에 연결',exact=True).click()
        await page.wait_for_timeout(600)
        await page.get_by_role('button',name='나의 경로 만들기',exact=True).click()
        await page.route('**/v1/journeys/search',lambda route:route.abort())
        await page.get_by_role('button',name='경로 비교하기',exact=True).click(force=True)
        await page.get_by_role('button',name='다시 시도',exact=True).wait_for(timeout=30000)
        await page.screenshot(path=str(OUT/'09-api-retry-mobile.png'))
        await page.unroute('**/v1/journeys/search')
        await page.get_by_role('button',name='다시 시도',exact=True).click()
        await page.get_by_role('button',name='ANY% 경로 상세 보기',exact=False).first.wait_for(timeout=30000)
        assert searches and all(q['dataset']=='observed' for q in searches)
        assert '124번' in await page.locator('body').aria_snapshot()
        await page.screenshot(path=str(OUT/'06-api-results-mobile.png'))
        await page.reload(wait_until='networkidle')
        await page.locator('flt-semantics-placeholder').dispatch_event('click')
        await page.wait_for_timeout(600)
        await page.get_by_role('button',name='데이터 연결 설정',exact=True).click()
        await page.get_by_role('textbox').fill('http://127.0.0.1:1')
        await page.get_by_role('button',name='백엔드에 연결',exact=True).click()
        await page.get_by_text('연결할 수 없습니다. 서버 주소와 실행 상태를 확인해주세요.',exact=True).wait_for(timeout=15000)
        await page.screenshot(path=str(OUT/'10-connection-error-mobile.png'))
        await page.get_by_role('button',name='운행 기록을 오프라인으로 사용',exact=True).click()
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(OUT/'07-observed-search-mobile.png'))
        await page.get_by_role('button',name='나의 경로 만들기',exact=True).click()
        await page.get_by_role('button',name='경로 비교하기',exact=True).click(force=True)
        await page.get_by_role('button',name='ANY% 경로 상세 보기',exact=False).first.wait_for(timeout=30000)
        await page.screenshot(path=str(OUT/'08-observed-results-mobile.png'))
        assert '07:48' in await page.locator('body').aria_snapshot()
        await page.get_by_role('button',name='ANY% 경로 상세 보기',exact=False).first.click()
        await page.wait_for_timeout(700)
        await page.get_by_role('button',name='버스가 늦는다면?',exact=True).click(force=True)
        await page.wait_for_timeout(700)
        slider=page.get_by_role('slider').first
        await slider.focus()
        for _ in range(3):await page.keyboard.press('ArrowRight')
        await page.wait_for_timeout(400)
        await page.screenshot(path=str(OUT/'11-observed-range-mobile.png'))
        assert '관측 범위 밖입니다.' in await page.locator('body').aria_snapshot(), await page.locator('body').aria_snapshot()
        await page.reload(wait_until='networkidle')
        await page.locator('flt-semantics-placeholder').dispatch_event('click')
        await page.wait_for_timeout(600)
        await page.get_by_role('button',name='출발 정류장 선택',exact=False).click()
        await page.get_by_role('textbox').fill('화정주공')
        await page.get_by_role('button',name='화정주공아파트앞',exact=False).first.click()
        await page.wait_for_timeout(500)
        async def late_network(route):
            await asyncio.sleep(1)
            await route.fulfill(status=200,content_type='application/json',body=(ROOT/'shared/observed_network.json').read_text(encoding='utf-8'))
        await page.route('**/v1/network*',late_network)
        await page.get_by_role('button',name='데이터 연결 설정',exact=True).click()
        await page.get_by_role('button',name='백엔드에 연결',exact=True).click()
        await page.mouse.click(20,100)
        await page.wait_for_timeout(1700)
        assert '화정주공아파트앞' in await page.locator('body').aria_snapshot()
        await page.screenshot(path=str(OUT/'12-cancel-preserves-input-mobile.png'))
        video=page.video
        await browser.close()
        assert not errors, errors
        assert not external, external
        if video:
            import shutil
            shutil.copyfile(await video.path(),ROOT/'artifacts/AnyPercent-demo.webm')
        assert blocked_tiles, 'Map failure recovery was not exercised'
        result={'passed':['default BusTracker recorded dataset','conditions use 07:10 recording time','Any% vs Safe recorded arrivals','124 / 741 / 114 timeline','no synthetic A / B route cards','Jetson API search uses observed dataset','API retry after interrupted request','invalid backend connection recovery','offline recovery keeps recorded bus numbers','3-minute delay reports unknown subsequent service','cancelled connection preserves selected stops','map failure to diagram fallback'],'errors':errors,'externalRequests':external,'mapTilesBlocked':len(blocked_tiles),'screenshotDirectory':str(OUT)}
        (ROOT/'artifacts/browser-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(run())
