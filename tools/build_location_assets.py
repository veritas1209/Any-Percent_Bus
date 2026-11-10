"""Create local place search and a compact pedestrian graph from the public OSM extract."""
import array
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
raw=json.loads((ROOT/'tmp/ulsan-all-roads.json').read_text(encoding='utf-8'))
edges=sorted({tuple(sorted((a,b))) for w in raw['ways'] if w['foot'] for a,b in w['pairs']})
ids=sorted({n for edge in edges for n in edge});lookup={n:i for i,n in enumerate(ids)}
coordinates=[raw['nodes'][str(n)] for n in ids]
offsets=array.array('I',[0])*(len(ids)+1)
for a,b in edges:offsets[lookup[a]+1]+=1;offsets[lookup[b]+1]+=1
for i in range(len(ids)):offsets[i+1]+=offsets[i]
neighbors=array.array('I',[0])*offsets[-1];cursor=array.array('I',offsets)
edge_indices=array.array('I');grid=defaultdict(list)
for index,(a,b) in enumerate(edges):
    a,b=lookup[a],lookup[b];edge_indices.extend((a,b))
    neighbors[cursor[a]]=b;cursor[a]+=1;neighbors[cursor[b]]=a;cursor[b]+=1
    ay,ax=coordinates[a];by,bx=coordinates[b]
    for x in range(math.floor(min(ax,bx)*910),math.floor(max(ax,bx)*910)+1):
        for y in range(math.floor(min(ay,by)*1110),math.floor(max(ay,by)*1110)+1):grid[x,y].append(index)
cells=array.array('i');entries=array.array('I')
for (x,y),values in sorted(grid.items()):cells.extend((x,y,len(entries),len(values)));entries.extend(values)
coords=array.array('i',[round(v*1e6) for p in coordinates for v in p])
data=bytearray(struct.pack('<4sIIIII',b'APW1',len(ids),len(neighbors),len(edges),len(grid),len(entries)))
for values in (coords,offsets,neighbors,edge_indices,cells,entries):data.extend(values.tobytes())
for target in (ROOT/'shared/walk_graph.bin',ROOT/'app/assets/data/walk_graph.bin'):target.write_bytes(data)
print('WALK',len(ids),len(edges),len(grid),len(data),'bytes',flush=True)
del raw,coordinates,edges,ids,lookup,offsets,neighbors,cursor,grid,entries,coords,edge_indices,cells,data

import osmium
places=[]
def collect(kind,ident,tags,lat,lon):
    if not (35.2<=lat<=35.85 and 128.85<=lon<=129.60):return
    name=tags.get('name:ko') or tags.get('name')
    address=tags.get('addr:full') or ' '.join(dict.fromkeys(tags.get(k,'') for k in ('addr:city','addr:suburb','addr:street','addr:housenumber') if tags.get(k)))
    if not name and not (tags.get('addr:street') and tags.get('addr:housenumber')):return
    if tags.get('highway') and not tags.get('amenity') and not tags.get('public_transport'):return
    category='장소'
    if tags.get('amenity') in ('school','university','college','kindergarten'):category='학교'
    elif tags.get('shop'):category='상점'
    elif tags.get('amenity') in ('restaurant','cafe','fast_food'):category='음식점'
    elif tags.get('leisure'):category='공원·시설'
    elif not name:category='주소'
    places.append({'id':f'osm:{kind}{ident}','name':name or address,'address':address,'kind':category,
                   'lat':round(lat,7),'lon':round(lon,7),'searchText':' '.join(str(tags.get(k,'')) for k in ('name','name:ko','alt_name','brand','addr:full','addr:city','addr:suburb','addr:street','addr:housenumber'))})

class Places(osmium.SimpleHandler):
    def node(self,n):collect('n',n.id,dict(n.tags),n.location.lat,n.location.lon)
    def way(self,w):
        tags=dict(w.tags)
        if not tags.get('name') and not tags.get('name:ko') and not tags.get('addr:housenumber'):return
        if tags.get('highway'):return
        points=[(n.lat,n.lon) for n in w.nodes if n.location.valid()]
        if points:collect('w',w.id,tags,sum(p[0] for p in points)/len(points),sum(p[1] for p in points)/len(points))

Places().apply_file(str(ROOT/'tmp/gyeongsang.osm.pbf'),locations=True)
result={'version':'osm-local-1','attribution':'© OpenStreetMap contributors / OSM Korea','places':places}
encoded=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8')
for target in (ROOT/'shared/places.json',ROOT/'app/assets/data/places.json'):target.write_bytes(encoded)
report={'source':'https://tiles.osm.kr/download/gyeongsang-non-military.osm.pbf','placeCount':len(places),
        'walkGraphSha256':hashlib.sha256((ROOT/'shared/walk_graph.bin').read_bytes()).hexdigest(),
        'placesSha256':hashlib.sha256(encoded).hexdigest(),'note':'Local public OSM place/address index; not a complete commercial geocoder or verified entrance database.'}
(ROOT/'artifacts/location-assets.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('PLACES',len(places),flush=True)
