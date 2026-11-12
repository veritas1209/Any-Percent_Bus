"""Compare nominal arrival/score against the recorded, same-dataset route matrix."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.engine import Engine, Query
from check_service_routes import CASES


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--references',nargs='+',default=['service-route-matrix.json','service-route-weekends.json'])
    parser.add_argument('--report',default='routing-optimization.json')
    parser.add_argument('--allow-expanded-network',action='store_true')
    args=parser.parse_args()
    path=ROOT/'shared/service_network.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    engine=Engine(data)
    cases={row[0]:row for row in CASES}
    output=[]
    for name in args.references:
        reference=json.loads((ROOT/'artifacts'/name).read_text(encoding='utf-8'))
        assert args.allow_expanded_network or reference['networkVersion']==data['version']
        for old in reference['cases']:
            _,_,origin,destination,transfers=cases[old['case']]
            point=lambda sid:{k:engine.stops[sid][k] for k in ('name','lat','lon')}
            q=Query(origin,destination,departure=old['departure'],max_walk=None,walking_penalty=1,
                max_transfers=transfers,service_day=old['day'],service_date=old['serviceDate'],
                origin_point=point(origin),destination_point=point(destination))
            started=time.perf_counter()
            rows=engine.search(q)
            elapsed=round((time.perf_counter()-started)*1000,2)
            fastest=min(j['arrival'] for j in rows)
            score=min(j['recommendationScore'] for j in rows)
            before=old['recommended']
            old_score=before['arrival']-q.departure+before['walkingMeters']/72+before['transfers']*3
            errors=[]
            if fastest>old['fastest']['arrival']+.001:errors.append('Fastest arrival regressed')
            if score>old_score+.001:errors.append('Recommended score regressed')
            output.append(dict(case=old['case'],day=old['day'],departure=old['departure'],
                localElapsedMs=elapsed,previousServerMs=old['serverMs'],
                fastestBefore=old['fastest']['arrival'],fastestAfter=fastest,
                scoreBefore=old_score,scoreAfter=score,errors=errors))
            print(json.dumps(output[-1]),flush=True)
    report=dict(networkVersion=data['version'],networkSha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        note='Local algorithm validation. Previous times are from Jetson and are not a hardware-matched speed comparison.',
        cases=output,passed=not any(r['errors'] for r in output))
    (ROOT/'artifacts'/args.report).write_text(json.dumps(report,indent=2),encoding='utf-8')
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
