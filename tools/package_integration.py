"""Export the small existing BusTracker changes as a portable patch and module."""
import difflib
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('C:/Users/hajin/공부/울산과학대학교/3학년_1학기/2026일경험/bustracker')
DEST=ROOT/'integration/bustracker'
(DEST/'api').mkdir(parents=True,exist_ok=True)
shutil.copyfile(SOURCE/'api/integration.py',DEST/'api/integration.py')
diff=[]
for name in ('server.py','replay.py'):
    before=(ROOT/'tmp/jetson-source'/name).read_text(encoding='utf-8').splitlines(keepends=True)
    after=(SOURCE/name).read_text(encoding='utf-8').splitlines(keepends=True)
    diff.extend(difflib.unified_diff(before,after,fromfile='a/'+name,tofile='b/'+name))
after=(DEST/'api/integration.py').read_text(encoding='utf-8').splitlines(keepends=True)
diff.extend(difflib.unified_diff([],after,fromfile='/dev/null',tofile='b/api/integration.py'))
(DEST/'bustracker.patch').write_text(''.join(diff),encoding='utf-8',newline='\n')
print('Exported integration module and minimal patch')
