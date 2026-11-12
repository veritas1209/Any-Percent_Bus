"""Review a small set of public walking directions for stops missing from OSM coverage."""
import asyncio
import hashlib
import json
import math
import sys
import subprocess
import urllib.parse
from datetime import datetime,timezone
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.walking import default_graph,distance


def nearest(graph,point):
    x,y=math.floor(point[1]*910),math.floor(point[0]*1110);edges=set()
    for dx in range(-12,13):
        for dy in range(-12,13):
            i=graph.grid.get((x+dx)*1000000+y+dy)
            if i is not None:edges.update(graph.entries[graph.cells[i+2]:graph.cells[i+2]+graph.cells[i+3]])
    best=None
    for edge in edges:
        a,b=graph.edges[edge*2:edge*2+2];pa,pb=graph.point(a),graph.point(b)
        dx,dy=(pb[1]-pa[1])*91000,(pb[0]-pa[0])*111000
        f=max(0,min(1,((point[1]-pa[1])*91000*dx+(point[0]-pa[0])*111000*dy)/(dx*dx+dy*dy))) if dx or dy else 0
        p=(pa[0]+f*(pb[0]-pa[0]),pa[1]+f*(pb[1]-pa[1]));gap=distance(point,p)
        if best is None or gap<best[0]:best=(gap,p)
    if best is None:raise ValueError('No nearby public pedestrian road')
    return best[1]


async def main():
    target=ROOT/'shared/pedestrian_supplements.json'
    if target.exists():
        print('Reviewed pedestrian supplement already exists; preserving it.',flush=True)
        return
    graph=default_graph()
    network=json.loads((ROOT/'shared/service_network.json').read_text(encoding='utf-8'))
    missing=[s for s in network['stops'] if graph.snap((s['lat'],s['lon'])) is None]
    folder=ROOT/'tmp/foot-gaps';folder.mkdir(exist_ok=True)
    paths=[];sources={}
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
        page=await browser.new_page(viewport={'width':1400,'height':1000})
        try:
            for stop in missing:
                point=stop['lat'],stop['lon'];target=nearest(graph,point)
                cache=folder/(stop['id']+'-walk.json')
                if cache.exists():snapshot=json.loads(cache.read_text(encoding='utf-8'))
                else:
                    url=f'https://map.naver.com/p/directions/{point[1]},{point[0]},'+urllib.parse.quote(stop['name'])+f',0,PLACE_POI/{target[1]},{target[0]},'+urllib.parse.quote('인근 보행로')+',0,PLACE_POI/-/walk'
                    async with page.expect_response(lambda r:'/p/api/directions/walk?' in r.url,timeout=45000) as pending:
                        await page.goto(url,wait_until='domcontentloaded',timeout=60000)
                    response=await pending.value;assert response.status==200
                    snapshot=dict(url=response.url,retrievedAt=datetime.now(timezone.utc).isoformat(),data=await response.json())
                    cache.write_text(json.dumps(snapshot,ensure_ascii=False),encoding='utf-8')
                    await page.wait_for_timeout(1300)
                    await page.screenshot(path=str(folder/(stop['id']+'-walk.png')))
                route=snapshot['data']['routes'][0];points=[]
                for leg in route['legs']:
                    for step in leg['steps']:
                        for value in (step.get('path') or '').split():
                            lon,lat=map(float,value.split(','));pnt=[lat,lon]
                            if not points or points[-1]!=pnt:points.append(pnt)
                assert len(points)>1
                end=graph.snap(tuple(points[-1]));assert end and end['error']<=40
                assert distance(point,points[0])<=80
                sid='naver_walk:'+stop['id']
                sources[sid]=dict(url=snapshot['url'],retrievedAt=snapshot['retrievedAt'],
                    sha256=hashlib.sha256(cache.read_bytes()).hexdigest())
                paths.append(dict(id=sid,stopId=stop['id'],points=points,sourceId=sid,
                    sourceDistanceMeters=route['summary']['distance'],
                    endConnectionErrorMeters=round(end['error'],2)))
                print(json.dumps(dict(stop=stop['name'],id=stop['id'],points=len(points),
                    distance=route['summary']['distance'],joinError=end['error']),ensure_ascii=False),flush=True)
        finally:await browser.close()
    result=dict(version=1,baseGraphCommit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        baseGraphSha256=hashlib.sha256(graph.data).hexdigest(),sources=sources,paths=paths)
    (ROOT/'shared/pedestrian_supplements.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')


if __name__=='__main__':asyncio.run(main())
