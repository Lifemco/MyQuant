"""同标的同日行情的身份、口径及跨源一致性保护。"""
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pandas as pd
import pytest

from app.core.validation import validateSymbol
from app.data.contract import describeBars, instrument, compareDailyBars, validateBars
from app.data.store import saveBars, loadBars
from app.data.tencent_provider import TencentProvider
from app.monitor.session import closedBars
from tests.conftest import makeBars


def data(values=None, *, source='tencent', symbol='600519', adjustment='none', unit='lot100', observed=None):
    return describeBars(makeBars(values or [100.,101.,102.]),'cn',symbol,'day',source=source,
                        adjustment=adjustment,volumeUnit=unit,observedAt=observed)


def test_stock_and_index_with_same_digits_have_different_identities():
    assert instrument('cn','000001')['instrumentId']=='cn:sz000001'
    assert instrument('cn','sh000001')['instrumentId']=='cn:sh000001'
    assert instrument('cn','sh000001')['priceUnit']=='point'
    assert validateSymbol('cn','SH000001')=='sh000001'
    assert validateSymbol('cn','SZ000001')=='000001'
    assert TencentProvider('cn')._fullCode('sh000001')=='sh000001'


def test_stock_and_index_do_not_share_cache_file(tmp_path):
    stock=data(symbol='000001')
    index=data(symbol='sh000001')
    a=saveBars(stock,'cn','000001',dataDir=tmp_path)
    b=saveBars(index,'cn','sh000001',dataDir=tmp_path)
    assert a!=b
    assert loadBars('cn','000001',dataDir=tmp_path).attrs['marketData']['instrumentType']=='stock'
    assert loadBars('cn','sh000001',dataDir=tmp_path).attrs['marketData']['instrumentType']=='index'


def test_metadata_and_native_units_survive_parquet(tmp_path):
    frame=data(adjustment='qfq')
    saveBars(frame,'cn','600519',dataDir=tmp_path,adjusted=True)
    loaded=loadBars('cn','600519',dataDir=tmp_path)
    assert loaded.attrs['marketData']==frame.attrs['marketData']
    assert loaded['volume'].tolist()==frame['volume'].tolist()


@pytest.mark.parametrize('kwargs',[{'source':'baostock'},{'adjustment':'qfq'},{'unit':'share'}])
def test_incompatible_source_adjustment_or_units_cannot_silently_merge(tmp_path,kwargs):
    path=saveBars(data(),'cn','600519',dataDir=tmp_path)
    original=path.read_bytes()
    with pytest.raises(ValueError,match='不能直接拼接'):
        saveBars(data(**kwargs),'cn','600519',dataDir=tmp_path)
    assert path.read_bytes()==original


def test_wrong_symbol_rejected_before_writing(tmp_path):
    with pytest.raises(ValueError,match='身份'):
        saveBars(data(symbol='000001'),'cn','600519',dataDir=tmp_path)
    assert list(tmp_path.rglob('*.parquet'))==[]


def test_legacy_cache_is_backed_up_and_rebuilt_without_guessing_units(tmp_path):
    legacy=makeBars([99.]*5)
    path=saveBars(legacy,'cn','600519',dataDir=tmp_path)
    current=data()
    saveBars(current,'cn','600519',dataDir=tmp_path,adjusted=True)
    assert path.with_suffix('.parquet.bak').exists()
    loaded=loadBars('cn','600519',dataDir=tmp_path)
    assert len(loaded)==3
    assert loaded.attrs['marketData']['source']=='tencent'
    assert loaded.attrs['historyNotice']


def test_comparison_converts_lots_to_shares_and_ignores_derived_fields():
    left=data()
    right=makeBars([100.,101.,102.]);right['volume']*=100;right['turnoverRate']=999
    right=describeBars(right,'cn','600519','day',source='baostock',adjustment='none',volumeUnit='share')
    result=compareDailyBars(left,right)
    assert result['matches'] and result['comparedDates']==3
    assert result['independentSources']
    right.loc[0,'close']=100.5  # 合法OHLC范围内的人为差异。
    result=compareDailyBars(left,right)
    assert not result['matches']
    assert result['differences']==[{'date':'2024-01-01','field':'close','left':100.,'right':100.5}]


def test_same_underlying_source_is_not_independent_validation():
    result=compareDailyBars(data(),data())
    assert result['sameSource'] and not result['independentSources']


def test_adjusted_or_different_instrument_cannot_be_compared():
    with pytest.raises(ValueError,match='不复权'):
        compareDailyBars(data(adjustment='qfq'),data(adjustment='qfq'))
    with pytest.raises(ValueError,match='不是同一标的'):
        compareDailyBars(data(symbol='000001'),data(symbol='sh000001'))


def test_no_shared_date_does_not_report_success():
    left=data()
    right=describeBars(makeBars([100.],start='2024-02-01'),'cn','600519','day',source='baostock',adjustment='none',volumeUnit='lot100')
    assert compareDailyBars(left,right)['matches'] is False


