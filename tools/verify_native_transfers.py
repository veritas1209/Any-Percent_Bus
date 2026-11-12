"""Compare compiled and Python reverse bounds on the actual reviewed road graph."""
import argparse
import json
import math
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.transfers import TransferGraph


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',default='native-transfer-verification.json');args=parser.parse_args()
    data=(ROOT/'shared/transfer_graph.bin').read_bytes()
    native=TransferGraph(data);reference=TransferGraph(data,use_native=False)
    assert native.native is not None,'SciPy is not installed in this interpreter'
    cases=[]
    for sources in ({'193012313':900},{'195040328':950,'196031532':910},
                    {'194019014':1000,'196030401':980,'196040232':930}):
        start=time.perf_counter();expected=reference.latest(sources,1.2,480);before=time.perf_counter()-start
        start=time.perf_counter();actual=native.latest(sources,1.2,480);after=time.perf_counter()-start
        assert actual.keys()==expected.keys()
        maximum=max((abs(actual[s]-expected[s]) for s in actual),default=0)
        assert maximum<1e-7,maximum
        cases.append(dict(sources=sources,stops=len(actual),maximumDifferenceMinutes=maximum,
            pythonMs=round(before*1000,2),nativeMs=round(after*1000,2)))
    import scipy
    result=dict(scipyVersion=scipy.__version__,cases=cases,passed=True)
    (ROOT/'artifacts').mkdir(exist_ok=True)
    (ROOT/'artifacts'/args.report).write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
