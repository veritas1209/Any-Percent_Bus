"""Timetable routing and journey-level reliability. All timestamps are minutes in service day."""
from __future__ import annotations

import copy
import math
import random
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass,replace
from .topology import connections,reachable,labels,walking_bounds,latest_departures


@dataclass(frozen=True)
class Query:
    origin: str
    destination: str
    departure: float = 540
    walking_speed: float = 1.2
    max_walk: float | None = 500
    max_transfers: int = 2
    delay: float = 0
    samples: int = 300
    seed: int = 42
    origin_point: dict | None = None
    destination_point: dict | None = None
    service_day: str = 'weekday'
    walking_penalty: float | None = None


def quantile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered)-1, math.ceil(len(ordered)*q)-1)]


class SampleDelays:
    """Draw a trip's delay when the simulation first reaches that trip."""
    def __init__(self, routes, rng):
        self.routes = routes
        self.rng = rng
        self.values = {}

    def get(self, key, default=0):
        if key not in self.values:
            self.values[key] = self.rng.choice(self.routes[key[0]]['delaySamples'])
        return self.values[key]


class Engine:
    def __init__(self, network,walking_graph=None):
        self.network = network
        self.walking_graph=walking_graph
        self.day_engines = {}
        self.stops = {s['id']: s for s in network['stops']}
        self.routes = {r['id']: r for r in network['routes']}
        self.timed_routes=[r for r in self.routes.values() if r['departures']]
        self.boardings=defaultdict(list);self.walks=defaultdict(list)
        for r in self.timed_routes:
            for bi,sid in enumerate(r['stops'][:-1]):self.boardings[sid].append((r,bi))
        for f in network.get('footpaths',[]):self.walks[f['from']].append(f)

    def _search_unlimited(self, q):
        from .walking import default_graph, prepare_locations
        penalty = 1.0 if q.walking_penalty is None else q.walking_penalty
        origin = q.origin_point or self.stops.get(q.origin)
        destination = q.destination_point or self.stops.get(q.destination)
        if not origin or not destination:
            raise ValueError('존재하지 않는 정류장입니다.')
        if 'lat' not in origin or 'lat' not in destination:
            return self.search(replace(q, max_walk=float('inf'), walking_penalty=penalty))
        q = replace(q, origin_point=origin, destination_point=destination, walking_penalty=penalty)
        graph = self.walking_graph or default_graph()
        radius = 2000.0
        fallback = []
        while True:
            stats = {}
            limited = replace(q, max_walk=radius)
            network, places = prepare_locations(self.network, limited, graph, stats)
            prepared = replace(limited, origin='@origin', destination='@destination', origin_point=None, destination_point=None)
            rows = Engine(network).search(prepared)
            for row in rows:
                row['places'] = places
            timed = [row for row in rows if row['arrival'] is not None]
            if timed:
                fastest = min(row['arrival'] for row in timed) - q.departure
                recommended = min(row['recommendationScore'] for row in timed)
                sufficient = max(fastest, recommended / (1 + penalty)) * q.walking_speed * 60
                if radius + .01 >= sufficient:
                    return timed
                next_radius = sufficient + .1
            else:
                fallback = rows or fallback
                next_radius = radius * 2
            if stats['exhausted']:
                return timed or fallback
            radius = next_radius

    def search(self, q: Query):
        if self.network.get('timetableDays') and q.service_day != self.network.get('serviceDay', 'weekday'):
            if q.service_day not in self.day_engines:
                routes = [dict(r, departures=r['departuresByDay'].get(q.service_day, [])) for r in self.network['routes']]
                self.day_engines[q.service_day] = Engine(dict(self.network, routes=routes, serviceDay=q.service_day), self.walking_graph)
            return self.day_engines[q.service_day].search(q)
        if q.max_walk is None:
            return self._search_unlimited(q)
        if q.origin_point is not None or q.destination_point is not None:
            from .walking import default_graph,prepare_locations
            augmented,places=prepare_locations(self.network,q,self.walking_graph or default_graph())
            prepared=replace(q,origin='@origin' if q.origin_point else q.origin,destination='@destination' if q.destination_point else q.destination,origin_point=None,destination_point=None)
            rows=Engine(augmented).search(prepared)
            for j in rows:j['places']=places
            return rows
        if q.origin not in self.stops or q.destination not in self.stops:
            raise ValueError('존재하지 않는 정류장입니다.')
        if q.origin == q.destination:
            return []
        frontier = [(q.origin, q.departure, [], set(), 0.0)]
        layers=reachable(self.timed_routes,self.network.get('footpaths',[]),q.destination,q.max_transfers+1,q.max_walk)
        bounds=walking_bounds(self.timed_routes,self.network.get('footpaths',[]),q.destination,q.max_transfers+1)
        found = {}
        cutoff=float('inf')
        arrival_cutoff = score_cutoff = float('inf')
        scored = q.walking_penalty is not None
        latest = None
        def rank(j):
            return j['arrival'], j['walkingMeters'], sum(leg['kind'] == 'ride' for leg in j['legs'])

        def competitive(now, walked, rides, remaining, stop):
            least_walk = walked + bounds[remaining].get(stop, float('inf'))
            optimistic = now - q.departure + least_walk / q.walking_speed / 60 * q.walking_penalty + max(0, rides - 1) * 3
            return now <= arrival_cutoff + 1e-6 or optimistic <= score_cutoff + 1e-6

        def add(legs,walked):
            nonlocal cutoff, arrival_cutoff, score_cutoff
            key='|'.join(f"{l.get('routeId','walk')}:{l['from']}:{l['to']}" for l in legs)
            candidate = {'id':key,'legs':legs,'arrival':legs[-1]['arrive'],'walkingMeters':walked}
            if scored:
                candidate['recommendationScore'] = candidate['arrival'] - q.departure + walked / q.walking_speed / 60 * q.walking_penalty + max(0, sum(leg['kind'] == 'ride' for leg in legs) - 1) * 3
            if key in found and rank(found[key]) <= rank(candidate):
                return
            found[key] = candidate
            if len(found)>20:
                keep = set(sorted(found, key=lambda key: rank(found[key]))[:20])
                if scored:
                    keep.add(min(found, key=lambda key: (found[key]['recommendationScore'], rank(found[key]))))
                for k in list(found):
                    if k not in keep:del found[k]
            if len(found) >= 20:
                arrival_cutoff = sorted(found.values(), key=rank)[19]['arrival']
                score_cutoff = min(row['recommendationScore'] for row in found.values()) if scored else float('inf')
                cutoff = max(arrival_cutoff, q.departure + score_cutoff) if scored else arrival_cutoff
        for f in self.walks[q.origin]:
            if f['from']==q.origin and f['to']==q.destination and f['meters']<=q.max_walk:
                add([{'kind':'walk','from':q.origin,'to':q.destination,'depart':q.departure,'arrive':q.departure+f['meters']/q.walking_speed/60,'meters':f['meters'],'shape':f.get('shape')}],f['meters'])
        for round in range(q.max_transfers+1):
            next_frontier = []
            for stop, now, legs, used, walked in frontier:
                if now>cutoff:continue
                if scored and not competitive(now, walked, len(used), q.max_transfers-round+1, stop):continue
                if latest is not None and now > latest[q.max_transfers-round+1].get(stop, -float('inf')) + 1e-6:
                    continue
                if walked+bounds[q.max_transfers-round+1].get(stop,float('inf'))>q.max_walk+.001:continue
                accesses = [(stop, now, [], walked)]
                for f in self.walks[stop]:
                    if f['from'] == stop and walked+f['meters'] <= q.max_walk:
                        end = now+f['meters']/q.walking_speed/60
                        accesses.append((f['to'], end, [{'kind':'walk','from':stop,'to':f['to'],'depart':now,'arrive':end,'meters':f['meters'],'shape':f.get('shape')}],walked+f['meters']))
                for board, ready, walk_legs, total_walk in accesses:
                    if scored and not competitive(ready, total_walk, len(used), q.max_transfers-round+1, board):continue
                    if latest is not None and ready > latest[q.max_transfers-round+1].get(board, -float('inf')) + 1e-6:
                        continue
                    for r,bi in self.boardings[board]:
                        if r['id'] in used:
                            continue
                        buffer = 0.5 if used else 0
                        index = bisect_left(r['departures'], ready + buffer - r['offsets'][bi] - 1e-9)
                        if index == len(r['departures']):
                            continue
                        trip = r['departures'][index]
                        for ai in range(bi+1,len(r['stops'])):
                            if trip+r['offsets'][ai]>cutoff:continue
                            endstop = r['stops'][ai]
                            if scored and not competitive(trip+r['offsets'][ai], total_walk, len(used)+1, q.max_transfers-round, endstop):continue
                            if latest is not None and trip+r['offsets'][ai] > latest[q.max_transfers-round].get(endstop, -float('inf')) + 1e-6:
                                continue
                            if endstop not in layers[q.max_transfers-round]:continue
                            if total_walk+bounds[q.max_transfers-round].get(endstop,float('inf'))>q.max_walk+.001:continue
                            leg = {'kind':'ride','routeId':r['id'],'from':board,'to':endstop,'boardIndex':bi,'alightIndex':ai,'trip':trip,'depart':trip+r['offsets'][bi],'arrive':trip+r['offsets'][ai]}
                            newlegs = legs+walk_legs+[leg]
                            if endstop == q.destination:
                                add(newlegs,total_walk)
                            else:
                                for f in self.walks[endstop]:
                                    if f['from']==endstop and f['to']==q.destination and total_walk+f['meters']<=q.max_walk:
                                        last={'kind':'walk','from':endstop,'to':q.destination,'depart':leg['arrive'],'arrive':leg['arrive']+f['meters']/q.walking_speed/60,'meters':f['meters'],'shape':f.get('shape')}
                                        add(newlegs+[last],total_walk+f['meters'])
                                if round<q.max_transfers:
                                    next_frontier.append((endstop,leg['arrive'],newlegs,used|{r['id']},total_walk))
            # Keep alternatives by route sequence, not just earliest label: late safe journeys matter.
            if round < q.max_transfers:
                remaining = q.max_transfers - round
                latest = latest_departures(
                    self.timed_routes, self.network.get('footpaths', []), q.destination,
                    remaining, cutoff, q.walking_speed,
                ) if math.isfinite(cutoff) else None
                frontier = list(labels(
                    state for state in next_frontier if state[1] <= cutoff and
                    (latest is None or state[1] <= latest[remaining].get(state[0], -float('inf')) + 1e-6)
                ))
        candidates = sorted(found.values(), key=rank)
        evaluated = [self.evaluate(j,q) for j in candidates]
        if not evaluated:
            return connections(self.network,q) if self.network.get('catalogFallback') else []
        if scored:
            single_rides = {}
            alternatives = []
            for journey in evaluated:
                rides = [leg for leg in journey['legs'] if leg['kind'] == 'ride']
                if len(rides) != 1:
                    alternatives.append(journey)
                    continue
                ride = rides[0]
                key = ride['routeId'], ride['trip'], ride['alightIndex']
                if key not in single_rides or rank(journey) < rank(single_rides[key]):
                    single_rides[key] = journey
            evaluated = alternatives + list(single_rides.values())
        any_id = min(evaluated,key=rank)['id']
        safe_id = min(evaluated,key=lambda j:(j.get('safeScore',j['p90Arrival']),j['expectedArrival'],j['walkingMeters']))['id']
        recommended_id = min(evaluated,key=lambda j:(j['recommendationScore'],rank(j)))['id'] if scored else None
        for j in evaluated:
            j['tags'] = (['추천'] if j['id']==recommended_id else [])+(['ANY%'] if j['id']==any_id else [])+(['SAFE'] if j['id']==safe_id else [])
        return sorted(evaluated, key=lambda j: (j['recommendationScore'],rank(j))) if scored else sorted(evaluated,key=lambda j:(not j['tags'],rank(j)))

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
                maximum_delay = max(r['delaySamples']) if draws is not None else 0
                earliest_trip = now + (0 if first else .5) - r['offsets'][bi] - maximum_delay - (q.delay if first else 0)
                start = bisect_left(r['departures'], earliest_trip - 1e-9)
                for trip in r['departures'][start:]:
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
        relevant={l['routeId'] for l in j['legs'] if l['kind']=='ride'}
        for _ in range(q.samples):
            draws = SampleDelays(self.routes, rng) if self.network.get('dataset') == 'service' else {
                (rid, trip): rng.choice(self.routes[rid]['delaySamples'])
                for rid in sorted(relevant) for trip in self.routes[rid]['departures']
            }
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
                 scheduleAvailable=True,transfers=max(0,sum(l['kind']=='ride' for l in j['legs'])-1),
                 missPenalty=None if baseline['arrival'] is None else max(0,baseline['arrival']-j['arrival']))
        if q.walking_penalty is not None:
            j['recommendationScore'] = j['arrival'] - q.departure + j['walkingMeters'] / q.walking_speed / 60 * q.walking_penalty + j['transfers'] * 3
            j['safeScore'] = j['p90Arrival'] - q.departure + j['walkingMeters'] / q.walking_speed / 60 * q.walking_penalty + j['transfers'] * 3
        return j
