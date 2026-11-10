"""Read-only, bounded inspection of BusTracker data for the seven sparse routes.

SSH password is consumed from stdin. No production files or database settings are changed.
"""
import json
import shlex
import sys
from pathlib import Path

import paramiko

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'tmp/jetson-extra'
DEST.mkdir(parents=True,exist_ok=True)
client=paramiko.SSHClient();client.load_system_host_keys()
client.connect('100.119.23.4',username='hajin',password=sys.stdin.readline().strip(),look_for_keys=False,allow_agent=False,timeout=10)
try:
    sftp=client.open_sftp()
    for name in ('stop_routes.csv','bus_stops.csv','route_stops.csv','gen_mapping.py','parse_namu.py','automap.py','find_route.py','fetch_route_names.py'):
        sftp.get('/home/hajin/bustracker/'+name,str(DEST/name))
    sftp.close()
    code=r'''
import json,sqlite3,time
from pathlib import Path
ids=['195000130','195900010','196000041','196000071','196000131','196000613','196000810']
db=sqlite3.connect('file:/home/hajin/bustracker/bustracker.db?mode=ro',uri=True,timeout=2)
db.row_factory=sqlite3.Row
deadline=time.monotonic()+15
db.set_progress_handler(lambda:time.monotonic()>deadline,10000)
result={'tables':[dict(r) for r in db.execute("SELECT name,sql FROM sqlite_master WHERE type IN ('table','index') AND name NOT LIKE 'sqlite_%'")],
        'routes':{},'stops':{},'stopLinks':{}}
for rid in ids:
 result['routes'][rid]=[dict(r) for r in db.execute('SELECT * FROM routes WHERE route_id=?',(rid,))]
 result['stops'][rid]=[dict(r) for r in db.execute('SELECT * FROM stops WHERE route_id=? ORDER BY seq',(rid,))]
 result['stopLinks'][rid]=[dict(r) for r in db.execute('SELECT * FROM stop_routes WHERE route_id=? LIMIT 500',(rid,))]
result['gpsQueryPlans']={rid:[tuple(r) for r in db.execute('EXPLAIN QUERY PLAN SELECT * FROM gps_log WHERE device_id=? AND route_id=? ORDER BY id DESC LIMIT 1000',(device,rid))] for rid,device in zip(ids,['987','2162','2136','6','992','5','636'])}
result['otherDataFiles']=[str(p.relative_to('/home/hajin/bustracker')) for p in Path('/home/hajin/bustracker').glob('*/*') if p.suffix in ('.csv','.json','.db','.sqlite')]
devices=['987','2162','2136','6','992','5','636']
result['deviceState']=[dict(r) for r in db.execute('SELECT * FROM device_state WHERE route_id IN (?,?,?,?,?,?,?)',ids)]
result['gpsSamples']={}
for rid,device in zip(ids,devices):
 # Bounded ordered seeks use the existing (device_id,id) index.
 first=db.execute('SELECT id FROM gps_log WHERE device_id=? ORDER BY id LIMIT 1',(device,)).fetchone()
 last=db.execute('SELECT id FROM gps_log WHERE device_id=? ORDER BY id DESC LIMIT 1',(device,)).fetchone()
 if first is None:result['gpsSamples'][rid]=[];continue
 samples={}
 for fraction in (0,.25,.5,.75,1):
  anchor=int(first['id']+(last['id']-first['id'])*fraction)
  if fraction==1:
   query='SELECT * FROM gps_log WHERE device_id=? ORDER BY id DESC LIMIT 150';parameters=(device,)
  else:
   query='SELECT * FROM gps_log WHERE device_id=? AND id>=? ORDER BY id LIMIT 150';parameters=(device,anchor)
  for row in db.execute(query,parameters):
   if row['route_id']==rid:samples[row['id']]=dict(row)
 result['gpsSamples'][rid]=list(samples.values())
print(json.dumps(result,ensure_ascii=False))
db.close()
'''
    _,out,err=client.exec_command('python3 -c '+shlex.quote(code),timeout=30)
    raw=out.read().decode('utf-8');error=err.read().decode('utf-8')
    if out.channel.recv_exit_status():raise RuntimeError(error)
    report=json.loads(raw)
    (DEST/'db-inspection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'downloaded':sorted(p.name for p in DEST.iterdir()),'routes':report['routes'],'stopCounts':{k:len(v) for k,v in report['stops'].items()},'stopLinkCounts':{k:len(v) for k,v in report['stopLinks'].items()},'historySampleCounts':{k:len(v) for k,v in report['gpsSamples'].items()},'otherDataFiles':report['otherDataFiles']},ensure_ascii=False))
finally:client.close()
