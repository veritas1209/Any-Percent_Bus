"""GPS UI acceptance with simulated browser positions, never the user's real GPS."""
import argparse,asyncio,json,re,struct,zlib
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--url',default='https://hajin-desktop.tailfb939b.ts.net:9443');args=parser.parse_args()
def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
TILE=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',256,256,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes((230,235,220))*256)*256))+chunk(b'IEND',b'')
GPS={'latitude':35.49971,'longitude':129.41719,'accuracy':15}

async def run():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
  errors=[]
  async def page_for(url=None,**options):
   ctx=await browser.new_context(viewport={'width':390,'height':844},**options)
   page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
   await page.route('https://tile.openstreetmap.org/**',lambda r:r.fulfill(status=200,content_type='image/png',body=TILE))
   await page.add_init_script("window.__gpsReads=0; const read=navigator.geolocation.getCurrentPosition.bind(navigator.geolocation); navigator.geolocation.getCurrentPosition=(...args)=>{window.__gpsReads++;return read(...args);};")
   await page.goto(url or args.url,wait_until='networkidle',timeout=60000)
   await page.locator('flt-semantics-placeholder').dispatch_event('click')
   await page.get_by_role('button',name='현재 위치를 출발지로',exact=True).wait_for()
   return ctx,page
  ctx,page=await page_for(geolocation=GPS,permissions=['geolocation'])
  assert await page.evaluate('window.__gpsReads')==0
  await page.get_by_role('button',name='현재 위치를 출발지로',exact=True).dispatch_event('click')
  await page.get_by_role('button',name=re.compile('출발 지점 선택.*현재 위치')).wait_for()
  assert await page.evaluate('window.__gpsReads')==1
  await page.screenshot(path=str(ROOT/'artifacts/screenshots/20-current-origin-mobile.png'))
  await page.get_by_role('button',name='출발 지점 선택',exact=False).click()
  await page.get_by_role('button',name='지도에서 고르기',exact=True).click()
  await page.get_by_role('button',name='현재 위치로 이동',exact=True).dispatch_event('click')
  await page.wait_for_timeout(400)
  assert await page.evaluate('window.__gpsReads')==2
  assert '현재 위치' in await page.locator('body').aria_snapshot()
  await page.screenshot(path=str(ROOT/'artifacts/screenshots/21-current-location-map-mobile.png'))
  await page.get_by_role('button',name='이 지점으로 정하기',exact=True).dispatch_event('click')
  await page.get_by_role('button',name='데이터 연결 설정',exact=True).click()
  async with page.expect_request('**/v1/network?dataset=observed') as pending_network:
   await page.get_by_role('button',name='백엔드에 연결',exact=True).click()
  api_url=(await pending_network.value).url
  if args.url.startswith('https:'):assert api_url.startswith(args.url.rstrip('/')+'/v1/network'),api_url
  await page.get_by_role('button',name='나의 경로 만들기',exact=True).click()
  async with page.expect_request('**/v1/journeys/search') as pending:
   await page.get_by_role('button',name='경로 비교하기',exact=True).click(force=True)
  query=(await pending.value).post_data_json
  assert query['origin_point']['lat']==GPS['latitude'] and query['origin_point']['lon']==GPS['longitude'],query
  await page.get_by_role('button',name='ANY% 경로 상세 보기',exact=False).first.click(timeout=30000)
  await page.get_by_role('button',name='현재 위치로 이동',exact=True).wait_for()
  await page.screenshot(path=str(ROOT/'artifacts/screenshots/22-current-location-route-mobile.png'))
  await ctx.close()
  # Permission denial is a real browser-denied response with no OS GPS access.
  ctx,page=await page_for()
  await ctx.grant_permissions(['geolocation'])
  await ctx.clear_permissions()
  cdp=await ctx.new_cdp_session(page)
  origin=re.match(r'https?://[^/]+',args.url).group()
  target=(await cdp.send('Target.getTargetInfo'))['targetInfo']
  await cdp.send('Browser.setPermission',{'permission':{'name':'geolocation'},'setting':'denied','origin':origin,'browserContextId':target['browserContextId']})
  await page.get_by_role('button',name='현재 위치를 출발지로',exact=True).dispatch_event('click')
  await page.get_by_text('현재 위치를 확인해주세요',exact=True).wait_for(timeout=5000)
  assert '위치 권한' in await page.locator('body').aria_snapshot()
  await page.screenshot(path=str(ROOT/'artifacts/screenshots/23-location-denied-mobile.png'))
  await page.get_by_role('button',name='확인',exact=True).click()
  await page.get_by_role('button',name=re.compile('출발 지점 선택.*울산과학대학앞')).wait_for()
  await ctx.close()
  ctx,page=await page_for(geolocation={'latitude':37.5,'longitude':127.0,'accuracy':30},permissions=['geolocation'])
  await page.get_by_role('button',name='현재 위치를 출발지로',exact=True).dispatch_event('click')
  await page.get_by_text('현재 위치가 울산 시연 데이터 범위 밖입니다. 울산 안의 출발 지점을 검색하거나 지도에서 골라주세요.',exact=True).wait_for()
  await page.get_by_role('button',name='확인',exact=True).click()
  await page.get_by_role('button',name=re.compile('출발 지점 선택.*울산과학대학앞')).wait_for()
  await ctx.close()
  ctx,page=await page_for(url='http://100.119.23.4:8080')
  await page.get_by_role('button',name='현재 위치를 출발지로',exact=True).dispatch_event('click')
  await page.get_by_role('button',name='HTTPS 앱 열기',exact=True).wait_for()
  assert await page.evaluate('window.__gpsReads')==0
  await ctx.close();await browser.close();assert not errors,errors
  result={'url':args.url,'passed':['GPS not read before a user action','one position read sets origin','map recenter and current-location dot','same-origin HTTPS API configuration','coordinate retained in actual journey request','route map location control','permission denial preserves prior origin','out-of-area location preserves prior origin'],
          'httpRecovery':'Old HTTP URL shows HTTPS launch action without reading GPS',
          'errors':errors,'geolocation':'Simulated browser coordinates in Ulsan; no actual user GPS read','tiles':'Memory PNG fixtures only'}
  (ROOT/'artifacts/current-location-acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':asyncio.run(run())
