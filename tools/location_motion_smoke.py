"""Check place/pin input and playback in Chrome; all map tiles are in-memory fixtures."""
import asyncio
import json
import re
import struct
import zlib
from pathlib import Path

from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
# Memory tile fixture. No production tile requests are sent by this test.
def chunk(kind,data):
    return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
TILE=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',256,256,8,2,0,0,0))+
      chunk(b'IDAT',zlib.compress((b'\0'+bytes((230,235,220))*256)*256))+chunk(b'IEND',b''))


async def run():
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
        page=await browser.new_page(viewport={'width':390,'height':844})
        errors=[];requests=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:requests.append(r.post_data_json) if r.method=='POST' and r.url.endswith('/v1/journeys/search') else None)
        await page.route('https://tile.openstreetmap.org/**',lambda r:r.fulfill(status=200,content_type='image/png',body=TILE))
        async def home():
            await page.goto('http://127.0.0.1:8080',wait_until='networkidle')
            await page.locator('flt-semantics-placeholder').dispatch_event('click')
        await home()
        await page.get_by_role('button',name='출발 지점 선택',exact=False).click()
        await page.get_by_role('textbox').fill('삼산로288')
        await page.get_by_role('button',name=re.compile('삼산로 ?288')).first.click()
        await page.wait_for_timeout(500)
        assert '288' in await page.locator('body').aria_snapshot()
        await page.screenshot(path=str(ROOT/'artifacts/screenshots/17-place-input-mobile.png'))
        await page.get_by_role('button',name='도착 지점 선택',exact=False).click()
        await page.get_by_role('button',name='지도에서 고르기',exact=True).click()
        await page.get_by_role('textbox',name='지점 이름',exact=False).wait_for()
        await page.wait_for_timeout(500)
        # Flutter's generated screen-reader overlay has no map tap action.
        # Send this gesture to the same canvas surface used by normal touch input.
        gesture_style=await page.add_style_tag(content='flt-semantics-host, flt-semantics-host * { pointer-events: none !important; }')
        await page.mouse.click(207,360)
        await page.wait_for_timeout(350)
        await gesture_style.evaluate('e => e.remove()')
        await page.screenshot(path=str(ROOT/'artifacts/screenshots/18-pin-input-mobile.png'))
        await page.get_by_role('button',name='이 지점으로 정하기',exact=True).dispatch_event('click')
        await page.wait_for_timeout(500)
        await page.get_by_role('button',name='나의 경로 만들기',exact=True).wait_for()
        # Send the actual point query to the independently deployed backend.
        await page.get_by_role('button',name='데이터 연결 설정',exact=True).click()
        await page.get_by_role('textbox').fill('http://100.119.23.4:8001')
        await page.get_by_role('button',name='백엔드에 연결',exact=True).click()
        await page.get_by_role('button',name='나의 경로 만들기',exact=True).click()
        async with page.expect_response('**/v1/journeys/search',timeout=30000) as reply:
            await page.get_by_role('button',name='경로 비교하기',exact=True).click(force=True)
        response=await reply.value
        assert response.status==200
        api_result=await response.json()
        assert api_result['journeys'] and api_result['journeys'][0]['places']
        assert requests
        q=requests[-1]
        assert q['origin_point']['name'].replace(' ','').endswith('288'),q
        assert q['destination_point']['name']=='지도에서 선택한 지점',q
        assert q['destination_point']['id']=='picked-map',q
        n=json.loads((ROOT/'shared/observed_network.json').read_text(encoding='utf-8'))
        stop=next(s for s in n['stops'] if s['id']==n['defaultDestination'])
        assert abs(q['destination_point']['lat']-stop['lat'])+abs(q['destination_point']['lon']-stop['lon'])>1e-6
        # Default journey: continuous playback, pause, seek and stop at the end.
        await home()
        await page.get_by_role('button',name='나의 경로 만들기',exact=True).click()
        await page.get_by_role('button',name='경로 비교하기',exact=True).click(force=True)
        await page.get_by_role('button',name='ANY% 경로 상세 보기',exact=False).first.click(timeout=30000)
        await page.get_by_role('button',name='버스가 늦는다면?',exact=True).click(force=True)
        await page.mouse.move(185,450)
        await page.mouse.wheel(0,500)
        await page.wait_for_timeout(500)
        clock=page.get_by_role('slider').last
        async def val():
            snapshot=await page.locator('body').aria_snapshot()
            match=re.search(r'기록 시각 (\d+):(\d+):(\d+)',snapshot)
            assert match,snapshot
            h,m,s=map(int,match.groups())
            return h*60+m+s/60
        initial=await val()
        await page.get_by_role('button',name='버스 재생',exact=True).dispatch_event('click')
        await page.get_by_role('button',name='일시정지',exact=True).wait_for(timeout=2000)
        await page.wait_for_timeout(1200)
        advanced=await val()
        assert .15<advanced-initial<1.5,(initial,advanced)
        await page.get_by_role('button',name='일시정지',exact=True).dispatch_event('click')
        await page.wait_for_timeout(100)
        paused=await val()
        await page.wait_for_timeout(500)
        assert abs(await val()-paused)<.001
        box=await clock.bounding_box()
        gesture_style=await page.add_style_tag(content='flt-semantics-host, flt-semantics-host * { pointer-events: none !important; }')
        # Flutter exposes the thumb's 48px semantics box, not the whole track.
        await page.mouse.click(page.viewport_size['width']-70,box['y']+box['height']/2)
        await page.wait_for_timeout(150)
        await gesture_style.evaluate('e => e.remove()')
        near_end=await val()
        print(json.dumps({'seekBox':box,'nearEnd':near_end}),flush=True)
        assert 454<near_end<460,near_end
        await page.get_by_role('button',name='버스 재생',exact=True).dispatch_event('click')
        await page.get_by_role('button',name='일시정지',exact=True).wait_for(timeout=2000)
        await page.get_by_role('button',name='버스 재생',exact=True).wait_for(timeout=15000)
        ended=await val()
        assert ended>near_end,(near_end,ended)
        await page.wait_for_timeout(1000)
        assert await val()==ended
        await page.screenshot(path=str(ROOT/'artifacts/screenshots/19-playback-ended-mobile.png'))
        await browser.close()
        assert not errors,errors
        result={'passed':['place and road-address selection','arbitrary map pin retains coordinates','point query sent to Jetson API','fractional GPS clock playback','pause retains clock','playback ends without wrapping'],
                'errors':errors,'playbackMinutes':{'initial':initial,'advanced':advanced,'nearEnd':near_end,'ended':ended},
                'tiles':'Only in-memory PNG fixtures; no live map requests',
                'origin':q['origin_point'],'destination':q['destination_point']}
        (ROOT/'artifacts/location-motion-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':asyncio.run(run())
