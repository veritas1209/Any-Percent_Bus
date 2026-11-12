"""Distance-unbounded stop transfers over the contracted pedestrian road graph."""
import heapq
import json
import math
import struct
from functools import lru_cache
from pathlib import Path

from .topology import labels
from .native_graph import make_native_graph


class TransferGraph:
    def __init__(self,data,use_native=True):
        magic,n,m,s,size,_=struct.unpack_from('<4sIIIII',data)
        if magic!=b'APX1':raise ValueError('Invalid transfer graph')
        self.meta=json.loads(data[24:24+size])
        self.data=data;offset=24+size
        def take(count,code):
            nonlocal offset
            width=8 if code=='d' else 4
            view=memoryview(data)[offset:offset+count*width].cast(code)
            offset+=count*width;return view
        self.offsets=take(n+1,'I');self.neighbors=take(m,'I');nodes=take(s,'i')
        offset+=( -offset)%8
        self.weights=take(m,'d');errors=take(s,'d')
        if offset!=len(data):raise ValueError('Unexpected transfer graph length')
        self.stops={sid:(nodes[i],errors[i]) for i,sid in enumerate(self.meta['stopIds']) if nodes[i]>=0}
        self.native=make_native_graph(self.offsets,self.neighbors,self.weights) if use_native else None

    def latest(self,values,walking_speed,earliest=-math.inf):
        """Optimistic reverse walking times, without a distance or walking-budget limit."""
        scale=walking_speed*60;costs={};queue=[]
        seeds=dict(values)
        for sid,others in self.meta.get('coincidentStops',{}).items():
            limit=max((values.get(other,-math.inf) for other in others),default=-math.inf)
            if limit>seeds.get(sid,-math.inf):seeds[sid]=limit
        if self.native is not None and seeds:
            pivot=max(seeds.values());starts={}
            for sid,limit in seeds.items():
                if sid not in self.stops:continue
                node,error=self.stops[sid];meters=(pivot-limit)*scale+error
                if meters<starts.get(node,math.inf):starts[node]=max(0,meters)
            distances=self.native.distances(starts,(pivot-earliest+1e-6)*scale)
            result=dict(seeds)
            for sid,(node,error) in self.stops.items():
                limit=pivot-(float(distances[node])+error)/scale
                if limit>result.get(sid,-math.inf):result[sid]=limit
            return {sid:value for sid,value in result.items() if value>=earliest-1e-6}
        for sid,limit in seeds.items():
            if sid not in self.stops:continue
            node,error=self.stops[sid];limit-=error/scale
            if limit<earliest-1e-6:continue
            if limit>costs.get(node,-math.inf):costs[node]=limit;heapq.heappush(queue,(-limit,node))
        while queue:
            negative,node=heapq.heappop(queue);limit=-negative
            if limit!=costs[node]:continue
            for i in range(self.offsets[node],self.offsets[node+1]):
                other=self.neighbors[i];candidate=limit-self.weights[i]/scale
                if candidate>=earliest-1e-6 and candidate>costs.get(other,-math.inf):
                    costs[other]=candidate;heapq.heappush(queue,(-candidate,other))
        result=dict(seeds)
        for sid,(node,error) in self.stops.items():
            limit=costs.get(node,-math.inf)-error/scale
            if limit>result.get(sid,-math.inf):result[sid]=limit
        return {sid:value for sid,value in result.items() if value>=earliest-1e-6}

    def spread(self,frontier,walking_speed,budget,deadline=math.inf,*,respect_used=False,boardable=None):
        """Retain arrival/walking Pareto labels, sharing each road relaxation across origins."""
        roots=list(frontier);kept={};queue=[];serial=0
        scale=walking_speed*60
        def put(node,now,walked,root):
            nonlocal serial
            if walked>budget+.001 or now>deadline+1e-6:return
            values=kept.setdefault(node,[])
            used=roots[root][3]
            if any(t<=now+1e-9 and w<=walked+1e-7 and
                   (not respect_used or roots[r][3]<=used) for t,w,r in values):return
            values[:]=[(t,w,r) for t,w,r in values if not (now<=t+1e-9 and walked<=w+1e-7 and
                       (not respect_used or used<=roots[r][3]))]
            item=(now,walked,root);values.append(item)
            heapq.heappush(queue,(now,serial,node,item));serial+=1
        for root,(sid,now,legs,used,walked) in enumerate(roots):
            if sid in self.stops:
                node,error=self.stops[sid]
                put(node,now+error/scale,walked+error,root)
        while queue:
            _,_,node,item=heapq.heappop(queue)
            if item not in kept[node]:continue
            now,walked,root=item
            for i in range(self.offsets[node],self.offsets[node+1]):
                meters=self.weights[i]
                put(self.neighbors[i],now+meters/scale,walked+meters,root)
        result=list(roots)
        for origin,start,legs,used,walked in roots:
            for sid in self.meta.get('coincidentStops',{}).get(origin,()):
                if boardable is not None and sid not in boardable:continue
                leg={'kind':'walk','from':origin,'to':sid,'depart':start,'arrive':start,'meters':0.0,'_transferWalk':True}
                result.append((sid,start,legs+[leg],used,walked))
        for sid,(node,error) in self.stops.items():
            if boardable is not None and sid not in boardable:continue
            for now,walked,root in kept.get(node,()):
                origin,start,legs,used,prior_walk=roots[root]
                if sid==origin:continue
                meters=round(walked-prior_walk+error,1)
                total=prior_walk+meters;end=start+meters/scale
                if total>budget+.001 or end>deadline+1e-6:continue
                leg={'kind':'walk','from':origin,'to':sid,'depart':start,'arrive':end,
                     'meters':meters,'_transferWalk':True}
                result.append((sid,end,legs+[leg],used,total))
        return list(labels(result,respect_used=respect_used))


@lru_cache(maxsize=1)
def default_transfer_graph():
    return TransferGraph((Path(__file__).resolve().parents[2]/'shared/transfer_graph.bin').read_bytes())