def test_cached_intraday_bar_does_not_become_confirmed_when_clock_advances():
    morning=datetime(2026,9,30,10,tzinfo=ZoneInfo('Asia/Shanghai'))
    frame=describeBars(makeBars([100.,110.],start='2026-09-29'),'cn','600519','day',source='tencent',adjustment='none',volumeUnit='lot100',observedAt=morning)
    evening=morning.replace(hour=18)
    assert str(closedBars(frame,'cn',now=evening).iloc[-1]['date'].date())=='2026-09-29'
    other=describeBars(makeBars([100.,110.],start='2026-09-29'),'cn','600519','day',source='baostock',adjustment='none',volumeUnit='lot100',observedAt=evening)
    assert compareDailyBars(frame,other)['comparedDates']==1


@pytest.mark.parametrize('change',[{'high':99.},{'low':102.},{'volume':-1.},{'close':float('nan')}])
def test_invalid_prices_or_volumes_are_rejected(change):
    frame=makeBars([100.])
    for key,value in change.items():frame.loc[0,key]=value
    with pytest.raises(ValueError):validateBars(frame)


def test_conflicting_duplicate_dates_are_rejected():
    frame=makeBars([100.]);other=frame.copy();other['close']=100.5
    with pytest.raises(ValueError,match='冲突'):
        validateBars(pd.concat([frame,other]))


def test_quote_identity_uses_response_code_not_response_order(monkeypatch):
    from tests.test_tencent_provider import SAMPLE_CN_QUOTE
    first=SAMPLE_CN_QUOTE
    second='v_sh000001="1~上证指数~000001~3000~2999~3001";'
    actual=httpx.Client
    def create(**kwargs):
        return actual(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=(second+first).encode('gbk'))))
    monkeypatch.setattr('app.data.third_party.httpx.Client',create)
    result=TencentProvider('cn').fetchQuotes(['600519','sh000001'])
    assert result['600519']['price']==1237.48
    assert result['sh000001']['price']==3000
    assert result['600519']['volumeUnit']=='lot100'


def test_quote_from_unverified_cache_is_not_merged(monkeypatch):
    import app.api.monitor as monitor
    class Provider:
        def fetchQuotes(self,symbols):
            return {'600519':{'price':120.,'time':'20260930100000','prevClose':100.}}
    monkeypatch.setattr(monitor,'_buildProvider',lambda market, **kwargs:Provider())
    frame=makeBars([100.],start='2026-09-29')
    result=monitor._mergeTodayBar('cn','600519',frame)
    assert len(result)==1 and result['close'].iloc[-1]==100.


def test_snapshot_with_mismatched_previous_close_does_not_mix_adjustment_basis(monkeypatch):
    import app.api.monitor as monitor
    now=datetime(2026,9,30,10,tzinfo=ZoneInfo('Asia/Shanghai'))
    monkeypatch.setattr('app.data.contract.marketNow',lambda market:now)
    monkeypatch.setattr(monitor,'marketNow',lambda market:now)
    class Provider:
        def fetchQuotes(self,symbols):
            return {'600519':{'price':120.,'time':'20260930100000','prevClose':50.}}
    monkeypatch.setattr(monitor,'_buildProvider',lambda market, **kwargs:Provider())
    frame=describeBars(makeBars([100.],start='2026-09-29'),'cn','600519','day',source='tencent',adjustment='qfq',volumeUnit='lot100')
    assert len(monitor._mergeTodayBar('cn','600519',frame))==1


def test_matching_snapshot_is_visible_but_not_confirmed_until_observed_close(monkeypatch):
    import app.api.monitor as monitor
    now=datetime(2026,9,30,18,tzinfo=ZoneInfo('Asia/Shanghai'))
    monkeypatch.setattr('app.data.contract.marketNow',lambda market:now)
    monkeypatch.setattr(monitor,'marketNow',lambda market:now)
    class Provider:
        def fetchQuotes(self,symbols):
            return {'600519':{'price':120.,'open':110.,'high':121.,'low':109.,'volume':1000.,'time':'20260930100000','prevClose':100.}}
    monkeypatch.setattr(monitor,'_buildProvider',lambda market, **kwargs:Provider())
    frame=describeBars(makeBars([100.],start='2026-09-29'),'cn','600519','day',source='tencent',adjustment='qfq',volumeUnit='lot100')
    result=monitor._mergeTodayBar('cn','600519',frame)
    assert len(result)==2 and result.iloc[-1]['close']==120.
    assert len(closedBars(result,'cn',now=now))==1


def test_unlabelled_data_cannot_downgrade_verified_cache(tmp_path):
    path=saveBars(data(),'cn','600519',dataDir=tmp_path)
    original=path.read_bytes()
    with pytest.raises(ValueError,match='缺少来源'):
        saveBars(makeBars([100.]),'cn','600519',dataDir=tmp_path)
    assert path.read_bytes()==original
