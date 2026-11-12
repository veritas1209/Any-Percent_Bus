import sqlite3
from app.live_history import LiveHistory


def test_live_passages_are_deduplicated_and_record_real_trip_travel_samples(tmp_path):
    data={'stops':[{'id':'a','lat':35.5,'lon':129.3},{'id':'b','lat':35.501,'lon':129.3}],
        'routes':[{'id':'its:1','stops':['a','b']}]}
    collector=LiveHistory(data,tmp_path/'live.db')
    def row(lat):return [{'busid':1,'brtid':1,'bopy2':lat,'bopx2':129.3,'busno':'must not be retained'}]
    assert collector.record(row(35.5),1000)['inserted']==1
    assert collector.record(row(35.5),1030)['inserted']==0
    assert collector.record(row(35.5005),1060)['inserted']==0
    assert collector.record(row(35.501),1090)['inserted']==1
    assert collector.record(row(35.501),1120)['inserted']==0
    coverage=collector.coverage()
    assert coverage['source']=='ulsan_its_live_gps'
    assert coverage['passages']==2 and coverage['travelSamples']==1
    assert not coverage['historicalBackfill']
    with sqlite3.connect(collector.path) as db:
        assert db.execute('SELECT end_at-start_at FROM travel_samples').fetchone()[0]==90
        assert {r[0] for r in db.execute('SELECT DISTINCT method FROM passages')}=={'initial_near_stop','entered_geofence_35m'}
        assert 'must not be retained' not in str(db.execute('SELECT * FROM latest').fetchall())


def test_missing_malformed_and_out_of_area_positions_are_not_made_into_history(tmp_path):
    collector=LiveHistory({'stops':[],'routes':[{'id':'its:1','stops':[]}]},tmp_path/'live.db')
    result=collector.record([{'busid':1,'brtid':1,'bopy2':float('nan'),'bopx2':129.3},
        {'busid':2,'brtid':1,'bopy2':37.5,'bopx2':127.0},{'brtid':1}],1000)
    assert result['tracked']==0 and result['inserted']==0
