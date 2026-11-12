"""Report concrete source coverage and remaining gaps in the delivered bus dataset."""
import hashlib
import json
import math
import sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.walking import default_graph


def main():
    raw=(ROOT/'shared/service_network.json').read_bytes()
    n=json.loads(raw)
    stops={s['id']:s for s in n['stops']}
    supplement=json.loads((ROOT/'shared/service_supplements.json').read_text(encoding='utf-8'))
    missing, misplaced = [],[]
    for route in n['routes']:
        for i,key in enumerate(route['shapeSegments']):
            points=n['shapes'][key]['points']
            if len(points)<2:
                missing.append(key)
                continue
            for point,sid in ((points[0],route['stops'][i]),(points[-1],route['stops'][i+1])):
                s=stops[sid]
                gap=math.hypot((point[0]-s['lat'])*111000,(point[1]-s['lon'])*91000)
                if gap>120:
                    misplaced.append(dict(routeId=route['id'],stopId=sid,meters=round(gap,1)))
    graph=default_graph()
    unsnapped=[dict(id=s['id'],name=s['name'],publicId=s['publicId']) for s in stops.values()
               if graph.snap((s['lat'],s['lon'])) is None]
    untimed=[]
    for route in n['routes']:
        if any(route['departuresByDay'].values()):
            continue
        reason=route.get('serviceStatus','Covered only by a verified joint timetable; individual 2300 departures are not separately assigned')
        untimed.append(dict(id=route['id'],number=route['number'],reason=reason))
    groups=[dict(id=r['id'],number=r['number'],passengerStops=len(r['passengerStops']),
                 calendar=r['serviceCalendar']) for r in n['routes'] if r.get('serviceGrouping')]
    report=dict(recordedAt=datetime.now(timezone.utc).isoformat(),networkVersion=n['version'],
        sha256=hashlib.sha256(raw).hexdigest(),officialRouteDirections=534,jointServiceGroups=groups,
        stops=len(stops),footpaths=len(n['footpaths']),geometry=dict(missingSegments=missing,
        endpointsOver120Meters=misplaced,naverRepairedRoutes=len(supplement['geometryRepairs']),
        correctedStopPositions=len(supplement.get('stops',{})),reviewedDirectedRoadTailConnections=1),
        directionsWithoutIndependentTimetable=untimed,
        remaining=dict(stopsOutsidePedestrianSnapCoverage=unsnapped,
            maximumStoredTransferWalkMeters=max(f['meters'] for f in n['footpaths']),
            storedFootpathsRole='Legacy nearby-stop cache; not the transfer walking search limit',
            transferWalkingMaximumMeters=None if n.get('walkingTransfers')=='road_graph' else 250,
            transferWalkingCoverage='Query-time pedestrian road-graph closure; arrival/walking Pareto labels and preference scoring, without a fixed distance cap',
            intermediateStopTimes='Distance and speed model; not recorded passage times',
            delayAndTransferProbability='Synthetic delay samples; not calibrated to contemporary observations',
            timetableRefresh='Reviewed snapshot; automatic change collection is not configured',
            liveHistory='Public ITS live GPS collection enabled on the deployed backend; historical days must accumulate',
            liveHistorySource='https://its.ulsan.kr/route/route.do'))
    (ROOT/'artifacts/service-data-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    official=json.loads((ROOT/'artifacts/official-data.json').read_text(encoding='utf-8'))
    official.update(sha256=report['sha256'],derivedNetworkVersion=n['version'],routes=len(n['routes']),
        officialRouteCount=534,supplementalServiceGroups=len(groups),footpaths=len(n['footpaths']),
        supplementalSources=n['supplementalSources'],routesMissingAllTimetables=[r['id'].removeprefix('its:') for r in untimed],
        departuresByDay={day:sum(len(r['departuresByDay'][day]) for r in n['routes']) for day in ('weekday','saturday','holiday')})
    (ROOT/'artifacts/official-data.json').write_text(json.dumps(official,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(missingRoadSegments=len(missing),endpointFlags=len(misplaced),
        stopCorrections=len(supplement.get('stops',{})),pedestrianSnapGaps=len(unsnapped),
        untimedDirections=len(untimed),jointGroups=len(groups))))


if __name__=='__main__':
    main()
