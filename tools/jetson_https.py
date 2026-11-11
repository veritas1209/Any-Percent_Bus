"""Configure the Any% HTTPS endpoints on the authorized Jetson."""
import argparse,json,shlex,sys
from pathlib import Path
import paramiko

parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inspect','enable','enable-public']);args=parser.parse_args()
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
        print(run('tailscale funnel --help 2>&1')[:6500])
    else:
        run('test -f /home/hajin/anypercent/.anypercent-managed')
        public = args.action == 'enable-public'
        port = 10000 if public else 9443
        key=f'{domain}:{port}';web=config.get('Web',{})
        if not public and config.get('AllowFunnel',{}).get(key):raise RuntimeError('Private HTTPS port is already public')
        existing=web.get(key,{}).get('Handlers',{})
        allowed={'/':'http://100.119.23.4:8080'}
        if public:
            for path in ('/v1/network','/v1/journeys/search','/v1/places/search'):
                allowed[path] = 'http://100.119.23.4:8001' + path
        else:
            allowed['/v1'] = 'http://100.119.23.4:8001/v1'
        for path,handler in existing.items():
            if path not in allowed or handler.get('Proxy')!=allowed[path]:raise RuntimeError(f'HTTPS port {port} already serves another application')
        command = 'funnel --yes' if public else 'serve'
        for path,target in allowed.items():
            print(run(f'tailscale {command} --bg --https={port} --set-path='+shlex.quote(path)+' '+shlex.quote(target),sudo=True),flush=True)
        after=json.loads(run('tailscale serve status --json'))
        preserved=all(after.get('Web',{}).get(k)==v for k,v in web.items() if k!=key)
        old_funnels = {k:v for k,v in config.get('AllowFunnel',{}).items() if k != key}
        other_funnels = {k:v for k,v in after.get('AllowFunnel',{}).items() if k != key}
        assert preserved and old_funnels == other_funnels
        assert bool(after.get('AllowFunnel',{}).get(key)) == public
        result={'url':f'https://{domain}:{port}','httpsPort':port,
                'handlers':after['Web'][key]['Handlers'],'privateOnly':not public,
                'existingServicesPreserved':preserved}
        filename = 'public-https-status.json' if public else 'https-status.json'
        root=Path(__file__).resolve().parents[1];(root/'artifacts'/filename).write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))
finally:client.close()
