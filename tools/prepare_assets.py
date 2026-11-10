"""Copy shared fixtures, archive BusTracker static topology, verify provenance. No source mutations."""
import csv
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('C:/Users/hajin/공부/울산과학대학교/3학년_1학기/2026일경험/bustracker')
target=ROOT/'app/assets/data/network.json'
target.parent.mkdir(parents=True,exist_ok=True)
for name in ('network.json','observed_network.json','places.json','walk_graph.bin'):
    shutil.copyfile(ROOT/'shared'/name,target.parent/name)
# Preserve raw catalog separately; reconstructed loops are not blindly treated as directional runs.
if SOURCE.exists():
    names={r['route_id']:r for r in csv.DictReader((SOURCE/'route_names_manual.csv').open(encoding='utf-8-sig'))}
    routes={};stops={}
    for row in csv.DictReader((SOURCE/'route_stops_named.csv').open(encoding='utf-8-sig')):
        rid,sid=row['route_id'],row['spot_id']
        meta=names.get(rid,{})
        route=routes.setdefault(rid,{'id':rid,'number':meta.get('route_no',''),'stops':[]})
        route['stops'].append({'stopId':sid,'sequence':int(row['spot_seq'])})
        stops.setdefault(sid,{'id':sid,'name':row['stop_name'],'lat':float(row['lat']),'lon':float(row['lon'])})
    catalog={'source':'bustracker_csv','routes':list(routes.values()),'stops':list(stops.values()),'warning':'구간 누락·중복·방향 혼합 가능. 시간표 없음.'}
    dest=ROOT/'shared/bustracker_catalog.json'
    dest.write_text(json.dumps(catalog,ensure_ascii=False),encoding='utf-8')
    print('Catalog',len(routes),'routes',len(stops),'stop IDs')
print('Assets prepared:',target)
