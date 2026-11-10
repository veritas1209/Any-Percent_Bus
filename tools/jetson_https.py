"""Inspect or configure a private Any% HTTPS endpoint; never enable Funnel."""
import argparse,json,shlex,sys
from pathlib import Path
import paramiko

parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inspect','enable']);args=parser.parse_args()
password=sys.stdin.readline().strip()
client=paramiko.SSHClient();client.load_system_host_keys()
client.connect('100.119.23.4',username='hajin',password=password,look_for_keys=False,allow_agent=False,timeout=10)
def run(command,sudo=False):
    stdin,out,err=client.exec_command(('sudo -S -p "" ' if sudo else '')+command,timeout=25)
    if sudo:stdin.write(password+'\n');stdin.flush()
    value=out.read().decode();error=err.read().decode();code=out.channel.recv_exit_status()
    if code:raise RuntimeError(f'{command}: {code}: {error[:500]} {value[:500]}')
    return value
try:
    status=json.loads(run('tailscale status --json'))
    domain=status['Self']['DNSName'].rstrip('.')
    config=json.loads(run('tailscale serve status --json') or '{}')
    if args.action=='inspect':
        print(json.dumps({'domain':domain,'serve':config,'certificateDomains':status.get('CertDomains'),'backendState':status['BackendState']}))
        print(run('tailscale serve --help')[:6500])
    else:
        run('test -f /home/hajin/anypercent/.anypercent-managed')
        port=9443;key=f'{domain}:{port}';web=config.get('Web',{})
        if config.get('AllowFunnel',{}).get(key):raise RuntimeError('Port 9443 is publicly exposed; left unchanged')
        existing=web.get(key,{}).get('Handlers',{})
        allowed={'/':'http://100.119.23.4:8080','/v1':'http://100.119.23.4:8001/v1'}
        for path,handler in existing.items():
            if path not in allowed or handler.get('Proxy')!=allowed[path]:raise RuntimeError('HTTPS port 9443 already serves another application; left unchanged')
        for path,target in allowed.items():
            print(run('tailscale serve --bg --https=9443 --set-path='+shlex.quote(path)+' '+shlex.quote(target),sudo=True))
        after=json.loads(run('tailscale serve status --json'))
        preserved=all(after.get('Web',{}).get(k)==v for k,v in web.items() if k!=key)
        assert preserved and after.get('AllowFunnel',{})==config.get('AllowFunnel',{})
        result={'url':f'https://{domain}:9443','httpsPort':9443,
                'handlers':after['Web'][key]['Handlers'],'privateOnly':not after.get('AllowFunnel',{}).get(key,False),
                'existingServicesPreserved':preserved}
        root=Path(__file__).resolve().parents[1];(root/'artifacts/https-status.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
finally:client.close()
