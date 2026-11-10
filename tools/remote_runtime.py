"""Manage only this isolated demo's two child processes on the authorized Jetson."""
import argparse
import json
import os
import secrets
import signal
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
HOST='100.119.23.4'
parser=argparse.ArgumentParser()
parser.add_argument('action',choices=['start-backend','start-web','status','stop'])
args=parser.parse_args()


def managed(kind):
    pidfile=ROOT/f'.{kind}.pid'
    if not pidfile.exists():return None
    pid=int(pidfile.read_text())
    try:
        proc=Path('/proc')/str(pid)
        if (proc/'stat').read_text().split(') ',1)[1].split()[0]=='Z':return None
        command=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
        if not command.strip():return None
        expected='uvicorn app.main:app' if kind=='backend' else 'http.server 8080'
        if (proc/'cwd').resolve()!=ROOT or expected not in command:
            if (proc/'stat').read_text().split(') ',1)[1].split()[0]=='Z':return None
            raise RuntimeError(f'{kind}: PID does not belong to this demo; refusing to stop it')
        return pid
    except FileNotFoundError:
        return None


def start(kind):
    old=managed(kind)
    if old:
        os.kill(old,signal.SIGTERM)
        for _ in range(150):
            if managed(kind) is None:break
            time.sleep(.1)
        else:
            if managed(kind)!=old:raise RuntimeError('Demo process ownership changed during shutdown')
            os.kill(old,signal.SIGKILL)
            time.sleep(.2)
            if managed(kind) is not None:raise RuntimeError('Existing demo process did not stop')
    env=os.environ.copy()
    if kind=='backend':
        keyfile=ROOT/'.integration-key'
        if not keyfile.exists():
            keyfile.write_text(secrets.token_urlsafe(32));keyfile.chmod(0o600)
        env.update(BUSTRACKER_CSV='/home/hajin/bustracker/gps_replay.csv',BUSTRACKER_URL=f'http://{HOST}:8001',BUSTRACKER_INTEGRATION_KEY=keyfile.read_text().strip())
        command=[sys.executable,'-m','uvicorn','app.main:app','--app-dir','backend','--host',HOST,'--port','8001']
    else:
        command=[sys.executable,'-m','http.server','8080','--bind',HOST,'--directory',str(ROOT/'web')]
    with (ROOT/f'{kind}.log').open('a') as log:
        child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    (ROOT/f'.{kind}.pid').write_text(str(child.pid))
    time.sleep(2)
    if child.poll() is not None:raise RuntimeError(f'{kind} failed; inspect its scoped log')
    print(json.dumps({'started':kind,'pid':child.pid,'host':HOST}))


if args.action.startswith('start-'):
    start(args.action.split('-',1)[1])
elif args.action=='stop':
    for kind in ('backend','web'):
        pid=managed(kind)
        if pid:os.kill(pid,signal.SIGTERM)
else:
    output={kind:managed(kind) for kind in ('backend','web')}
    output['memoryMiB']={}
    for kind in ('backend','web'):
        if output[kind]:
            for line in Path(f'/proc/{output[kind]}/status').read_text().splitlines():
                if line.startswith('VmRSS:'):output['memoryMiB'][kind]=round(int(line.split()[1])/1024,1)
    dbpath=ROOT/'backend/catalog.db'
    if dbpath.exists():
        with sqlite3.connect(f'file:{dbpath}?mode=ro',uri=True) as db:
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='arrivals'").fetchone():
                output['arrivals']=[{'source':s,'count':n,'trips':t,'stops':p} for s,n,t,p in db.execute('SELECT source,COUNT(*),COUNT(DISTINCT trip_id),COUNT(DISTINCT stop_id) FROM arrivals GROUP BY source')]
    try:
        with urlopen(f'http://{HOST}:8001/v1/health',timeout=5) as r:output['health']=json.load(r)
    except Exception as e:output['health']=str(e)
    output['bustracker']=subprocess.check_output(['systemctl','is-active','bustracker'],text=True).strip()
    print(json.dumps(output))
