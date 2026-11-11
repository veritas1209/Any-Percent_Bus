"""Import reviewed operator workbook cells and the dated joint-service PDF table."""
import hashlib
import json
import re
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'tmp/other-bus-sources'
DAYS=('weekday','saturday','holiday')


def main():
    sources={}
    for day,post in zip(DAYS,(18,17,16)):
        path=FOLDER/(day+'.xlsx')
        sources['operator:'+day]=dict(url=f'http://www.ulsanbus.or.kr/bbs/board.php?bo_table=time&wr_id={post}',
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),retrievedDate='2026-11-11')
    def cells(day,prefix):
        path=next(FOLDER.glob(day+'-'+prefix+'*.json'))
        return {c['cell']:c['value'] for row in json.loads(path.read_text(encoding='utf-8')) for c in row}
    def minutes(value):
        if isinstance(value,str) and re.fullmatch(r'\d\d:\d\d:\d\d',value):
            h,m,_=map(int,value.split(':'));return h*60+m
        raise ValueError('Expected an inspected Excel time cell')
    returns={}
    for day in DAYS:
        values=cells(day,'남구52')
        selected=[]
        for row in ((15,16,19,20) if day=='weekday' else (11,13)):
            for col in range(3,24,2):
                cell=chr(64+col)+str(row)
                value=values.get(cell)
                if isinstance(value,str) and re.fullmatch(r'\d\d:\d\d:\d\d',value):
                    selected.append(minutes(value))
        returns[day]=sorted(set(selected))
    assert [len(returns[d]) for d in DAYS]==[32,18,18]
    eonyang=[2,7,12,17,22,27]
    namchang=[3,8,13,18,23,28]
    seochang=[4,9,14,19,24,29]
    routes={
        'its:193000059':dict(departuresByDay=returns,scheduleSourceId='operator:weekday',
            scheduleEvidence=dict(sheet='남구52번(구22)',effectiveFrom='2026-09-09',
                cells='weekday C15:W16,C19:W20; weekend C11:U11,C13:S13; 동문굿모닝힐 columns only')),
        'its:196000761':dict(departuresByDay={d:[420,540,660,810,930] for d in DAYS},
            serviceCalendar=dict(onlyMonthDays=eonyang),scheduleSourceId='operator:weekday',
            scheduleEvidence=dict(sheet='울주83(구 울주03)',cells='B8,D8:G8; H8=17:30 uses the regular non-market route')),
        'its:196000760':dict(serviceCalendar=dict(monthDayOverrides=[dict(days=eonyang,departures=[1050])])),
        'its:196000764':dict(departuresByDay={d:[420,550,680,890,1020] for d in DAYS},
            serviceCalendar=dict(onlyMonthDays=namchang),scheduleSourceId='operator:weekday',
            scheduleEvidence=dict(sheet='울주87(구 울주07)',cells='B12,D12,F12,H12,J12')),
        'its:196000765':dict(departuresByDay={d:[480,610,740,950,1070] for d in DAYS},
            serviceCalendar=dict(onlyMonthDays=namchang),scheduleSourceId='operator:weekday',
            scheduleEvidence=dict(sheet='울주87(구 울주07)',cells='C12,E12,G12,I12,K12')),
        'its:196000762':dict(serviceCalendar=dict(exceptMonthDays=namchang,
            monthDayOverrides=[dict(days=seochang,departures=[420,540,660,890,1020])])),
        'its:196000763':dict(serviceCalendar=dict(exceptMonthDays=namchang,
            monthDayOverrides=[dict(days=seochang,departures=[470,590,710,950,1070])])),
        'its:196000776':dict(serviceStatus='No separate return departures in the current operator table',
            scheduleSourceId='operator:weekday',scheduleEvidence=dict(sheet='533(구718)',
            cells='B12:M17; yellow J15=17:40 is the outbound 196000775, not this return variant')),
        'its:195000233':dict(serviceStatus='No separate return departures in the current operator table',
            scheduleSourceId='operator:weekday',scheduleEvidence=dict(sheet='772',
            cells='B13:K18; school-support departures B16=06:40,H14=16:45 are outbound only')),
    }
    sources['namchang-market']=dict(url='https://access.visitkorea.or.kr/ms/detail.do?cotId=a07ae8af-fc6e-4146-9af2-28ab0d05dfe3')
    sources['seochang-market']=dict(url='https://yangsan.go.kr/ungsang/contents.do?mid=0206140100')
    sources['eonyang-market']=dict(url='https://assembly.ulju.ulsan.kr/kr/qna/contents?uid=67DA0D88892FD9BD3CD18D9BC4E248BC&reform=view')
    sources['yangsan:joint']=dict(url='https://bus.yangsan.go.kr/yangsan_2016/board/notice_view.php?num=943',
        attachmentUrl='https://bus.yangsan.go.kr/yangsan_2016/board/download.php?num=943',
        sha256=hashlib.sha256((FOLDER/'yangsan-2300.pdf').read_bytes()).hexdigest(),
        effectiveFrom='2026-10-06',effectiveThrough='2026-11-22',
        scope='2100/2300 shared departures; only their verified common Ulsan stops may be used')
    tables=json.loads((FOLDER/'yangsan-tables.json').read_text(encoding='utf-8'))
    times=[]
    for table in tables:
        direction=[]
        for cols in ((7,10),(8,11)):
            values=[]
            for row in table[2:]:
                for col in cols:
                    text=row[col] or ''
                    if re.fullmatch(r'\d\d:\d\d',text):
                        h,m=map(int,text.split(':'));values.append(h*60+m)
            assert all(0<=value<1440 for value in values)
            direction.append(sorted(set(values)))
        times.append(direction)
    assert [len(v) for v in times[0]]==[77,70]
    assert [len(v) for v in times[1]]==[66,60]
    network=json.loads((ROOT/'shared/service_network.json').read_text(encoding='utf-8'))
    stops={s['id']:s for s in network['stops']}
    naver2100=json.loads((ROOT/'tmp/naver-bus/2030030.json').read_text(encoding='utf-8'))['data']
    naver2300=json.loads((ROOT/'tmp/naver-bus/2030073.json').read_text(encoding='utf-8'))['data']
    common={s['id'] for s in naver2100['busStops']} & {s['id'] for s in naver2300['busStops']}
    shared_stops=[s for s in naver2300['busStops'] if s['id'] in common]
    extras=[]
    for direction,base in enumerate(('its:388023001','its:388023002')):
        route=next(r for r in network['routes'] if r['id']==base)
        # Yangsan and Ulsan publish different public codes for the same stop.
        allowed=[sid for sid in route['stops'] if sid.startswith('19') and any(
            math.hypot((stops[sid]['lat']-s['point']['y'])*111000,
                       (stops[sid]['lon']-s['point']['x'])*91000)<=40 for s in shared_stops)]
        assert len(allowed)>=15
        extras.append(dict(id='shared:yangsan:'+str(direction),baseRoute=base,patch=dict(
            number='2100·2300',familyId='shared:yangsan:'+str(direction),passengerStops=allowed,
            departuresByDay={day:times[0 if day=='weekday' else 1][direction] for day in DAYS},
            serviceCalendar=dict(startDate='2026-10-06',endDate='2026-11-22'),
            scheduleSourceId='yangsan:joint',serviceGrouping='Shared Ulsan stop service, individual bus number not assigned')))
    result=dict(sources=sources,routes=routes,extraRoutes=extras)
    (ROOT/'shared/service_schedule_supplements.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(routePatches=len(routes),sharedServiceGroups=len(extras),jointDepartureCounts=[[len(v) for v in day] for day in times])))


if __name__=='__main__':
    main()
