"""Build an isolated runtime using the existing BusTracker code, without its production DB."""
import csv
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('C:/Users/hajin/공부/울산과학대학교/3학년_1학기/2026일경험/bustracker')
DEST=ROOT/'tmp/bustracker'
DEST.mkdir(parents=True,exist_ok=True)
for name in ('route_stops_named.csv','stop_routes.csv','route_meta.csv','route_names_manual.csv'):
    shutil.copyfile(SOURCE/name,DEST/name)
print(DEST)
