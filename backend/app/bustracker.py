"""Transport adapter and explicitly approximate, replay-cycle-scoped arrival observations."""
import json
import math
import os
import sqlite3
import time
from pathlib import Path

import httpx

DB=Path(__file__).resolve().parents[1]/'catalog.db'


async def fetch(path):
    base=os.getenv('BUSTRACKER_URL','').rstrip('/')
    if not base:
        raise ValueError('BUSTRACKER_URL이 설정되지 않았습니다.')
    async with httpx.AsyncClient(timeout=15) as client:
        response=await client.get(base+'/integration/v1/'+path,headers={'X-Integration-Key':os.getenv('BUSTRACKER_INTEGRATION_KEY','')})
        response.raise_for_status()
        return response.json()


def distance(a,b):
    x=math.radians(a['lat']-b['lat']); y=math.radians(a['lon']-b['lon'])
    return 6371000*2*math.asin(math.sqrt(math.sin(x/2)**2+math.cos(math.radians(a['lat']))*math.cos(math.radians(b['lat']))*math.sin(y/2)**2))


def observe(network,vehicles,db_path=DB):
    source=vehicles.get('source','replay_observed')
    if source not in ('replay_observed','live_observed'):
        raise ValueError('관측 데이터 출처를 확인할 수 없습니다.')
    stops={s['id']:s for s in network['stops']}
    routes={r['id']:r for r in network['routes']}
    count=0
    with sqlite3.connect(db_path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS arrivals(source TEXT,trip_id TEXT,stop_id TEXT,route_id TEXT,virtual_epoch REAL,observed_at REAL,method TEXT,PRIMARY KEY(source,trip_id,stop_id))')
        for v in vehicles.get('vehicles',[]):
            if v.get('speedKph',100)>7 or v.get('virtualEpochSec') is None:
                continue
            route=routes.get(v.get('routeId'))
            if not route:
                continue
            candidates=[stops[s['stopId']] for s in route['stops'] if s['stopId'] in stops]
            if not candidates:
                continue
            stop=min(candidates,key=lambda s:distance(v,s))
            if distance(v,stop)>60:
                continue
            # Replaying the same recording is never relabeled as an independent real day.
            result=db.execute('INSERT OR IGNORE INTO arrivals VALUES(?,?,?,?,?,?,?)',(source,v['tripId'],stop['id'],v['routeId'],v['virtualEpochSec'],time.time(),'geofence_60m_low_speed'))
            count+=result.rowcount
    return count


def observations(db_path=DB):
    with sqlite3.connect(db_path) as db:
        db.row_factory=sqlite3.Row
        exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='arrivals'").fetchone()
        if not exists:
            return []
        return [dict(row) for row in db.execute('SELECT * FROM arrivals ORDER BY observed_at DESC LIMIT 500')]
