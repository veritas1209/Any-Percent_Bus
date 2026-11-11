"""Task-scoped SSH helper. Password is read from stdin and never written to disk."""
import argparse
import hashlib
import json
import shlex
import sys
from pathlib import Path

import paramiko

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['inspect','download','probe','deploy-backend','deploy-backend-code','deploy-web','deploy-web-server','deploy-apk','status'])
args=parser.parse_args()
client=paramiko.SSHClient()
client.load_system_host_keys()
client.connect('100.119.23.4',username='hajin',password=sys.stdin.readline().strip(),look_for_keys=False,allow_agent=False,timeout=10,auth_timeout=10)
client.get_transport().set_keepalive(15)
try:
    if args.action in ('deploy-backend','deploy-backend-code','deploy-web','deploy-web-server','deploy-apk','status'):
        base='/home/hajin/anypercent'
        sftp=client.open_sftp()
        sftp.get_channel().settimeout(60)
        if args.action!='status':
            marker=base+'/.anypercent-managed'
            try:
                sftp.stat(base)
                sftp.stat(marker)
            except FileNotFoundError:
                try:sftp.stat(base)
                except FileNotFoundError:
                    sftp.mkdir(base)
                    with sftp.open(marker,'w') as f:f.write('isolated Anypercent development demo\n')
                else:raise RuntimeError('Unmanaged existing remote folder; refusing to overwrite')
            remote_hashes = {}
            if args.action == 'deploy-web':
                _, hashes, hash_errors = client.exec_command('find '+shlex.quote(base+'/web')+' -type f -exec sha256sum {} +', timeout=45)
                lines = hashes.read().decode().splitlines()
                if hashes.channel.recv_exit_status() != 0:
                    raise RuntimeError('Could not read the existing web bundle hashes')
                remote_hashes = {line[66:]: line[:64] for line in lines}
            def upload(source,target):
                if source.is_dir():
                    try:sftp.mkdir(target)
                    except OSError:pass
                    for child in source.iterdir():
                        if child.name not in ('__pycache__','.pytest_cache'):upload(child,target+'/'+child.name)
                else:
                    if remote_hashes.get(target) == hashlib.sha256(source.read_bytes()).hexdigest():
                        return
                    sftp.put(str(source),target)
            if args.action in ('deploy-backend','deploy-backend-code'):
                for folder in ('backend','shared','tools'):
                    try:sftp.mkdir(base+'/'+folder)
                    except OSError:pass
                upload(ROOT/'backend/app',base+'/backend/app')
                if args.action == 'deploy-backend':
                    for name in ('network.json','observed_network.json','service_network.json','bustracker_catalog.json','walk_graph.bin','places.json'):
                        upload(ROOT/'shared'/name,base+'/shared/'+name)
                upload(ROOT/'tools/remote_runtime.py',base+'/tools/remote_runtime.py')
            elif args.action in ('deploy-web','deploy-web-server'):
                if args.action == 'deploy-web':
                    upload(ROOT/'app/build/web',base+'/web')
                upload(ROOT/'tools/web_server.py',base+'/tools/web_server.py')
                upload(ROOT/'tools/remote_runtime.py',base+'/tools/remote_runtime.py')
            else:
                manifest=json.loads((ROOT/'release/manifest.json').read_text())
                apk=next(item for item in manifest['files'] if item['name'].endswith('.apk'))
                temporary = base + '/web/AnyPercent.apk.uploading'
                upload(ROOT/'release'/apk['name'],temporary)
                _,check,check_err=client.exec_command('sha256sum '+shlex.quote(temporary),timeout=20)
                if check.read().decode().split()[0]!=apk['sha256']:
                    raise RuntimeError('Uploaded APK checksum mismatch')
                sftp.posix_rename(temporary, base + '/web/AnyPercent.apk')
                print('APK SHA256 verified')
        sftp.close()
        action={'deploy-backend':'start-backend','deploy-backend-code':'start-backend','deploy-web':'start-web','deploy-web-server':'start-web','deploy-apk':'status','status':'status'}[args.action]
        _,out,err=client.exec_command('python3 '+base+'/tools/remote_runtime.py '+action,timeout=30)
        print(out.read().decode());print(err.read().decode())
        if out.channel.recv_exit_status()!=0:raise RuntimeError('Remote demo command failed')
    elif args.action=='probe':
        code="""import sys,importlib.util,socket
from pathlib import Path
print('PYTHON',sys.version)
for name in ('fastapi','uvicorn','httpx','pydantic','venv'):
 try:
  m=__import__(name);print(name,getattr(m,'__version__','available'))
 except ImportError:print(name,'MISSING')
print('TARGET_EXISTS',Path('/home/hajin/anypercent').exists())
for port in (8001,8080):
 s=socket.socket();print('PORT',port,'in use' if s.connect_ex(('100.119.23.4',port))==0 else 'free');s.close()
"""
        _,out,err=client.exec_command('python3 -c '+shlex.quote(code),timeout=20)
        print(out.read().decode());print(err.read().decode())
    elif args.action=='inspect':
        code="""import os,csv,collections
from pathlib import Path
p=Path('/home/hajin/bustracker')
print('PROJECT_EXISTS',p.exists())
if p.exists():
 print('FILES',[(x.name,x.stat().st_size) for x in p.iterdir() if x.is_file()])
 f=p/'gps_replay.csv'
 if f.exists():
  with f.open(encoding='utf-8-sig') as h:
   r=csv.reader(h); header=next(r); count=0; devices=set(); routes=collections.Counter(); first=None; last=None
   for row in r:
    count+=1; first=first or row[0]; last=row[0]; devices.add(row[1]); routes[row[4]]+=1
  print('GPS',{'header':header,'rows':count,'start':first,'end':last,'vehicles':len(devices),'routes':len(routes),'topRoutes':routes.most_common(10)})
"""
        command='hostname; uname -m; cat /proc/device-tree/model 2>/dev/null; systemctl show bustracker -p ActiveState -p ExecStart -p WorkingDirectory; python3 -c '+shlex.quote(code)
        _,out,err=client.exec_command(command,timeout=30)
        print(out.read().decode('utf-8',errors='replace'))
        print(err.read().decode('utf-8',errors='replace'))
    else:
        dest=ROOT/'tmp/jetson-source';dest.mkdir(parents=True,exist_ok=True)
        sftp=client.open_sftp()
        for name in ('server.py','state.py','replay.py','api/tracking.py','db.py','route_stops_named.csv','route_names_manual.csv','route_meta.csv','gps_replay.csv'):
            target=dest/name;target.parent.mkdir(parents=True,exist_ok=True)
            try:
                sftp.get('/home/hajin/bustracker/'+name,str(target))
                print('DOWNLOADED',name,target.stat().st_size)
            except FileNotFoundError:
                print('MISSING',name)
        sftp.close()
finally:
    client.close()
