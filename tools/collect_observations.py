"""Explicitly started collector; Ctrl+C exits. Reads Any% API, never rewrites BusTracker."""
import argparse
import json
import time
import urllib.request
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:8001')
parser.add_argument('--interval',type=float,default=10)
parser.add_argument('--duration',type=float,default=0,help='Seconds; 0 runs until Ctrl+C')
parser.add_argument('--quiet',action='store_true')
parser.add_argument('--output',type=Path)
args=parser.parse_args()
started=time.monotonic();requests=inserted=errors=0;sources=set()
try:
    while not args.duration or time.monotonic()-started<args.duration:
        try:
            request=urllib.request.Request(args.url.rstrip('/')+'/v1/observations/collect',data=b'',method='POST')
            with urllib.request.urlopen(request,timeout=20) as response:
                payload=json.load(response);requests+=1;inserted+=payload['inserted'];sources.add(payload['source'])
                if not args.quiet:print(json.dumps(payload),flush=True)
        except Exception as e:
            errors+=1
            print(type(e).__name__,str(e),flush=True)
        time.sleep(max(1,args.interval))
except KeyboardInterrupt:
    print('Collector stopped.')
finally:
    result={'requests':requests,'inserted':inserted,'errors':errors,'sources':sorted(sources),'durationSeconds':round(time.monotonic()-started,2),'warning':'Repeated replay observations are not independent real calendar days.'}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result),flush=True)
