"""Package inspected app builds and portable sources; exclude caches, credentials and production data."""
import hashlib
import json
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'release'
OUT.mkdir(exist_ok=True)
APK=ROOT/'app/build/app/outputs/flutter-apk/app-release.apk'
version=re.search(r'^version:\s*(\d+\.\d+\.\d+)',(ROOT/'app/pubspec.yaml').read_text(encoding='utf-8'),re.MULTILINE).group(1)
apk_name=f'AnyPercent-{version}.apk'
assert APK.exists(), 'Build Android APK first'
backend=ET.parse(ROOT/'artifacts/backend-tests.xml').getroot().find('testsuite')
assert backend is not None and int(backend.attrib['failures'])==0 and int(backend.attrib['errors'])==0
events=[]
for line in (ROOT/'artifacts/flutter-tests.jsonl').read_text(encoding='utf-8-sig').splitlines():
    try:event=json.loads(line)
    except json.JSONDecodeError:continue
    if isinstance(event,dict):events.append(event)
assert any(e.get('type')=='done' and e.get('success') is True for e in events), 'Flutter tests did not pass'
browser=json.loads((ROOT/'artifacts/browser-acceptance.json').read_text(encoding='utf-8'))
assert not browser['errors'] and not browser.get('externalRequests') and len(browser['passed'])>=11
audit=json.loads((ROOT/'artifacts/build-audit.json').read_text())
assert hashlib.sha256(APK.read_bytes()).hexdigest()==audit['apkSha256'], 'APK changed after audit'
shutil.copyfile(APK,OUT/apk_name)

excluded={'build','.gradle','.dart_tool','.kotlin','.cxx','.idea','__pycache__','.pytest_cache','.git','video'}
excluded_files={'local.properties','key.properties','GeneratedPluginRegistrant.java','.flutter-plugins-dependencies'}


def allowed(path):
    return not (excluded & set(path.relative_to(ROOT).parts)) and path.name not in excluded_files and not path.name.startswith('.env') and path.suffix not in ('.db','.db-wal','.db-shm','.sqlite','.sqlite3','.log','.jks','.keystore','.pem','.key','.p12','.pfx','.pyc','.iml')


with zipfile.ZipFile(OUT/'AnyPercent-source.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
    for folder in ('app','backend','shared','integration','tools','artifacts'):
        for path in sorted((ROOT/folder).rglob('*')):
            if path.is_file() and allowed(path):archive.write(path,path.relative_to(ROOT).as_posix())
    for name in ('README.md','.gitignore','.gitattributes'):
        archive.write(ROOT/name,name)

with zipfile.ZipFile(OUT/'AnyPercent-web.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((ROOT/'app/build/web').rglob('*')):
        if path.is_file():archive.write(path,path.relative_to(ROOT/'app/build/web').as_posix())

manifest={'builtAt':datetime.now(timezone.utc).isoformat(),'version':version,'files':[]}
for name in (apk_name,'AnyPercent-source.zip','AnyPercent-web.zip'):
    path=OUT/name
    manifest['files'].append({'name':name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(manifest,indent=2))
