from app.engine import Engine, Query


def network(stops, routes):
    return {'stops':[{'id':s} for s in stops], 'routes':[
        dict(id=rid,stops=path,offsets=offsets,departures=trips,delaySamples=delays)
        for rid,path,offsets,trips,delays in routes], 'footpaths':[]}


def test_express_transfer_can_reboard_an_earlier_trip_of_the_first_route():
    data=network(['o','u','v','d'],[
        ('A',['o','u','v','d'],[0,10,40,60],[20,40],[0]),
        ('B',['u','v'],[0,1],[51],[0])])
    rows=Engine(data).search(Query('o','d',departure=25,max_walk=0,walking_penalty=1,max_transfers=2))
    fastest=next(j for j in rows if 'ANY%' in j['tags'])
    assert fastest['arrival']==80
    assert [(l['routeId'],l['trip']) for l in fastest['legs']]==[('A',40),('B',51),('A',20)]


def test_protected_candidates_preserve_a_safer_later_prefix():
    data=network(['o','x','y','h','d'],[
        ('A',['o','x'],[0,5],[5],[0,4]),
        ('B',['x','h'],[0,5],[10.5,70.5],[0]),
        ('C',['o','y'],[0,2],[5],[0]),
        ('D',['y','h'],[0,6],[13.5],[0]),
        ('E',['h','d'],[0,5],[26,86],[0])])
    rows=Engine(data).search(Query('o','d',departure=0,max_walk=0,walking_penalty=1,max_transfers=2))
    safer=next(j for j in rows if 'SAFE' in j['tags'])
    assert [l['routeId'] for l in safer['legs']]==['C','D','E']
    assert safer['p90Arrival']==31
    risky=next(j for j in rows if [l['routeId'] for l in j['legs']]==['A','B','E'])
    assert risky['p90Arrival']==91
