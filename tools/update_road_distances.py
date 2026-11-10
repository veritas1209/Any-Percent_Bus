"""Use available pedestrian road lengths, preserving the synthetic demo's comparison arrival times."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
for name in ('network.json','observed_network.json'):
    network=json.loads((ROOT/'shared'/name).read_text(encoding='utf-8'))
    old_demo_walk=next((p['meters'] for p in network['footpaths'] if p['from']=='station' and p['to']=='station-b'),None)
    available=[]
    for path in network['footpaths']:
        shape=path.get('shape',{})
        if not shape.get('points'):continue
        path['meters']=max(1,round(shape['meters'],1));path['source']='osm_road_estimate';available.append(path)
    network['footpaths']=available
    if old_demo_walk is not None:
        new=next(p['meters'] for p in available if p['from']=='station' and p['to']=='station-b')
        route=next(r for r in network['routes'] if r['id']=='demo-b')
        old=route.get('walkCalibrationMeters',old_demo_walk)
        delta=(new-old)/1.2/60
        route['departures']=[d+delta for d in route['departures']]
        route['offsets']=[0]+[o-delta for o in route['offsets'][1:]]
        route['walkCalibrationMeters']=new
    network['description']=network['description'].replace('보행거리는 기하 추정','보행거리는 OSM 도로망 추정')
    for path in (ROOT/'shared'/name,ROOT/'app/assets/data'/name):
        path.write_text(json.dumps(network,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('ROAD_DISTANCES',name,len(available),'walking links')
