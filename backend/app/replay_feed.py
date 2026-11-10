"""Optional read-only adapter over BusTracker CSV, hosted beside Any%, not in production BusTracker.

It replays recorded coordinates on a looping virtual clock. It neither ingests GPS
into BusTracker nor claims to share its running process's vehicle classification.
"""
from __future__ import annotations

import bisect
import csv
import hashlib
import json
import os
import secrets
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException


class ReplayFeed:
    def __init__(self, path: Path, catalog: dict, speed: float=1):
        self.catalog=catalog
        self.speed=speed
        self.started=time.monotonic()
        self.rows={}
        with path.open(encoding='utf-8-sig') as handle:
            reader=csv.reader(handle);next(reader)
            for row in reader:
                if row[4]=='0':
                    continue
                # Recording timestamps are Korea local time, explicitly converted to UTC epoch.
                stamp=datetime.strptime(row[0],'%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp()-9*3600
                self.rows.setdefault(row[1],[]).append((stamp,row[4],float(row[6]),float(row[5]),float(row[7])))
        for rows in self.rows.values():
            rows.sort(key=lambda r:r[0])
        self.times={key:[r[0] for r in rows] for key,rows in self.rows.items()}
        self.start=min(r[0] for rows in self.rows.values() for r in rows)
        self.end=max(r[0] for rows in self.rows.values() for r in rows)
        self.duration=self.end-self.start+1
        self.version=hashlib.sha256(json.dumps(catalog,sort_keys=True).encode()).hexdigest()[:16]

    def snapshot(self, elapsed=None):
        elapsed=(time.monotonic()-self.started)*self.speed if elapsed is None else elapsed
        cycle=int(elapsed//self.duration)
        current=self.start+elapsed%self.duration
        result=[]
        for vehicle,rows in self.rows.items():
            i=bisect.bisect_right(self.times[vehicle],current)-1
            if i<0:
                continue
            stamp,route,lat,lon,speed=rows[i]
            if current-stamp>120:
                continue
            result.append({'vehicleId':vehicle,'routeId':route,'tripId':f'{cycle}:{vehicle}:{route}',
                           'lat':lat,'lon':lon,'speedKph':speed,'virtualEpochSec':stamp,
                           'source':'replay_observed'})
        return {'vehicles':result,'virtualEpochSec':current,'cycle':cycle,'source':'replay_observed',
                'adapter':'isolated_csv_replay','observedAt':time.time()}


def create_router(path: Path,catalog: dict):
    router=APIRouter(prefix='/integration/v1',tags=['Isolated BusTracker CSV replay'])
    feed=None
    lock=threading.Lock()

    def access(key):
        nonlocal feed
        expected=os.getenv('BUSTRACKER_INTEGRATION_KEY','')
        if not expected:
            raise HTTPException(503,'Integration key is not configured')
        if not secrets.compare_digest(key,expected):
            raise HTTPException(401,'Invalid integration key')
        with lock:
            if feed is None:
                feed=ReplayFeed(path,catalog,float(os.getenv('REPLAY_SPEED','1')))
        return feed

    @router.get('/network')
    def network(x_integration_key: str=Header(default='')):
        current=access(x_integration_key)
        return dict(catalog,version=current.version,adapter='isolated_csv_replay',observedAt=time.time())

    @router.get('/status')
    def status(x_integration_key: str=Header(default='')):
        current=access(x_integration_key)
        snapshot=current.snapshot()
        return {'mode':'CSV_REPLAY','source':'replay_observed','adapter':'isolated_csv_replay',
                'replay':{'cycle':snapshot['cycle'],'virtualEpochSec':snapshot['virtualEpochSec'],'speed':current.speed},
                'recordingStart':current.start,'recordingEnd':current.end}

    @router.get('/vehicles')
    def vehicles(x_integration_key: str=Header(default='')):
        return access(x_integration_key).snapshot()

    return router
