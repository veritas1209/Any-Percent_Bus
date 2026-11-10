"""Browser check for the partial GPS section and same-number variant navigation."""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]


async def run():
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True,args=['--disable-gpu'])
        page=await browser.new_page(viewport={'width':390,'height':844})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        await page.route('https://**/*',lambda r:r.abort())
        async def home():
            await page.goto('http://127.0.0.1:8080',wait_until='networkidle')
            await page.locator('flt-semantics-placeholder').dispatch_event('click')
        await home()
        for label,sid,name in [('출발','ref:31531','남창고등학교'),('도착','ref:31532','남창역(기점)')]:
            await page.get_by_role('button',name=label+' 지점 선택',exact=False).click()
            await page.get_by_role('textbox').fill(sid)
            await page.wait_for_timeout(500)
            await page.get_by_role('button',name=name,exact=False).first.click()
            await page.wait_for_timeout(500)
        await page.get_by_role('button',name='나의 경로 만들기',exact=True).click()
        slider=page.get_by_role('slider').first
        await slider.scroll_into_view_if_needed()
        box=await slider.bounding_box()
        await page.mouse.click(box['x']+2,box['y']+box['height']/2)
        await slider.focus()
        for _ in range(20):await page.keyboard.press('ArrowLeft')
        assert '0m' in await page.locator('body').aria_snapshot()
        await page.mouse.move(180,400)
        await page.mouse.wheel(0,500)
        await page.wait_for_timeout(500)
        direct=page.get_by_role('button',name='직행만',exact=True)
        await direct.click(force=True)
        await page.wait_for_timeout(300)
        assert await direct.get_attribute('aria-current')=='true'
        await page.get_by_role('button',name='경로 비교하기',exact=True).click(force=True)
        try:
            await page.get_by_role('button',name='ROUTE 경로 상세 보기',exact=False).first.wait_for(timeout=30000)
        except Exception:
            print(await page.locator('body').aria_snapshot(),flush=True)
            print(errors,flush=True)
            raise
        result=await page.locator('body').aria_snapshot()
        assert '운행시각 미확인' in result and '울주81번 · GPS추정' in result
        assert '도착 예정' not in result and '환승 성공 추정' not in result
        await page.get_by_role('button',name='ROUTE 경로 상세 보기',exact=False).first.click()
        await page.wait_for_timeout(600)
        detail=await page.locator('body').aria_snapshot()
        assert 'GPS 근접 추정 구간' in detail and '운행시각이 없는 경로입니다' in detail
        await page.screenshot(path=str(ROOT/'artifacts/screenshots/15-recovered-81-mobile.png'))
        await home()
        await page.get_by_role('button',name='출발 지점 선택',exact=False).click()
        await page.get_by_role('button',name='노선',exact=True).click()
        await page.get_by_role('textbox').fill('북구13')
        await page.wait_for_timeout(600)
        await page.get_by_role('button',name='북구13번',exact=False).first.click()
        await page.get_by_role('button',name='북구13번 · 다른 구간 보기',exact=True).click()
        await page.wait_for_timeout(400)
        alternate=await page.locator('body').aria_snapshot()
        assert '정류장 ID' in alternate and '다른 구간 보기' not in alternate
        await page.screenshot(path=str(ROOT/'artifacts/screenshots/16-related-variant-mobile.png'))
        await browser.close()
        assert not errors,errors
        report={'passed':['recovered 81 can be searched with direct-only and zero walking','partial GPS source is explicit','no invented arrival or probability','sparse variant opens a real same-number section'],'errors':errors}
        (ROOT/'artifacts/recovery-acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))


if __name__=='__main__':asyncio.run(run())
