"""Schedule-free route connections. Never manufacture arrival times or probabilities."""
from collections import defaultdict


def reachable(routes,footpaths,destination,rides,max_walk):
    incoming=defaultdict(list)
    for f in footpaths:
        if f['meters']<=max_walk:incoming[f['to']].append(f['from'])
    layer={destination,*incoming[destination]};layers=[layer]
    for _ in range(rides):
        boardable=set(layer)
        for r in routes:
            downstream=False
            for sid in reversed(r['stops']):
                if downstream:boardable.add(sid)
                if sid in layer:downstream=True
        layer=boardable|{a for b in boardable for a in incoming[b]}
        layers.append(layer)
    return layers


def labels(states):
    kept=defaultdict(list)
    # A prior label dominates only when it also forbids no additional routes.
    for state in sorted(states,key=lambda x:(x[1],x[4])):
        stop,now,legs,used,walked=state
        if any(t<=now and w<=walked and u<=used for t,w,u in kept[stop]):continue
        kept[stop].append((now,walked,used))
        yield state


def connections(network,q):
    routes=[r for r in network['routes'] if r.get('scheduleSource')=='catalog_topology']
    walks=defaultdict(list);boards=defaultdict(list)
    for f in network['footpaths']:walks[f['from']].append(f)
    for r in routes:
        for bi,sid in enumerate(r['stops'][:-1]):boards[sid].append((r,bi))
    layers=reachable(routes,network['footpaths'],q.destination,q.max_transfers+1,q.max_walk)
    frontier=[(q.origin,0,[],set(),0.0)]
    for round in range(q.max_transfers+1):
        following=[];found={};remaining=q.max_transfers-round
        for stop,cost,legs,used,walked in frontier:
            accesses=[(stop,cost,[],walked)]
            for f in walks[stop]:
                if walked+f['meters']<=q.max_walk:
                    accesses.append((f['to'],cost+f['meters']*2,[dict(kind='walk',from_=stop,to=f['to'],meters=f['meters'])],walked+f['meters']))
            for board,access_cost,walk_legs,total_walk in accesses:
                for r,bi in boards[board]:
                    if r['id'] in used:continue
                    offsets=r.get('distanceOffsets')
                    if offsets is None:offsets=list(range(len(r['stops'])))
                    for ai in range(bi+1,len(r['stops'])):
                        end=r['stops'][ai]
                        if end not in layers[remaining]:continue
                        newcost=access_cost+offsets[ai]-offsets[bi]
                        leg=dict(kind='ride',routeId=r['id'],from_=board,to=end,boardIndex=bi,alightIndex=ai)
                        newlegs=legs+walk_legs+[leg]
                        tails=[([],total_walk,newcost)] if end==q.destination else [
                            ([dict(kind='walk',from_=end,to=q.destination,meters=f['meters'])],total_walk+f['meters'],newcost+f['meters']*2)
                            for f in walks[end] if f['to']==q.destination and total_walk+f['meters']<=q.max_walk]
                        for tail,budget,score in tails:
                            full=[dict(l,**{'from':l['from_']}) for l in newlegs+tail]
                            for l in full:l.pop('from_',None)
                            key='|'.join(f"{l.get('routeId','walk')}:{l['from']}:{l['to']}" for l in full)
                            found.setdefault(key,dict(id=key,legs=full,arrival=None,walkingMeters=budget,transfers=round,
                                tags=['ROUTE'],source='catalog_topology',scheduleAvailable=False,topologyCost=score,
                                expectedArrival=None,p90Arrival=None,successProbability=None,noServiceProbability=None,
                                sampleCount=0,delaySource='unavailable'))
                        if remaining:following.append((end,newcost,newlegs,used|{r['id']},total_walk))
        if found:return sorted(found.values(),key=lambda j:(j['topologyCost'],j['walkingMeters']))[:5]
        frontier=list(labels(following))
    return []
