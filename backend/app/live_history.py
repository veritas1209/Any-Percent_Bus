"""Contemporary public GPS observations, isolated from historical replay data."""
import asyncio
import logging
import math
import sqlite3
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx

SOURCE='ulsan_its_live_gps'
URL='https://its.ulsan.kr/mpng/getList.json'
PAYLOAD={'postData':{'serviceName':'busService','methodName':'getGridList','paging':False},'record':{},'sorting':[]}


class LiveHistory:
    def __init__(self,network,path):
        self.path=Path(path);self.routes={r['id']:r for r in network['routes']}
        self.stops={s['id']:s for s in network['stops']};self.last_error=None
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS snapshots(observed_at REAL PRIMARY KEY,vehicles INTEGER,source TEXT);
            CREATE TABLE IF NOT EXISTS latest(vehicle_id TEXT PRIMARY KEY,route_id TEXT,lat REAL,lon REAL,
                observed_at REAL,stop_index INTEGER,trip_key TEXT,at_stop INTEGER,passage_at REAL);
            CREATE TABLE IF NOT EXISTS passages(vehicle_id TEXT,route_id TEXT,stop_id TEXT,stop_index INTEGER,
                trip_key TEXT,observed_at REAL,service_date TEXT,method TEXT,source TEXT,
                PRIMARY KEY(vehicle_id,trip_key,stop_index));
            CREATE INDEX IF NOT EXISTS passage_time ON passages(observed_at);
            CREATE TABLE IF NOT EXISTS travel_samples(vehicle_id TEXT,route_id TEXT,from_index INTEGER,to_index INTEGER,
                start_at REAL,end_at REAL,service_date TEXT,source TEXT,
                PRIMARY KEY(vehicle_id,route_id,start_at,end_at));
            ''')

    def connect(self):
        db=sqlite3.connect(self.path,timeout=15);db.row_factory=sqlite3.Row
        return db

    def record(self,rows,now=None):
        now=time.time() if now is None else now
        day=datetime.fromtimestamp(now,timezone(timedelta(hours=9))).date().isoformat()
        inserted=0;tracked=0
        with self.connect() as db:
            for raw in rows:
                route_id='its:'+str(raw.get('brtid',''));route=self.routes.get(route_id)
                if not route:continue
                try:lat,lon=float(raw['bopy2']),float(raw['bopx2']);vehicle=str(raw['busid'])
                except (KeyError,TypeError,ValueError):continue
                if not math.isfinite(lat+lon) or not (35.2<=lat<=35.85 and 128.85<=lon<=129.6):continue
                old=db.execute('SELECT * FROM latest WHERE vehicle_id=?',(vehicle,)).fetchone()
                fresh=not old or old['route_id']!=route_id or now-old['observed_at']>1800
                previous=-1 if fresh else old['stop_index'];candidates=[]
                for i,sid in enumerate(route['stops']):
                    s=self.stops[sid];meters=math.hypot((lat-s['lat'])*111000,(lon-s['lon'])*91000)
                    if meters<=35:candidates.append((meters,i,sid))
                candidates.sort(key=lambda x:(x[0],x[1]))
                if candidates:
                    nearest=candidates[0][0]
                    forward=[c for c in candidates if c[0]<=nearest+5 and c[1]>=previous]
                    meters,index,sid=min(forward,key=lambda x:x[1]) if forward else candidates[0]
                else:index=None
                wrap=index is not None and previous>=0 and index<previous-3
                if fresh or wrap:
                    trip=f'{vehicle}:{route_id}:{now:.3f}';previous=-1;passage_at=None;at_stop=-1
                else:trip=old['trip_key'];passage_at=old['passage_at'];at_stop=old['at_stop']
                if index is not None and index!=at_stop:
                    method='initial_near_stop' if fresh else 'entered_geofence_35m'
                    result=db.execute('INSERT OR IGNORE INTO passages VALUES(?,?,?,?,?,?,?,?,?)',
                        (vehicle,route_id,sid,index,trip,now,day,method,SOURCE));inserted+=result.rowcount
                    if result.rowcount and passage_at is not None and 0<index-previous<=8 and 0<now-passage_at<=1200:
                        db.execute('INSERT OR IGNORE INTO travel_samples VALUES(?,?,?,?,?,?,?,?)',
                            (vehicle,route_id,previous,index,passage_at,now,day,SOURCE))
                    if result.rowcount:previous=index;passage_at=now
                db.execute('INSERT OR REPLACE INTO latest VALUES(?,?,?,?,?,?,?,?,?)',
                    (vehicle,route_id,lat,lon,now,previous,trip,index if index is not None else -1,passage_at));tracked+=1
            db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?)',(now,len(rows),SOURCE))
            db.execute('DELETE FROM latest WHERE observed_at<?',(now-86400,))
        return dict(source=SOURCE,vehicles=len(rows),tracked=tracked,inserted=inserted)

    def coverage(self):
        with self.connect() as db:
            snapshots=db.execute('SELECT COUNT(*),MAX(observed_at) FROM snapshots').fetchone()
            passages=db.execute('SELECT COUNT(*),COUNT(DISTINCT route_id),COUNT(DISTINCT service_date) FROM passages').fetchone()
            samples=db.execute('SELECT COUNT(*) FROM travel_samples').fetchone()[0]
        return dict(source=SOURCE,snapshots=snapshots[0],lastObservedAt=snapshots[1],passages=passages[0],
            routes=passages[1],serviceDays=passages[2],travelSamples=samples,lastError=self.last_error,
            method='Public live GPS geofence observations; collection timestamps, not door-open arrival times',
            historicalBackfill=False,calibrationMinimum=dict(samplesPerPair=20,serviceDays=3))

    async def run(self,interval=30):
        async with httpx.AsyncClient(timeout=20,headers={'Referer':'https://its.ulsan.kr/route/route.do',
                'User-Agent':'AnyPercent university project - public transport observations'}) as client:
            while True:
                try:
                    response=await client.post(URL,json=PAYLOAD);response.raise_for_status();data=response.json()
                    if str(data.get('resultCode'))!='200' or not isinstance(data.get('rows'),list):
                        raise ValueError('Unexpected public ITS response')
                    await asyncio.to_thread(self.record,data['rows']);self.last_error=None
                except (httpx.HTTPError,ValueError,sqlite3.Error) as error:
                    self.last_error=type(error).__name__
                    logging.getLogger(__name__).warning('Public ITS observation: %s',self.last_error)
                await asyncio.sleep(max(30,interval))
