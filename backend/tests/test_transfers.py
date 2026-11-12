import json
import struct
import array
from app.engine import Engine,Query
from app.transfers import TransferGraph
from pathlib import Path
import pytest


def line_graph(meters):
    meta=json.dumps({'stopIds':['p','q']}).encode();meta+=b' '*((-len(meta))%8)
    data=bytearray(struct.pack('<4sIIIII',b'APX1',2,2,2,len(meta),0)+meta)
    for code,values in [('I',[0,1,2]),('I',[1,0]),('i',[0,1])]:data.extend(array.array(code,values).tobytes())
    data.extend(b' '*((-len(data))%8))
    for values in ([meters,meters],[0,0]):data.extend(array.array('d',values).tobytes())
    return TransferGraph(bytes(data))


def test_transfer_longer_than_five_kilometers_is_scored_instead_of_excluded():
    class Walks:
        def connections(self,point,stops,budget):
            return [(stops[0]['id'],6000,[[35,129],[35.05,129]])]
    data={'stops':[{'id':s,**({'lat':35,'lon':129} if s in ('p','q') else {})} for s in ('o','p','q','d')],
      'routes':[
        dict(id='A',stops=['o','p'],departures=[5],offsets=[0,5],delaySamples=[0]),
        dict(id='B',stops=['q','d'],departures=[110],offsets=[0,5],delaySamples=[0]),
        dict(id='direct',stops=['o','d'],departures=[5],offsets=[0,195],delaySamples=[0])], 'footpaths':[]}
    engine=Engine(data,Walks(),line_graph(6000))
    def search(penalty):return engine.search(Query('o','d',departure=0,max_walk=None,walking_penalty=penalty,max_transfers=1,samples=20))
    less=search(2);willing=search(.25)
    assert less[0]['walkingMeters']==0
    assert willing[0]['walkingMeters']==6000
    assert next(j for j in less if 'ANY%' in j['tags'])['arrival']==115
    assert any(l.get('shape',{}).get('source')=='pedestrian_transfer' for l in willing[0]['legs'])
    assert all('_transferWalk' not in l for j in willing for l in j['legs'])
    finite=engine.search(Query('o','d',departure=0,max_walk=5000,walking_penalty=.25,max_transfers=1,samples=20))
    assert all(j['walkingMeters']==0 for j in finite)


def test_multisource_walk_keeps_both_arrival_and_walking_alternatives():
    graph=line_graph(600)
    roots=[('p',0,[],set(),0),('q',5,[],set(),1000)]
    rows=graph.spread(roots,1.2,10000,boardable={'q'})
    q=[row for row in rows if row[0]=='q']
    assert {(round(row[1],3),row[4]) for row in q}=={(5,1000),(8.333,600)}


@pytest.mark.parametrize('origin,destination,budget',[
    ('193031109','193040404',4000),('193031109','193012313',8000),('195040328','193012313',15000)])
def test_contraction_matches_independent_uncontracted_pedestrian_paths(origin,destination,budget):
    from app.walking import WalkingGraph
    root=Path(__file__).resolve().parents[2]
    data=json.loads((root/'shared/service_network.json').read_text(encoding='utf-8'))
    stops={s['id']:s for s in data['stops']}
    raw=WalkingGraph((root/'shared/walk_graph.bin').read_bytes())
    graph=TransferGraph((root/'shared/transfer_graph.bin').read_bytes())
    a=stops[origin];expected=raw.connections((a['lat'],a['lon']),[stops[destination]],budget)
    assert expected
    rows=graph.spread([(origin,0,[],set(),0)],1.2,budget,boardable={destination})
    found=min(row[4] for row in rows if row[0]==destination)
    assert found==pytest.approx(expected[0][1],abs=.11)
