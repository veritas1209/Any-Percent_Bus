"""Single-run device check, not a production latency benchmark or a traffic accuracy study."""
import argparse
import hashlib
import json
import time
from datetime import datetime,timezone
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://100.119.23.4:8001')
parser.add_argument('--web',default='http://100.119.23.4:8080')
args=parser.parse_args()
rows=[]
with httpx.Client(timeout=30) as client:
    for dataset,name,departure in [('demo','network.json',540),('observed','observed_network.json',430)]:
        local=json.loads((ROOT/'shared'/name).read_text(encoding='utf-8'))
        response=client.get(args.url+'/v1/network',params={'dataset':dataset});response.raise_for_status()
        assert response.json()==local,'Remote API dataset differs from bundled data'
        raw=client.get(args.web+'/assets/assets/data/'+name);raw.raise_for_status()
        assert raw.content==(ROOT/'shared'/name).read_bytes(),'Remote web dataset differs from delivered app'
        query={'dataset':dataset,'origin':local.get('defaultOrigin','uc'),'destination':local.get('defaultDestination','tower'),'departure':departure,'samples':300}
        client.post(args.url+'/v1/journeys/search',json=query).raise_for_status()
        started=time.perf_counter();response=client.post(args.url+'/v1/journeys/search',json=query);response.raise_for_status()
        elapsed=round((time.perf_counter()-started)*1000,2)
        data=response.json()
        assert all('statisticsIncludeFailurePenalty' in j for j in data['journeys'])
        rows.append({'dataset':dataset,'samples':300,'measuredRequests':1,'clientRoundTripMs':elapsed,'serverElapsedMs':data['elapsedMs'],
                     'candidateCount':len(data['journeys']),'source':data['source'],'networkSha256':hashlib.sha256(raw.content).hexdigest()})
result={'recordedAt':datetime.now(timezone.utc).isoformat(),'platform':'NVIDIA Jetson Orin Nano Super','cases':rows,
        'note':'One warmed request per dataset; not a percentile latency estimate. Both remote API and web datasets match delivered assets.'}
(ROOT/'artifacts/jetson-benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
