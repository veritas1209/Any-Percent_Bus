"""Check Android and web bundles contain exactly the shared datasets being delivered."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
apk=ROOT/'app/build/app/outputs/flutter-apk/app-release.apk'
result={'apkBytes':apk.stat().st_size,'apkSha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'datasets':[]}
with zipfile.ZipFile(apk) as archive:
    for name in ('network.json','observed_network.json'):
        raw=(ROOT/'shared'/name).read_bytes()
        assert archive.read('assets/flutter_assets/assets/data/'+name)==raw, f'Outdated APK asset: {name}'
        assert (ROOT/'app/build/web/assets/assets/data'/name).read_bytes()==raw, f'Outdated web asset: {name}'
        data=json.loads(raw)
        result['datasets'].append({'name':name,'sha256':hashlib.sha256(raw).hexdigest(),'routes':len(data['routes']),'stops':len(data['stops'])})
    assert 'assets/flutter_assets/assets/fonts/PretendardVariable.ttf' in archive.namelist()
(ROOT/'artifacts/build-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
