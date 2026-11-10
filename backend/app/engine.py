"""Timetable routing and journey-level reliability. All timestamps are minutes in service day."""
from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    origin: str
    destination: str
    departure: float = 540
    walking_speed: float = 1.2
    max_walk: float = 500
    max_transfers: int = 2
    delay: float = 0
    samples: int = 300
    seed: int = 42


def quantile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered)-1, math.ceil(len(ordered)*q)-1)]


class Engine:
    def __init__(self, network):
        self.network = network
        self.stops = {s['id']: s for s in network['stops']}
        self.routes = {r['id']: r for r in network['routes']}

    def search(self, q: Query):
        if q.origin not in self.stops or q.destination not in self.stops:
            raise ValueError('존재하지 않는 정류장입니다.')
        if q.origin == q.destination:
            return []
        frontier = [(q.origin, q.departure, [], set(), 0.0)]
        found = {}
        def add(legs,walked):
            key='|'.join(f"{l.get('routeId','walk')}:{l['from']}:{l['to']}" for l in legs)
            found.setdefault(key,{'id':key,'legs':legs,'arrival':legs[-1]['arrive'],'walkingMeters':walked})
        for f in self.network.get('footpaths',[]):
            if f['from']==q.origin and f['to']==q.destination and f['meters']<=q.max_walk:
                add([{'kind':'walk','from':q.origin,'to':q.destination,'depart':q.departure,'arrive':q.departure+f['meters']/q.walking_speed/60,'meters':f['meters']}],f['meters'])
        for _ in range(q.max_transfers+1):
            next_frontier = []
            for stop, now, legs, used, walked in frontier:
                accesses = [(stop, now, [], walked)]
                for f in self.network.get('footpaths', []):
                    if f['from'] == stop and walked+f['meters'] <= q.max_walk:
                        end = now+f['meters']/q.walking_speed/60
                        accesses.append((f['to'], end, [{'kind':'walk','from':stop,'to':f['to'],'depart':now,'arrive':end,'meters':f['meters']}],walked+f['meters']))
                for board, ready, walk_legs, total_walk in accesses:
                    for r in self.routes.values():
                        if r['id'] in used or board not in r['stops']:
                            continue
                        bi = r['stops'].index(board)
                        buffer = 0.5 if used else 0
                        trip = next((d for d in r['departures'] if d+r['offsets'][bi] >= ready+buffer), None)
                        if trip is None:
                            continue
                        for ai in range(bi+1,len(r['stops'])):
                            endstop = r['stops'][ai]
                            leg = {'kind':'ride','routeId':r['id'],'from':board,'to':endstop,'boardIndex':bi,'alightIndex':ai,'trip':trip,'depart':trip+r['offsets'][bi],'arrive':trip+r['offsets'][ai]}
                            newlegs = legs+walk_legs+[leg]
                            if endstop == q.destination:
                                add(newlegs,total_walk)
                            else:
                                for f in self.network.get('footpaths',[]):
                                    if f['from']==endstop and f['to']==q.destination and total_walk+f['meters']<=q.max_walk:
                                        last={'kind':'walk','from':endstop,'to':q.destination,'depart':leg['arrive'],'arrive':leg['arrive']+f['meters']/q.walking_speed/60,'meters':f['meters']}
                                        add(newlegs+[last],total_walk+f['meters'])
                                next_frontier.append((endstop,leg['arrive'],newlegs,used|{r['id']},total_walk))
            # Keep alternatives by route sequence, not just earliest label: late safe journeys matter.
            frontier = sorted(next_frontier,key=lambda x:x[1])[:500]
        candidates = sorted(found.values(), key=lambda j:j['arrival'])[:20]
        evaluated = [self.evaluate(j,q) for j in candidates]
        if not evaluated:
            return []
        any_id = min(evaluated,key=lambda j:j['arrival'])['id']
        safe_id = min(evaluated,key=lambda j:(j['p90Arrival'],j['expectedArrival']))['id']
        for j in evaluated:
            j['tags'] = (['ANY%'] if j['id']==any_id else [])+(['SAFE'] if j['id']==safe_id else [])
        return sorted(evaluated,key=lambda j:(not j['tags'],j['arrival']))

    def replay(self, journey, q, draws=None):
        now = q.departure
        missed = []
        result = []
        first = True
        margin = None
        for source_leg in journey['legs']:
            leg = dict(source_leg)
            leg['depart'] = now
            if leg['kind']=='walk':
                now += leg['meters']/q.walking_speed/60
            else:
                r = self.routes[leg['routeId']]
                bi, ai = leg['boardIndex'],leg['alightIndex']
                # A scenario delay belongs to a vehicle trip and is shared by every stop on it.
                selected = None
                for trip in r['departures']:
                    if first and trip < leg['trip']:
                        continue
                    d = (draws or {}).get((r['id'],trip),0)
                    extra = q.delay if first and trip==leg['trip'] else 0
                    depart = trip+r['offsets'][bi]+d+extra
                    if depart >= now+(0 if first else 0.5):
                        selected = (trip, depart, trip+r['offsets'][ai]+d+extra)
                        break
                if selected is None:
                    return {'arrival':None,'missed':missed+[leg['routeId']],'legs':result,'margin':margin}
                trip, depart, arrive = selected
                if not first:
                    slack = depart-now-0.5
                    margin = slack if margin is None else min(margin,slack)
                    if trip > leg['trip']:
                        missed.append(leg['routeId'])
                leg.update(trip=trip,depart=depart)
                now = arrive
                first = False
            leg['arrive'] = now
            result.append(leg)
        return {'arrival':now,'missed':missed,'legs':result,'margin':margin}

    def evaluate(self, journey, q):
        j = copy.deepcopy(journey)
        baseline = self.replay(j,q)
        arrivals = []; successes = 0; no_service = 0
        rng = random.Random(q.seed)
        for _ in range(q.samples):
            draws = {(r['id'],trip): rng.choice(r['delaySamples']) for r in self.routes.values() for trip in r['departures']}
            sample = self.replay(j,q,draws)
            if sample['arrival'] is None:
                no_service += 1
            else:
                arrivals.append(sample['arrival'])
            if not sample['missed'] and sample['arrival'] is not None:
                successes += 1
        # No-service outcomes cannot silently disappear from a quantile or expected value.
        censored = arrivals + [max(q.departure+240,1440)]*no_service
        j.update(expectedArrival=sum(censored)/len(censored),p90Arrival=quantile(censored,.9),successProbability=successes/q.samples,
                 sampleCount=q.samples,noServiceProbability=no_service/q.samples,source=self.network.get('source','simulated'),delaySource='simulated',scenario=baseline,
                 statisticsIncludeFailurePenalty=no_service>0,failurePenaltyArrival=max(q.departure+240,1440) if no_service else None,
                 transfers=max(0,sum(l['kind']=='ride' for l in j['legs'])-1),
                 missPenalty=None if baseline['arrival'] is None else max(0,baseline['arrival']-j['arrival']))
        return j
