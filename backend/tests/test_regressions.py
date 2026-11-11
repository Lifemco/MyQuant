"""审查发现的成交、信号确认、输入边界与持久化回归用例。"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from threading import Barrier
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.backtest.engine import runBacktest
from app.backtest.metrics import computeMetrics
from app.backtest.strategies import getStrategy
from app.data.store import loadBars, saveBars, listSymbols
from app.main import app
from app.monitor.session import closedBars
from app.watchlist.store import addWatchItem, loadWatchlist
from tests.conftest import makeBars

client = TestClient(app, raise_server_exceptions=False)


class Fixed:
    def __init__(self, signals): self.signals = signals
    def generateSignals(self, bars): return pd.Series(self.signals, index=bars['date'].values)


def test_buy_does_not_earn_gap_before_execution_and_sell_keeps_overnight_gain():
    bars = makeBars([100., 110., 120.])
    bars['open'] = [100., 110., 120.]
    result = runBacktest(bars, Fixed([1, 0, 0]), feeRate=0)
    assert result['equityCurve'][1]['equity'] == pytest.approx(1)
    assert result['equityCurve'][-1]['equity'] == pytest.approx(120 / 110)
    assert result['trades'][0]['entryPrice'] == 110
    assert result['trades'][0]['exitPrice'] == 120
    assert result['trades'][0]['pnlPct'] == pytest.approx(120 / 110 - 1)
    assert result['metrics']['winRate'] == 1


def test_round_trip_charges_one_fee_per_fill_and_never_borrows_cash():
    bars = makeBars([100.] * 3); bars['open'] = 100.
    result = runBacktest(bars, Fixed([1, 0, 0]), feeRate=.001)
    # 现金1购买股票及支付佣金，卖出再扣一次佣金。
    expected = (1 - .001) / (1 + .001)
    assert result['equityCurve'][-1]['equity'] == pytest.approx(expected, abs=1e-8)
    assert result['trades'][0]['pnlPct'] == pytest.approx(expected - 1, abs=1e-8)


def test_trade_includes_entry_day_return_and_open_trades_do_not_count_as_wins():
    bars = makeBars([100., 110., 110.]); bars['open'] = [100., 100., 110.]
    result = runBacktest(bars, Fixed([1, 0, 0]), feeRate=0)
    assert result['trades'][0]['pnlPct'] == pytest.approx(.1)
    assert result['metrics']['winRate'] == 1
    opened = runBacktest(bars, Fixed([1, 1, 1]), feeRate=0)
    assert opened['trades'][0]['exitDate'] is None
    assert opened['trades'][0]['pnlPct'] == pytest.approx(.1)
    assert opened['metrics']['winRate'] == 0


def test_sharpe_uses_daily_excess_mean_and_short_history_is_finite():
    equity = pd.Series([1., 1.1, 1.], index=pd.bdate_range('2024-01-01', periods=3))
    returns = equity.pct_change().dropna()
    expected = (returns.mean() - .02 / 252) / returns.std() * np.sqrt(252)
    result = computeMetrics(equity, pd.Series([0, 1, 1], index=equity.index))
    assert result['sharpeRatio'] == pytest.approx(expected, abs=1e-4)
    short = computeMetrics(equity.iloc[:2], pd.Series([0, 1], index=equity.index[:2]))
    assert all(np.isfinite(value) for value in short.values())


@pytest.mark.parametrize('market,zone,close', [('cn','Asia/Shanghai','15:00'), ('hk','Asia/Hong_Kong','16:10'), ('us','America/New_York','16:00')])
def test_unclosed_day_does_not_generate_confirmed_signal(market, zone, close):
    bars = makeBars([100.] * 30 + [120.], start='2026-08-19')
    assert str(bars.iloc[-1].date.date()) == '2026-09-30'
    early = datetime(2026,9,30,10,0,tzinfo=ZoneInfo(zone))
    assert len(closedBars(bars, market, now=early)) == 30
    hour, minute = map(int, close.split(':'))
    late = early.replace(hour=hour,minute=minute)
    assert len(closedBars(bars, market, now=late)) == 31
    # 以UTC传入同一瞬间仍应得到相同结果。
    assert len(closedBars(bars, market, now=early.astimezone(ZoneInfo('UTC')))) == 30


def test_incomplete_week_month_excluded():
    bars = makeBars([100.], start='2026-09-30')
    now = datetime(2026,9,30,10,0,tzinfo=ZoneInfo('Asia/Shanghai'))
    assert closedBars(bars,'cn','month',now).empty
    assert closedBars(bars,'cn','week',now).empty
    assert len(closedBars(bars,'cn','month',now.replace(hour=16))) == 1


def test_chart_shows_in_progress_bar_but_signals_use_only_closed_bars(monkeypatch):
    import app.api.monitor as monitor
    bars = makeBars([100.]*30+[120.], start='2026-08-19')
    monkeypatch.setattr(monitor,'loadBars',lambda *a,**kw:bars)
    monkeypatch.setattr(monitor,'_mergeTodayBar',lambda m,s,b:b)
    monkeypatch.setattr('app.monitor.session.marketNow',lambda m:datetime(2026,9,30,10,tzinfo=ZoneInfo('Asia/Shanghai')))
    response=client.post('/api/monitor/chart',json={'market':'cn','symbol':'600519','strategy':'sma_cross'})
    assert response.status_code==200
    data=response.json()
    assert len(data['bars'])==31
    assert data['holding'] is False and data['markers']==[]
    assert data['signalAsOf']=='2026-09-29'


@pytest.mark.parametrize('params',[{'window':0},{'window':2.5},{'window':True},{'window':None},{'typo':14}])
def test_invalid_strategy_bindings_rejected_without_changing_file(tmp_path,monkeypatch,params):
    import app.watchlist.store as store
    monkeypatch.setattr(store,'DATA_DIR',tmp_path)
    addWatchItem('cn','600519',dataDir=tmp_path)
    before=(tmp_path/'watchlist.json').read_bytes()
    response=client.put('/api/watchlist/cn/600519',json={'strategy':'rsi_reversion','params':params})
    assert response.status_code==422
    assert (tmp_path/'watchlist.json').read_bytes()==before


@pytest.mark.parametrize('symbol',['../../outside','/tmp/file','..\\file','   '])
def test_traversal_and_empty_symbols_are_rejected(symbol,tmp_path):
    response=client.post('/api/backtest/run',json={'market':'cn','symbol':symbol,'strategy':'sma_cross'})
    assert response.status_code==422
    with pytest.raises(ValueError): loadBars('cn',symbol,dataDir=tmp_path)


def test_symlink_cannot_escape_data_root(tmp_path):
    root=tmp_path/'data'; root.mkdir()
    outside=tmp_path/'outside'; outside.mkdir()
    (root/'cn').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError): saveBars(makeBars([1.]),'cn','600519',dataDir=root)
    assert list(outside.iterdir())==[]


def test_concurrent_watchlist_updates_preserved(tmp_path):
    barrier=Barrier(12)
    def add(i):
        barrier.wait()
        addWatchItem('cn',f'{i:06}',dataDir=tmp_path)
    with ThreadPoolExecutor(12) as pool: list(pool.map(add,range(12)))
    assert len(loadWatchlist(tmp_path))==12


def test_adjustment_change_rebuilds_one_basis_and_backs_up_history(tmp_path):
    old=makeBars([100.]*4)
    new=makeBars([50.]*2,start='2024-01-03')
    path=saveBars(old,'cn','600519',dataDir=tmp_path,adjusted=True)
    saveBars(new,'cn','600519',dataDir=tmp_path,adjusted=True)
    cached=loadBars('cn','600519',dataDir=tmp_path)
    assert list(cached['close'])==[50.,50.]
    assert cached.attrs['historyNotice']
    assert list(pd.read_parquet(path.with_suffix('.parquet.bak'))['close'])==[100.]*4


def test_live_last_bar_revision_does_not_discard_history(tmp_path):
    old=makeBars([100.]*4)
    saveBars(old,'cn','600519',dataDir=tmp_path,adjusted=True)
    saveBars(makeBars([110.],start='2024-01-04'),'cn','600519',dataDir=tmp_path,adjusted=True)
    assert list(loadBars('cn','600519',dataDir=tmp_path)['close'])==[100.,100.,100.,110.]


def test_dotted_us_ticker_is_listed(tmp_path):
    saveBars(makeBars([100.]),'us','BRK.B',dataDir=tmp_path)
    assert listSymbols(tmp_path)[0]['symbol']=='BRK.B'


def test_refresh_includes_cached_periods_and_reports_failures(tmp_path,monkeypatch):
    import app.data.store as store
    import app.watchlist.store as watchstore
    import app.api.monitor as monitor
    monkeypatch.setattr(store,'DATA_DIR',tmp_path)
    monkeypatch.setattr(watchstore,'DATA_DIR',tmp_path)
    addWatchItem('cn','600519',dataDir=tmp_path)
    for period in ('day','week','month'): saveBars(makeBars([100.]),'cn','600519',period,dataDir=tmp_path)
    calls=[]
    class Provider:
        def fetchDailyBars(self,s,start,end,period='day'):
            calls.append(period)
            if period=='month':raise RuntimeError('source unavailable')
            return makeBars([100.,110.])
    monkeypatch.setattr(monitor,'_buildProvider',lambda m:Provider())
    response=client.post('/api/monitor/refresh')
    assert response.status_code==200
    result=response.json()[0]
    assert calls==['day','week','month']
    assert 'source unavailable' in result['refreshError']
    assert result['refreshedAt'] is None
    assert len(loadBars('cn','600519','week',tmp_path))==2


def test_invalid_persisted_strategy_is_visible_and_does_not_break_overview(tmp_path,monkeypatch):
    import app.data.store as store
    import app.api.monitor as monitor
    monkeypatch.setattr(store,'DATA_DIR',tmp_path)
    saveBars(makeBars([100.]*30),'cn','600519',dataDir=tmp_path)
    monkeypatch.setattr(monitor,'loadWatchlist',lambda:[{'market':'cn','symbol':'600519','name':'test','strategy':'rsi_reversion','params':{'window':0}}])
    result=client.get('/api/monitor/overview')
    assert result.status_code==200
    assert result.json()[0]['error']


def test_us_quote_placeholder_is_explicit():
    response=client.post('/api/monitor/quotes',json={'items':[{'market':'us','symbol':'AAPL'}]})
    assert response.status_code==200
    assert response.json()[0]['symbol']=='AAPL'
    assert response.json()[0]['price'] is None


def test_upstream_minute_date_is_not_replaced_by_server_today():
    from app.data.tencent_provider import TencentProvider
    assert TencentProvider._minuteTradeDate({'data':{'date':'20260930'}},'sh600519')=='2026-09-30'
    assert TencentProvider._minuteTradeDate({},'sh600519')==''


def test_fetch_dates_are_real_and_ordered():
    from app.schemas.api import FetchBarsRequest
    for start,end in [('2026-02-30','2026-03-01'),('2026-10-01','2026-09-01')]:
        with pytest.raises(ValueError): FetchBarsRequest(market='cn',symbol='600519',startDate=start,endDate=end)


def test_yahoo_end_date_is_inclusive(monkeypatch):
    import sys
    from types import SimpleNamespace
    from app.data.yfinance_provider import YFinanceProvider
    calls=[]
    def download(*args,**kwargs):
        calls.append(kwargs)
        return pd.DataFrame()
    monkeypatch.setitem(sys.modules,'yfinance',SimpleNamespace(download=download))
    YFinanceProvider().fetchDailyBars('AAPL','2026-09-01','2026-09-30')
    assert calls[0]['end']=='2026-10-01'
