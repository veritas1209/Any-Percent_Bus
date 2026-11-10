"""Read-only, key-authenticated Any% integration. No DB or GPS ingestion mutations."""
import hashlib
import json
import os
import secrets
import time

from fastapi import APIRouter, Header, HTTPException
import db
import state

router = APIRouter(prefix='/integration/v1', tags=['Any% integration'])


def authorize(x_integration_key: str = ''):
    expected = os.getenv('BUSTRACKER_INTEGRATION_KEY', '')
    if not expected:
        raise HTTPException(503, 'Integration key is not configured')
    if not secrets.compare_digest(x_integration_key, expected):
        raise HTTPException(401, 'Invalid integration key')


@router.get('/network')
def network(x_integration_key: str = Header(default='')):
    authorize(x_integration_key)
    info = {r['route_id']: r for r in db.get_route_list()}
    routes, stops = [], {}
    with state.LOCK:
        for rid, route in state.ROUTES.items():
            entries=[]
            for seq, sid, lat, lon in route.stops:
                sid=str(sid)
                if not state.valid_coord(lat, lon):
                    continue
                stops.setdefault(sid, {'id':sid,'name':state.STOP_NAMES.get(sid,sid),'lat':lat,'lon':lon})
                entries.append({'stopId':sid,'sequence':seq})
            meta=info.get(rid,{})
            routes.append({'id':rid,'number':meta.get('route_no',''),'name':meta.get('display_name',''),'stops':entries})
    payload={'routes':routes,'stops':list(stops.values())}
    version=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:16]
    return dict(payload,version=version,source='bustracker',observedAt=time.time())


@router.get('/status')
def status(x_integration_key: str = Header(default='')):
    authorize(x_integration_key)
    with state.LOCK:
        replay=dict(state.REPLAY_STATE)
    return {'mode':os.getenv('BUSTRACKER_MODE','D'),'replay':replay,'observedAt':time.time()}


@router.get('/vehicles')
def vehicles(x_integration_key: str = Header(default='')):
    authorize(x_integration_key)
    source='replay_observed' if os.getenv('BUSTRACKER_MODE','D')=='D' else 'live_observed'
    out=[]
    with state.LOCK:
        current=state.REPLAY_STATE.get('virtualEpochSec')
        cycle=state.REPLAY_STATE.get('cycle',0)
        for did, tr in state.TRACKS.items():
            if not tr.trail or not tr.is_bus:
                continue
            t,lat,lon,kph=tr.trail[-1]
            if current is not None and (t>current or current-t>120):
                continue
            out.append({'vehicleId':did,'routeId':tr.matched_route,'tripId':f'{cycle}:{did}:{tr.matched_route}',
                        'lat':lat,'lon':lon,'speedKph':kph,'virtualEpochSec':t})
    return {'vehicles':out,'virtualEpochSec':current,'cycle':cycle,'source':source,'observedAt':time.time()}
