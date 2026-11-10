"""Local road graph and GPS-constrained geometry. Never sends coordinates over a network."""
from __future__ import annotations

import heapq
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


def xy(point):
    return point[1]*91000,point[0]*111000


def distance(a,b):
    ax,ay=xy(a);bx,by=xy(b)
    return math.hypot(ax-bx,ay-by)


def length(points):
    return sum(distance(a,b) for a,b in zip(points,points[1:]))


DRIVE={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','living_street','service','busway','bus_guideway','road'}
FOOT=DRIVE-{'motorway','motorway_link','trunk','trunk_link','bus_guideway'}|{'footway','pedestrian','path','steps','cycleway'}


def extract(pbf: Path,target: Path):
    import osmium

    class Roads(osmium.SimpleHandler):
        def __init__(self):
            super().__init__();self.nodes={};self.ways=[]
        def node(self,n):
            # Fixed public Ulsan metropolitan envelope, not a GPS-derived upload.
            if 35.40<=n.location.lat<=35.72 and 129.10<=n.location.lon<=129.55:
                self.nodes[n.id]=[round(n.location.lat,7),round(n.location.lon,7)]
        def way(self,w):
            highway=w.tags.get('highway','')
            if highway not in DRIVE|FOOT or w.tags.get('area')=='yes':return
            tags=dict(w.tags)
            drive=highway in DRIVE and (tags.get('motor_vehicle')!='no' or tags.get('bus') in ('yes','designated'))
            foot=highway in FOOT and tags.get('foot')!='no'
            if tags.get('access')=='no':
                drive=drive and tags.get('bus') in ('yes','designated','permissive')
                foot=foot and tags.get('foot') in ('yes','designated','permissive')
            if not drive and not foot:return
            oneway=tags.get('oneway','yes' if tags.get('junction')=='roundabout' else 'no')
            if tags.get('oneway:bus')=='no':oneway='no'
            pairs=[]
            refs=[n.ref for n in w.nodes]
            for a,b in zip(refs,refs[1:]):
                if a in self.nodes and b in self.nodes and a!=b:pairs.append([a,b])
            if pairs:self.ways.append({'id':w.id,'pairs':pairs,'drive':drive,'foot':foot,'oneway':oneway})

    reader=Roads();reader.apply_file(str(pbf))
    used={n for w in reader.ways for pair in w['pairs'] for n in pair}
    data={'source':'OpenStreetMap contributors / OSM Korea regional extract','nodes':{str(n):reader.nodes[n] for n in used},'ways':reader.ways}
    target.write_text(json.dumps(data,separators=(',',':')),encoding='utf-8')
    print('ROAD_GRAPH',len(used),'nodes',len(reader.ways),'ways',flush=True)


@dataclass(frozen=True)
class Snap:
    a: int
    b: int
    fraction: float
    point: tuple[float,float]
    error: float


class RoadGraph:
    def __init__(self,data,mode='drive'):
        self.nodes={int(k):tuple(v) for k,v in data['nodes'].items()}
        self.adj=defaultdict(dict);self.grid=defaultdict(list);self.mode=mode
        for way in data['ways']:
            if not way[mode]:continue
            for a,b in way['pairs']:
                directions=[(a,b),(b,a)]
                if mode=='drive':
                    if way['oneway'] in ('yes','1','true'):directions=[(a,b)]
                    elif way['oneway']=='-1':directions=[(b,a)]
                for u,v in directions:self.adj[u][v]=distance(self.nodes[u],self.nodes[v])
        for a,neighbors in self.adj.items():
            for b in neighbors:
                ax,ay=xy(self.nodes[a]);bx,by=xy(self.nodes[b])
                for x in range(math.floor(min(ax,bx)/100),math.floor(max(ax,bx)/100)+1):
                    for y in range(math.floor(min(ay,by)/100),math.floor(max(ay,by)/100)+1):self.grid[x,y].append((a,b))
        self.cache={}

    def candidates(self,point,count=6):
        px,py=xy(point);cx,cy=math.floor(px/100),math.floor(py/100)
        edges=set()
        for radius in (1,3,8):
            for x in range(cx-radius,cx+radius+1):
                for y in range(cy-radius,cy+radius+1):edges.update(self.grid.get((x,y),[]))
            if edges:break
        result=[]
        for a,b in edges:
            ax,ay=xy(self.nodes[a]);bx,by=xy(self.nodes[b]);dx,dy=bx-ax,by-ay
            if dx==dy==0:continue
            f=max(0,min(1,((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy)))
            error=math.hypot(px-ax-f*dx,py-ay-f*dy)
            lat=self.nodes[a][0]+f*(self.nodes[b][0]-self.nodes[a][0]);lon=self.nodes[a][1]+f*(self.nodes[b][1]-self.nodes[a][1])
            result.append(Snap(a,b,f,(lat,lon),error))
        return sorted(result,key=lambda s:(s.error,s.a,s.b))[:count]

    def path(self,start,end,limit=20000):
        if start==end:return [start]
        key=(start,end)
        if key in self.cache:return self.cache[key]
        target=self.nodes[end]
        queue=[(distance(self.nodes[start],target),0,start)]
        costs={start:0};previous={};expanded=0
        while queue:
            _,cost,node=heapq.heappop(queue)
            if cost!=costs[node]:continue
            if node==end:
                result=[end]
                while result[-1]!=start:result.append(previous[result[-1]])
                result.reverse();self.cache[key]=result;return result
            expanded+=1
            if expanded>60000:break
            for neighbor,weight in self.adj.get(node,{}).items():
                new=cost+weight
                if new>limit or new>=costs.get(neighbor,float('inf')):continue
                costs[neighbor]=new;previous[neighbor]=node
                heapq.heappush(queue,(new+distance(self.nodes[neighbor],target),new,neighbor))
        return None

    def connect(self,a: Snap,b: Snap,limit=20000):
        if a.a==b.a and a.b==b.b and b.fraction>=a.fraction:return [a.point,b.point]
        middle=self.path(a.b,b.a,limit)
        if middle is None:return None
        return [a.point]+[self.nodes[n] for n in middle]+[b.point]

    def route(self,start,end,limit=25000):
        best=None
        for a in self.candidates(start):
            for b in self.candidates(end):
                points=self.connect(a,b,limit)
                if not points:continue
                score=length(points)+8*(a.error+b.error)
                if best is None or score<best[0]:best=(score,points,max(a.error,b.error))
        if best is None:raise ValueError('Disconnected road graph')
        return best[1],best[2]

    def match(self,samples):
        # Greedy, GPS-constrained transitions on directed OSM edges. Every
        # returned line segment belongs to the road graph; no gap is bridged.
        reduced=[samples[0]]
        for p in samples[1:-1]:
            if distance(reduced[-1],p)>=35:reduced.append(p)
        reduced.append(samples[-1])
        if len(reduced)<3:return self.route(reduced[0],reduced[-1])
        first=self.candidates(reduced[0]);second=self.candidates(reduced[1])
        best=None
        for a in first:
            for b in second:
                points=self.connect(a,b,max(1500,distance(reduced[0],reduced[1])*5+200))
                if points is None:continue
                score=length(points)+8*(a.error+b.error)
                if best is None or score<best[0]:best=(score,a,b,points)
        if best is None:return self.route(reduced[0],reduced[-1])
        _,_,current,result=best;max_error=max(best[1].error,current.error)
        for index,p in enumerate(reduced[2:],2):
            best=None
            for candidate in self.candidates(p):
                points=self.connect(current,candidate,max(1500,distance(reduced[index-1],p)*6+300))
                if points is None:continue
                score=length(points)+8*candidate.error
                if best is None or score<best[0]:best=(score,candidate,points)
            if best is None:
                # Reject an unmatchable intermediate GPS outlier, not the road.
                if index<len(reduced)-1:continue
                tail,error=self.route(current.point,p)
                result.extend(tail[1:]);max_error=max(max_error,error);break
            _,current,points=best;result.extend(points[1:]);max_error=max(max_error,current.error)
        return result,max_error


def compact(points):
    result=[]
    for p in points:
        p=[round(p[0],6),round(p[1],6)]
        if not result or p!=result[-1]:result.append(p)
    return result if len(result)>1 else result*2
