"""Reconstruct time-indexed road trajectories from GPS, never from stop centroids."""
import argparse
import bisect
import csv
import hashlib
import json
import math
import time
from collections import defaultdict
from pathlib import Path

from local_roads import RoadGraph,compact,distance,length

ROOT=Path(__file__).resolve().parents[1]


def simplify(points,tolerance=2):
    if len(points)<=2:return points
    a,b=points[0],points[-1];dx=(b[1]-a[1])*91000;dy=(b[0]-a[0])*111000;den=dx*dx+dy*dy
    best=(-1,0)
    for i,p in enumerate(points[1:-1],1):
        x=(p[1]-a[1])*91000;y=(p[0]-a[0])*111000;f=max(0,min(1,(x*dx+y*dy)/den)) if den else 0
        best=max(best,((x-f*dx)**2+(y-f*dy)**2,i))
    if best[0]<=tolerance*tolerance:return [a,b]
    i=best[1];return simplify(points[:i+1],tolerance)[:-1]+simplify(points[i:],tolerance)


def trace_groups(samples):
    groups=[];group=[]
    for t,p,speed in samples:
        if not (35.2<=p[0]<=35.85 and 128.85<=p[1]<=129.6):continue
        if group:
            dt=(t-group[-1][0])*60
            if dt<=0:continue
            if dt>120 or distance(group[-1][1],p)>dt*150/3.6+30:
                if len(group)>=2:groups.append(group)
                group=[]
            elif speed<=2 and group[-1][2]<=2 and distance(group[-1][1],p)<30:
                p=group[-1][1]
        group.append((t,p,speed))
    if len(group)>=2:groups.append(group)
    return groups


def match_trace(graph,samples):
    """Small Viterbi beam with heading and observed/network-distance agreement."""
    layers=[];results=[]
    def finish():
        if len(layers)<2:return
        index=min(range(len(layers[-1])),key=lambda i:layers[-1][i]['cost']);chain=[]
        for layer in reversed(layers):
            state=layer[index];chain.append(state);index=state['previous']
        chain.reverse();points=[list(chain[0]['snap'].point)];frames=[[chain[0]['time'],0.0]];meters=0.0
        for state in chain[1:]:
            road=compact(simplify(state['path']))
            meters+=length(road);points.extend(road[1:]);frames.append([state['time'],round(meters,3)])
        results.append({'points':compact(points),'samples':frames,'meters':round(meters,3),
                        'maxSnapErrorMeters':round(max(s['snap'].error for s in chain),1)})
    for i,(t,p,speed) in enumerate(samples):
        before=samples[max(0,i-1)][1];after=samples[min(len(samples)-1,i+1)][1]
        vx,vy=(after[1]-before[1])*91000,(after[0]-before[0])*111000;norm=math.hypot(vx,vy)
        candidates=[]
        for snap in graph.candidates(p,12):
            if snap.error>80:continue
            a,b=graph.nodes[snap.a],graph.nodes[snap.b];dx,dy=(b[1]-a[1])*91000,(b[0]-a[0])*111000;d=math.hypot(dx,dy)
            heading=1.5*(1-(dx*vx+dy*vy)/(d*norm)) if norm>15 and speed>2 and d else 0
            emission=snap.error*snap.error/800+heading
            candidates.append((emission,snap))
        candidates.sort(key=lambda x:(x[0],x[1].a,x[1].b));candidates=candidates[:2]
        if not candidates:
            finish();layers=[];continue
        current=[]
        for emission,snap in candidates:
            if not layers:
                current.append({'snap':snap,'cost':emission,'previous':0,'path':[],'time':t});continue
            best=None
            for previous,state in enumerate(layers[-1]):
                observed=distance(samples[i-1][1],p)
                elapsed=(t-state['time'])*60
                limit=min(max(80,observed*4+50),elapsed*130/3.6+5)
                path=graph.connect(state['snap'],snap,limit)
                if path is None:continue
                meters=length(path)
                if meters>limit:continue
                score=state['cost']+emission+abs(meters-observed)/35
                if best is None or score<best['cost']:best={'snap':snap,'cost':score,'previous':previous,'path':path,'time':t}
            if best is not None:current.append(best)
        if not current:
            finish();layers=[]
            current=[{'snap':snap,'cost':emission,'previous':0,'path':[],'time':t} for emission,snap in candidates]
        layers.append(current)
    finish();return results


def progress(frames,t):
    index=bisect.bisect_right([f[0] for f in frames],t)-1
    if index<0:return frames[0][1]
    if index>=len(frames)-1:return frames[-1][1]
    a,b=frames[index],frames[index+1];f=(t-a[0])/(b[0]-a[0]);return a[1]+f*(b[1]-a[1])


