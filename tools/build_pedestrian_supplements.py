"""Add reviewed public walking lines to the pedestrian graph, preserving the base graph."""
import array
import hashlib
import json
import math
import struct
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.walking import WalkingGraph,distance


def main():
    supplement=json.loads((ROOT/'shared/pedestrian_supplements.json').read_text(encoding='utf-8'))
    base=ROOT/'tmp/walk-graph-base.bin'
    if not base.exists():
        current=(ROOT/'shared/walk_graph.bin').read_bytes()
        if hashlib.sha256(current).hexdigest()!=supplement['baseGraphSha256']:
            revision=supplement.get('baseGraphCommit','afdd41ea2f443f08a5faf61f359ccfc4ae10ae52')
            current=subprocess.check_output(['git','show',revision+':shared/walk_graph.bin'],cwd=ROOT)
        base.write_bytes(current)
    data=base.read_bytes();assert hashlib.sha256(data).hexdigest()==supplement['baseGraphSha256']
    graph=WalkingGraph(data)
    coords=array.array('i',graph.coords);points={(coords[i],coords[i+1]):i//2 for i in range(0,len(coords),2)}
    edges={tuple(graph.edges[i:i+2]) for i in range(0,len(graph.edges),2)}
    def node(point):
        key=tuple(round(v*1e6) for v in point)
        if key not in points:
            points[key]=len(coords)//2;coords.extend(key)
        return points[key]
    joins=[]
    for path in supplement['paths']:
        values=[node(p) for p in path['points']]
        for a,b in zip(values,values[1:]):
            if a!=b:edges.add(tuple(sorted((a,b))))
        snap=graph.snap(tuple(path['points'][-1]));assert snap and snap['error']<=40
        join=node(snap['point'])
        for a,b in ((values[-1],join),(join,snap['a']),(join,snap['b'])):
            if a!=b:edges.add(tuple(sorted((a,b))))
        joins.append(dict(stopId=path['stopId'],endConnectionErrorMeters=snap['error']))
    edges=sorted(edges);n=len(coords)//2
    offsets=array.array('I',[0])*(n+1)
    for a,b in edges:offsets[a+1]+=1;offsets[b+1]+=1
    for i in range(n):offsets[i+1]+=offsets[i]
    neighbors=array.array('I',[0])*offsets[-1];cursor=array.array('I',offsets)
    grid=defaultdict(list);edge_values=array.array('I')
    for i,(a,b) in enumerate(edges):
        edge_values.extend((a,b));neighbors[cursor[a]]=b;cursor[a]+=1;neighbors[cursor[b]]=a;cursor[b]+=1
        ay,ax=coords[a*2]/1e6,coords[a*2+1]/1e6;by,bx=coords[b*2]/1e6,coords[b*2+1]/1e6
        for x in range(math.floor(min(ax,bx)*910),math.floor(max(ax,bx)*910)+1):
            for y in range(math.floor(min(ay,by)*1110),math.floor(max(ay,by)*1110)+1):grid[x,y].append(i)
    cells=array.array('i');entries=array.array('I')
    for (x,y),values in sorted(grid.items()):cells.extend((x,y,len(entries),len(values)));entries.extend(values)
    out=bytearray(struct.pack('<4sIIIII',b'APW1',n,len(neighbors),len(edges),len(grid),len(entries)))
    for values in (coords,offsets,neighbors,edge_values,cells,entries):out.extend(values.tobytes())
    new=WalkingGraph(bytes(out));network=json.loads((ROOT/'shared/service_network.json').read_text(encoding='utf-8'))
    missing=[s['id'] for s in network['stops'] if new.snap((s['lat'],s['lon'])) is None]
    assert not missing,missing
    for name in ('shared/walk_graph.bin','app/assets/data/walk_graph.bin'):(ROOT/name).write_bytes(out)
    network['pedestrianSupplementalSources']=supplement['sources']
    network['pedestrianGraphSha256']=hashlib.sha256(out).hexdigest()
    for name in ('shared/service_network.json','app/assets/data/service_network.json'):
        (ROOT/name).write_text(json.dumps(network,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    report=dict(baseGraphSha256=supplement['baseGraphSha256'],sha256=hashlib.sha256(out).hexdigest(),
        addedNodes=n-len(graph.coords)//2,addedEdges=len(edges)-len(graph.edges)//2,
        reviewedWalkingLines=len(supplement['paths']),unsnappedStops=missing,joins=joins)
    (ROOT/'artifacts/pedestrian-data-repairs.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    metadata=ROOT/'artifacts/location-assets.json'
    if metadata.exists():
        location=json.loads(metadata.read_text(encoding='utf-8'))
        location.update(walkGraphSha256=report['sha256'],walkGraphBaseSha256=report['baseGraphSha256'],
            pedestrianSupplementFile='shared/pedestrian_supplements.json')
        metadata.write_text(json.dumps(location,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
