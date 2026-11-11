"""Local pedestrian graph; coordinates never go to a public routing service."""
import heapq
import math
import struct
from functools import lru_cache
from pathlib import Path


def distance(a,b):return math.hypot((a[0]-b[0])*111000,(a[1]-b[1])*91000)


class WalkingGraph:
    def __init__(self,data):
        self.data=data
        magic,n,m,e,c,g=struct.unpack_from('<4sIIIII',data)
        if magic!=b'APW1':raise ValueError('Invalid pedestrian graph')
        offset=24
        def take(count,code):
            nonlocal offset
            values=memoryview(data)[offset:offset+count*4].cast(code);offset+=count*4;return values
        self.coords=take(n*2,'i');self.offsets=take(n+1,'I');self.neighbors=take(m,'I')
        self.edges=take(e*2,'I');self.cells=take(c*4,'i');self.entries=take(g,'I')
        self.grid={self.cells[i]*1000000+self.cells[i+1]:i for i in range(0,c*4,4)}
        if offset!=len(data):raise ValueError('Unexpected pedestrian graph length')

    def point(self,n):return self.coords[n*2]/1e6,self.coords[n*2+1]/1e6

    @lru_cache(maxsize=8192)
    def snap(self,point):
        x,y=math.floor(point[1]*910),math.floor(point[0]*1110);edges=set()
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                i=self.grid.get((x+dx)*1000000+y+dy)
                if i is not None:edges.update(self.entries[self.cells[i+2]:self.cells[i+2]+self.cells[i+3]])
        best=None
        for edge in edges:
            a,b=self.edges[edge*2:edge*2+2];pa,pb=self.point(a),self.point(b)
            dx,dy=(pb[1]-pa[1])*91000,(pb[0]-pa[0])*111000;den=dx*dx+dy*dy
            if not den:continue
            f=max(0,min(1,((point[1]-pa[1])*91000*dx+(point[0]-pa[0])*111000*dy)/den))
            p=(pa[0]+f*(pb[0]-pa[0]),pa[1]+f*(pb[1]-pa[1]));error=distance(point,p)
            if best is None or (error,edge)<(best['error'],best['edge']):best=dict(a=a,b=b,f=f,point=p,error=error,edge=edge,length=math.sqrt(den))
        return best if best and best['error']<=80 else None

    def connections(self,point,stops,budget,reverse=False):
        candidates=[s for s in stops if distance(point,(s['lat'],s['lon']))<=budget+.01]
        snap=self.snap(point);costs={};parent={};queue=[]
        if snap:
            for node,cost in [(snap['a'],snap['error']+snap['length']*snap['f']),(snap['b'],snap['error']+snap['length']*(1-snap['f']))]:
                if cost<=budget and cost<costs.get(node,float('inf')):costs[node]=cost;parent[node]=None;heapq.heappush(queue,(cost,node))
        while queue:
            cost,node=heapq.heappop(queue)
            if cost!=costs[node]:continue
            a=self.point(node)
            for i in range(self.offsets[node],self.offsets[node+1]):
                other=self.neighbors[i];new=cost+distance(a,self.point(other))
                if new<=budget and new<costs.get(other,float('inf')):
                    costs[other]=new;parent[other]=node;heapq.heappush(queue,(new,other))
        results=[]
        for stop in candidates:
            end=(stop['lat'],stop['lon'])
            if distance(point,end)<.1:
                results.append((stop['id'],0,[list(point),list(end)]));continue
            target=self.snap(end)
            if not snap or not target:continue
            options=[]
            if snap['edge']==target['edge']:
                options.append((snap['error']+abs(snap['f']-target['f'])*snap['length']+target['error'],None))
            for node,extra in [(target['a'],target['length']*target['f']),(target['b'],target['length']*(1-target['f']))]:
                if node in costs:options.append((costs[node]+extra+target['error'],node))
            if not options:continue
            cost,node=min(options,key=lambda x:x[0])
            if cost>budget+.01:continue
            middle=[]
            if node is not None:
                while node is not None:middle.append(self.point(node));node=parent[node]
                middle.reverse()
            points=[point,snap['point'],*middle,target['point'],end]
            compact=[]
            for p in points:
                value=[round(p[0],6),round(p[1],6)]
                if not compact or value!=compact[-1]:compact.append(value)
            if reverse:compact.reverse()
            results.append((stop['id'],round(cost,1),compact))
        return results


@lru_cache(maxsize=1)
def default_graph():return WalkingGraph((Path(__file__).resolve().parents[2]/'shared/walk_graph.bin').read_bytes())


def prepare_locations(network,q,graph):
    points=[];links=[];stops=[s for s in network['stops'] if not s['id'].startswith('@')]
    for kind,value in [('origin',q.origin_point),('destination',q.destination_point)]:
        if value is None:continue
        sid='@'+kind;point=dict(value,id=sid,direction='선택한 지점',isLocation=True);points.append(point)
        for stop,meters,path in graph.connections((value['lat'],value['lon']),stops,q.max_walk,reverse=kind=='destination'):
            links.append({'from':sid if kind=='origin' else stop,'to':stop if kind=='origin' else sid,
                          'meters':meters,'shape':{'points':path,'meters':meters,'source':'osm_pedestrian_access'},'access':True})
    if q.origin_point and q.destination_point:
        for _,meters,path in graph.connections((q.origin_point['lat'],q.origin_point['lon']),[dict(q.destination_point,id='@destination')],q.max_walk):
            links.append({'from':'@origin','to':'@destination','meters':meters,'shape':{'points':path,'meters':meters,'source':'osm_pedestrian_access'},'access':True})
    return dict(network,stops=stops+points,footpaths=network.get('footpaths',[])+links),points