def cut(points,start,end):
    result=[];at=0
    for a,b in zip(points,points[1:]):
        size=distance(a,b);finish=at+size
        if finish>=start and at<=end:
            for value in (max(start,at),min(end,finish)):
                f=(value-at)/size if size else 0;p=[a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1])]
                if not result or p!=result[-1]:result.append(p)
        at=finish
    return compact(result)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int);args=parser.parse_args()
    started=time.monotonic();network=json.loads((ROOT/'shared/observed_network.json').read_text(encoding='utf-8'))
    graph=RoadGraph(json.loads((ROOT/'tmp/ulsan-all-roads.json').read_text(encoding='utf-8')),'drive')
    traces=defaultdict(dict)
    with (ROOT/'tmp/jetson-source/gps_replay.csv').open(encoding='utf-8-sig') as f:
        reader=csv.reader(f);next(reader)
        for row in reader:
            if row[4]=='0':continue
            t=int(row[0][11:13])*60+int(row[0][14:16])+int(row[0][17:19])/60
            traces[row[4],row[1]][t]=(t,(float(row[6]),float(row[5])),float(row[7]))
    traces={key:sorted(values.values()) for key,values in traces.items()}
    ticks={key:[s[0] for s in values] for key,values in traces.items()}
    fingerprint=hashlib.sha256((ROOT/'tmp/jetson-source/gps_replay.csv').read_bytes()).hexdigest()+':motion3b'
    cache_path=ROOT/'tmp/motion-traces-cache.json';cache={}
    if cache_path.exists():
        prior=json.loads(cache_path.read_text(encoding='utf-8'))
        if prior.get('fingerprint')==fingerprint:cache=prior['routes']
    def save():
        temp=cache_path.with_suffix('.tmp');temp.write_text(json.dumps({'fingerprint':fingerprint,'routes':cache},separators=(',',':')),encoding='utf-8');temp.replace(cache_path)
    pool=dict(network.get('shapes',{}));family_edges={};count=0;gaps=0
    for route in network['routes']:
        if route['scheduleSource']!='replay_observed':continue
        count+=1
        if args.limit and count>args.limit:break
        if route['id'] not in cache:
            key=(route['familyId'],route['vehicleId']);start=route['departures'][0];end=start+route['offsets'][-1]
            lo,hi=bisect.bisect_left(ticks[key],start-.001),bisect.bisect_right(ticks[key],end+.001)
            chunks=[]
            for group in trace_groups(traces[key][lo:hi]):chunks.extend(match_trace(graph,group))
            cache[route['id']]=chunks
        chunks=cache[route['id']];route['traceChunks']=[]
        for i,chunk in enumerate(chunks):
            key=f"motion3:{route['id']}:{i}";pool[key]={k:v for k,v in chunk.items() if k!='samples'}|{'source':'gps_trace_matched'}
            route['traceChunks'].append({'shape':key,'samples':chunk['samples']})
        route['shapeSegments']=[]
        for i,(a,b) in enumerate(zip(route['stops'],route['stops'][1:])):
            t0=route['departures'][0]+route['offsets'][i];t1=route['departures'][0]+route['offsets'][i+1];key=f"motion-stop3:{route['id']}:{i}"
            valid=next((c for c in chunks if c['samples'][0][0]<=t0+.001 and c['samples'][-1][0]>=t1-.001),None)
            if valid:
                points=cut(valid['points'],progress(valid['samples'],t0),progress(valid['samples'],t1))
                if len(points)<2:points=valid['points'][:1]*2
                pool[key]={'points':points,'meters':round(length(points),1),'source':'gps_trace_matched'}
            else:pool[key]={'points':[],'meters':None,'source':'unavailable'};gaps+=1
            route['shapeSegments'].append(key)
            if pool[key]['points']:family_edges.setdefault((route['familyId'],a,b),key)
        if count%25==0:
            save();print('MOTION',count,'seconds',round(time.monotonic()-started,1),'cache',len(cache),flush=True)
    save()
    if args.limit:print('PREVIEW',count-1,'seconds',round(time.monotonic()-started,2));return
    for route in network['routes']:
        if route['scheduleSource']!='catalog_topology' or route.get('routeSource')=='gps_proximity_inferred':continue
        route['shapeSegments']=[family_edges.get((route['familyId'],a,b),old) for a,b,old in zip(route['stops'],route['stops'][1:],route['shapeSegments'])]
        route['distanceOffsets']=[0]
        for key in route['shapeSegments']:route['distanceOffsets'].append(round(route['distanceOffsets'][-1]+(pool[key].get('meters') or 0),1))
    used={r for route in network['routes'] for r in route.get('shapeSegments',[])}|{p['shape'] for p in network['footpaths'] if isinstance(p.get('shape'),str)}
    used|={c['shape'] for route in network['routes'] for c in route.get('traceChunks',[])}
    network['shapes']={k:pool[k] for k in used};network['geometryVersion']='local-osm-trace-3';network['motionVersion']='gps-clock-1'
    network['version']='jetson-2025-12-31-all+trace3b+locations1'
    for path in (ROOT/'shared/observed_network.json',ROOT/'app/assets/data/observed_network.json'):
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(network,ensure_ascii=False,separators=(',',':')),encoding='utf-8');temp.replace(path)
    report={'observedRuns':count,'chunks':sum(len(r.get('traceChunks',[])) for r in network['routes']),'missingStopGeometry':gaps,
            'method':'Two-state Viterbi with heading and distance agreement; reject matched travel over 130km/h plus 5m GPS tolerance per interval; stationary jitter held; gaps over 120 seconds split',
            'forcedStopAnchors':False,'gpsExternalTransmission':False,'elapsedSeconds':round(time.monotonic()-started,2)}
    (ROOT/'artifacts/motion-build.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('DONE',report,flush=True)


if __name__=='__main__':main()
