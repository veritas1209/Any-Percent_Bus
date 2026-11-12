"""Contract pedestrian degree-two chains, retaining exact stop projections and distances."""
import array
import hashlib
import json
import math
import struct
import sys
from collections import defaultdict, deque
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.walking import WalkingGraph, distance


def build(data, stops):
    graph=WalkingGraph(data)
    n=len(graph.offsets)-1
    snaps={s['id']:graph.snap((s['lat'],s['lon'])) for s in stops}
    kept={i for i in range(n) if graph.offsets[i+1]-graph.offsets[i]!=2}
    by_edge=defaultdict(list)
    for sid,snap in snaps.items():
        if snap:
            kept.update((snap['a'],snap['b']))
            by_edge[snap['edge']].append((snap['f'],sid))
    kept=sorted(kept);index={node:i for i,node in enumerate(kept)}
    adjacency=[{} for _ in kept]
    def link(a,b,meters):
        if a==b:return
        adjacency[a][b]=min(adjacency[a].get(b,math.inf),meters)
        adjacency[b][a]=min(adjacency[b].get(a,math.inf),meters)
    # Every retained-to-retained chain is traversed once in each direction.
    for a in kept:
        for j in range(graph.offsets[a],graph.offsets[a+1]):
            prior,node=a,graph.neighbors[j]
            meters=distance(graph.point(a),graph.point(node))
            while node not in index:
                neighbors=graph.neighbors[graph.offsets[node]:graph.offsets[node+1]]
                other=neighbors[0] if neighbors[0]!=prior else neighbors[1]
                meters+=distance(graph.point(node),graph.point(other))
                prior,node=node,other
            if a<node:link(index[a],index[node],meters)
    stop_nodes={};stop_errors={}
    for edge, values in by_edge.items():
        a,b=graph.edges[edge*2:edge*2+2]
        # Split only this original road edge, never a competing contracted chain.
        aa,bb=index[a],index[b]
        direct=distance(graph.point(a),graph.point(b))
        old=adjacency[aa].get(bb,math.inf)
        if abs(old-direct)<1e-6:
            adjacency[aa].pop(bb,None);adjacency[bb].pop(aa,None)
        else:
            # A shorter parallel path must remain; the direct edge is inserted as well.
            pass
        last,position=aa,0.0
        for fraction,sid in sorted(values):
            if fraction<=1e-12:node=aa
            elif fraction>=1-1e-12:node=bb
            elif abs(fraction-position)<1e-12:node=last
            else:
                node=len(adjacency);adjacency.append({})
            link(last,node,(fraction-position)*direct)
            stop_nodes[sid]=node;stop_errors[sid]=snaps[sid]['error']
            last,position=node,fraction
        link(last,bb,(1-position)*direct)
    # Branches without a stop cannot improve a positive-distance stop-to-stop walk.
    anchors=set(stop_nodes.values())
    queue=deque(i for i,row in enumerate(adjacency) if i not in anchors and len(row)<=2)
    removed=set()
    while queue:
        node=queue.popleft()
        if node in removed or node in anchors or len(adjacency[node])>2:continue
        row=adjacency[node];near=list(row)
        if len(near)==2:link(near[0],near[1],row[near[0]]+row[near[1]])
        for other in near:
            adjacency[other].pop(node,None)
            if other not in anchors and len(adjacency[other])<=2:queue.append(other)
        adjacency[node]={};removed.add(node)
    retained=[i for i in range(len(adjacency)) if i not in removed]
    remap={old:i for i,old in enumerate(retained)}
    adjacency=[{remap[b]:meters for b,meters in adjacency[a].items()} for a in retained]
    stop_nodes={sid:remap[node] for sid,node in stop_nodes.items()}
    ids=[s['id'] for s in stops]
    positions={s['id']:(s['lat'],s['lon']) for s in stops};bins=defaultdict(list)
    for sid,(lat,lon) in positions.items():bins[round(lat*1e6),round(lon*1e6)].append(sid)
    aliases={}
    for sid,(lat,lon) in positions.items():
        x,y=round(lat*1e6),round(lon*1e6)
        near=[other for dx in (-1,0,1) for dy in (-1,0,1) for other in bins.get((x+dx,y+dy),())
              if other!=sid and distance((lat,lon),positions[other])<.1]
        if near:aliases[sid]=near
    meta=json.dumps(dict(stopIds=ids,coincidentStops=aliases,sourceGraphSha256=hashlib.sha256(data).hexdigest(),
        stopPositionsSha256=hashlib.sha256(json.dumps([(s['id'],s['lat'],s['lon']) for s in stops],separators=(',',':')).encode()).hexdigest()),separators=(',',':')).encode()
    # Pad the JSON to preserve typed-array alignment in Dart.
    meta+=b' '*((-len(meta))%8)
    offsets=array.array('I',[0]);neighbors=array.array('I');weights=array.array('d')
    for row in adjacency:
        for node,meters in sorted(row.items()):neighbors.append(node);weights.append(meters)
        offsets.append(len(neighbors))
    nodes=array.array('i',[stop_nodes.get(s,-1) for s in ids]);errors=array.array('d',[stop_errors.get(s,math.inf) for s in ids])
    result=bytearray(struct.pack('<4sIIIII',b'APX1',len(adjacency),len(neighbors),len(ids),len(meta),0))
    result.extend(meta)
    for values in (offsets,neighbors,nodes):result.extend(values.tobytes())
    result.extend(b' '*((-len(result))%8))
    for values in (weights,errors):result.extend(values.tobytes())
    return bytes(result),dict(nodes=len(adjacency),directedEdges=len(neighbors),stops=len(ids),
        unsnapped=[s for s in ids if s not in stop_nodes],originalRoadNodes=n,
        sourceGraphSha256=hashlib.sha256(data).hexdigest())


def main():
    network=json.loads((ROOT/'shared/service_network.json').read_text(encoding='utf-8'))
    binary,report=build((ROOT/'shared/walk_graph.bin').read_bytes(),network['stops'])
    for path in ('shared/transfer_graph.bin','app/assets/data/transfer_graph.bin'):(ROOT/path).write_bytes(binary)
    network['walkingTransfers']='road_graph'
    network['transferGraphSha256']=hashlib.sha256(binary).hexdigest()
    network['version']='ulsan-its-2026-11-11+sources4+walk1'
    encoded=json.dumps(network,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    for path in ('shared/service_network.json','app/assets/data/service_network.json'):(ROOT/path).write_bytes(encoded)
    report.update(bytes=len(binary),sha256=hashlib.sha256(binary).hexdigest(),
        method='Exact degree-two chain contraction; no transfer distance cap; stop projection offsets retained')
    (ROOT/'artifacts/transfer-graph.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
