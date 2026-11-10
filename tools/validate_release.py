"""Relocate a release source ZIP and run its tests. Keeps the scoped audit folder for inspection."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--flutter',required=True,type=Path)
args=parser.parse_args()
archive=ROOT/'release/AnyPercent-source.zip'
(ROOT/'tmp').mkdir(exist_ok=True)
destination=Path(tempfile.mkdtemp(prefix='release-check-',dir=ROOT/'tmp')).resolve()
with zipfile.ZipFile(archive) as z:
    for name in z.namelist():
        target=(destination/name).resolve()
        assert target.is_relative_to(destination),'Unsafe archive path'
    z.extractall(destination)


def run(command,cwd):
    result=subprocess.run(command,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:
        print(result.stdout);print(result.stderr);raise RuntimeError('Portable test failed')
    return result.stdout


python_result=run([sys.executable,'-m','pytest','backend/tests','-q'],destination)
flutter_prefix=[str(args.flutter.resolve())]
if os.name=='nt':flutter_prefix=[os.environ.get('COMSPEC','cmd.exe'),'/d','/c',*flutter_prefix]
run([*flutter_prefix,'pub','get'],destination/'app')
flutter_result=run([*flutter_prefix,'test'],destination/'app')
passed=re.search(r'\b(\d+) passed\b',python_result)
result={'testedAt':datetime.now(timezone.utc).isoformat(),'archiveSha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'backendPassed':bool(passed),'backendTestCount':int(passed.group(1)) if passed else 0,'flutterPassed':'All tests passed!' in flutter_result,
        'note':'Extracted into a new directory; uses existing Python dependencies, Flutter SDK and download cache, not a clean operating system.',
        'auditDirectory':str(destination)}
assert result['backendPassed'] and result['flutterPassed']
(ROOT/'release/portability.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
