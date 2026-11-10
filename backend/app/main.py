from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .engine import Engine, Query
from . import bustracker
from .history import generate_history

ROOT = Path(__file__).resolve().parents[2]
NETWORK = json.loads((ROOT/'shared/network.json').read_text(encoding='utf-8'))
engine = Engine(NETWORK)
OBSERVED = json.loads((ROOT/'shared/observed_network.json').read_text(encoding='utf-8'))
NETWORKS = {'demo': NETWORK, 'observed': OBSERVED}
ENGINES = {'demo': engine, 'observed': Engine(OBSERVED)}
HISTORY=generate_history(NETWORK)
app = FastAPI(title='Any% journey planner', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origin_regex=r'https?://(localhost|127\.0\.0\.1|100\.119\.23\.4)(:\d+)?',allow_methods=['GET','POST'],allow_headers=['Content-Type'])
if os.getenv('BUSTRACKER_CSV'):
    from .replay_feed import create_router
    static_catalog=json.loads((ROOT/'shared/bustracker_catalog.json').read_text(encoding='utf-8'))
    app.include_router(create_router(Path(os.environ['BUSTRACKER_CSV']),static_catalog))


class Search(BaseModel):
    dataset: Literal['demo','observed'] = 'demo'
    origin: str
    destination: str
    departure: float = Field(default=540,ge=0,lt=1440)
    walking_speed: float = Field(default=1.2,ge=.3,le=3)
    max_walk: float = Field(default=500,ge=0,le=2000)
    max_transfers: int = Field(default=2,ge=0,le=2)
    delay: float = Field(default=0,ge=0,le=30)
    samples: int = Field(default=300,ge=20,le=1000)
    seed: int = 42


@app.get('/v1/health')
def health():
    return {'status':'ok','mode':'prototype','networkVersion':NETWORK['version'],'datasets':list(NETWORKS)}


@app.get('/v1/network')
def network(dataset: Literal['demo','observed']='demo'):
    return NETWORKS[dataset]


@app.get('/v1/stops/search')
def search_stops(q: str='',dataset: Literal['demo','observed']='demo'):
    return {'stops':[s for s in NETWORKS[dataset]['stops'] if q.casefold() in (s['name']+s['direction']).casefold()]}


@app.post('/v1/journeys/search')
def journeys(body: Search):
    started=time.perf_counter()
    try:
        rows=ENGINES[body.dataset].search(Query(**body.model_dump(exclude={'dataset'})))
    except ValueError as e:
        raise HTTPException(400,str(e)) from e
    selected=NETWORKS[body.dataset]
    return {'journeys':rows,'source':selected['source'],'delaySource':'simulated','networkVersion':selected['version'],'elapsedMs':round((time.perf_counter()-started)*1000,2),
            'warning':selected['description']+' 지연 확률은 가상 표본의 추정치입니다.'}


@app.get('/v1/vehicles')
def vehicles(minute: float=540,dataset: Literal['demo','observed']='demo'):
    rows=[]
    selected=NETWORKS[dataset]; selected_engine=ENGINES[dataset]
    for r in selected['routes']:
        for trip in r['departures']:
            for i in range(len(r['stops'])-1):
                start,end=trip+r['offsets'][i],trip+r['offsets'][i+1]
                if start<=minute<end:
                    a,b=selected_engine.stops[r['stops'][i]],selected_engine.stops[r['stops'][i+1]]
                    f=(minute-start)/(end-start)
                    rows.append({'vehicleId':r.get('vehicleId',f"{r['id']}:{trip}"),'routeId':r['id'],'lat':a['lat']+(b['lat']-a['lat'])*f,'lon':a['lon']+(b['lon']-a['lon'])*f,'source':selected['source'],'positionMethod':'stop_segment_interpolation','tripId':str(trip)})
    return {'vehicles':rows,'virtualMinute':minute,'source':selected['source'],'positionMethod':'stop_segment_interpolation'}


@app.post('/v1/integration/sync')
async def sync():
    base=os.getenv('BUSTRACKER_URL','').rstrip('/')
    token=os.getenv('BUSTRACKER_INTEGRATION_KEY','')
    if not base:
        raise HTTPException(503,'BUSTRACKER_URL이 설정되지 않았습니다. 로컬 데모를 사용할 수 있습니다.')
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response=await client.get(base+'/integration/v1/network',headers={'X-Integration-Key':token})
            response.raise_for_status()
            snapshot=response.json()
        if not isinstance(snapshot.get('routes'),list) or not isinstance(snapshot.get('stops'),list):
            raise ValueError('노선망 응답 형식 오류')
        # Static catalog is separate: do not invent measured schedules from live ETA.
        with sqlite3.connect(ROOT/'backend/catalog.db') as db:
            db.execute('CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY, observed REAL, payload TEXT)')
            db.execute('INSERT INTO snapshots(observed,payload) VALUES(?,?)',(time.time(),json.dumps(snapshot,ensure_ascii=False)))
        return {'routes':len(snapshot['routes']),'stops':len(snapshot['stops']),'routingMode':'demo','note':'실제 정적 노선망 동기화 완료. 운행시각 검증 후 라우팅 적용 가능.'}
    except (httpx.HTTPError,ValueError) as e:
        raise HTTPException(502,'BusTracker 연결 또는 데이터 형식 오류') from e


@app.get('/v1/integration/catalog')
def catalog():
    dbpath=ROOT/'backend/catalog.db'
    if not dbpath.exists():
        raise HTTPException(404,'동기화된 노선망이 없습니다.')
    with sqlite3.connect(dbpath) as db:
        row=db.execute('SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1').fetchone()
    if not row:
        raise HTTPException(404,'동기화된 노선망이 없습니다.')
    return json.loads(row[0])


@app.get('/v1/live/{resource}')
async def live(resource: str):
    if resource not in ('status','vehicles'):
        raise HTTPException(404,'지원하지 않는 리소스입니다.')
    try:
        return await bustracker.fetch(resource)
    except ValueError as e:
        raise HTTPException(503,str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(502,'BusTracker에 연결할 수 없습니다.') from e


@app.post('/v1/observations/collect')
async def collect():
    snapshot=catalog()
    try:
        vehicles=await bustracker.fetch('vehicles')
        count=bustracker.observe(snapshot,vehicles)
        return {'inserted':count,'source':vehicles.get('source','replay_observed'),'method':'60m 내 저속 GPS 관측; 실제 정차시각 근사치'}
    except ValueError as e:
        raise HTTPException(503,str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(502,'차량 관측 정보를 읽지 못했습니다.') from e


@app.get('/v1/observations')
def arrival_observations():
    return {'observations':bustracker.observations(),'warning':'리플레이 반복 표본은 실제 과거 날짜의 독립 관측이 아닙니다.'}


@app.get('/v1/history/{stop_id}')
def history(stop_id: str, sample_day: int=1):
    if stop_id not in engine.stops or not 1<=sample_day<=21:
        raise HTTPException(400,'정류장 또는 가상 표본일을 확인해주세요.')
    return {'source':'simulated','sampleDay':sample_day,'records':[r for r in HISTORY if r['stopId']==stop_id and r['sampleDay']==sample_day],
            'warning':'21개 가상 표본일이며 실제 3주간의 관측기록이 아닙니다.'}
