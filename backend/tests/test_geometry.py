import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'tools'))
from app.geometry import point_along
from local_roads import RoadGraph


def test_local_graph_follows_a_bridge_instead_of_drawing_across_water():
    data={'nodes':{'1':[35.50,129.30],'2':[35.50,129.31],'3':[35.51,129.31],'4':[35.51,129.30]},
          'ways':[{'id':1,'pairs':[[1,2],[2,3],[3,4]],'drive':True,'foot':True,'oneway':'yes'}]}
    graph=RoadGraph(data)
    road,_=graph.route([35.50,129.30],[35.51,129.30])
    assert (35.50,129.31) in road and (35.51,129.31) in road
    assert graph.path(4,1) is None
    middle=point_along(road,.5)
    assert middle[1]==pytest.approx(129.31)
    assert point_along([], .5) is None


def test_demo_has_road_geometry_and_true_walk_length():
    network=json.loads((ROOT/'shared/network.json').read_text(encoding='utf-8'))
    assert network['geometryVersion']=='local-osm-1'
    for route in network['routes']:
        assert len(route['shapeSegments'])==len(route['stops'])-1
        assert all(len(shape['points'])>2 for shape in route['shapeSegments'])
    a=next(r for r in network['routes'] if r['id']=='demo-a')
    assert a['shapeSegments'][1]['source']=='gps_road_matched'
    assert a['shapeSegments'][1]['referenceRoute']=='194001240'
    assert len(a['shapeSegments'][1]['points'])>100
    walk=network['footpaths'][0]
    assert walk['meters']==walk['shape']['meters']
