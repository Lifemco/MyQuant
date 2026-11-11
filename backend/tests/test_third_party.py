"""统一配置、SDK边界、下载和缓存切换回归。上游响应由测试固定。"""
import copy
import io
import socket
import sys
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.data import third_party as integrations
from app.data.contract import describeBars
from app.data.sdk_provider import SDKProvider
from app.data.store import loadBars, saveBars
from app.main import app
from tests.conftest import makeBars

client=TestClient(app,raise_server_exceptions=False)


def akFrame():
    return pd.DataFrame({'日期':['2024-01-01','2024-01-02','2024-01-03'], '开盘':[100.,101.,102.],
                         '最高':[101.,102.,103.], '最低':[99.,100.,101.], '收盘':[100.,101.,102.], '成交量':[10.,20.,30.]})


@pytest.fixture
def ak(monkeypatch):
    calls=[]
    state={'timeout':99}
    def history(**kwargs): calls.append(kwargs);return akFrame()
    sdk=SimpleNamespace(get_timeout=lambda:state['timeout'], set_timeout=lambda value:state.update(timeout=value),
                        stock_zh_a_hist=history,stock_hk_hist=history,index_zh_a_hist=history)
    monkeypatch.setitem(sys.modules,'akshare',sdk)
    return sdk,calls,state


@pytest.mark.parametrize('market,symbol,kind,unit',[('cn','600519','stock','lot100'),('hk','00700','stock','share'),('cn','sh000001','index','lot100')])
def test_akshare_normalizes_market_and_distinguishes_index(ak,market,symbol,kind,unit):
    sdk,calls,state=ak
    df=SDKProvider(market,'akshare','none').fetchDailyBars(symbol,'2024-01-02','2024-01-03')
    assert len(df)==2 and list(df['close'])==[101.,102.]
    assert calls[0]['symbol']==('000001' if kind=='index' else symbol)
    assert calls[0]['start_date']=='20240102' and calls[0]['end_date']=='20240103'
    if kind=='index': assert 'adjust' not in calls[0]
    else: assert calls[0]['adjust']==''
    assert df.attrs['marketData']['source']=='eastmoney'
    assert df.attrs['marketData']['adapter']=='akshare'
    assert df.attrs['marketData']['volumeUnit']==unit
    assert state['timeout']==99


def test_akshare_period_and_adjustment_mapping(ak):
    _,calls,_=ak
    SDKProvider('cn','akshare','hfq').fetchDailyBars('600519','2024-01-01','2024-01-03',period='week')
    assert calls[0]['period']=='weekly' and calls[0]['adjust']=='hfq'


def test_akshare_failure_restores_timeout_and_returns_502(ak,monkeypatch):
    sdk,_,state=ak
    def fail(**kwargs):raise httpx.ProxyError('403 Forbidden')
    sdk.stock_zh_a_hist=fail
    r=client.post('/api/data/download',json=payload())
    assert r.status_code==502 and '403 Forbidden' in r.json()['detail']
    assert state['timeout']==99


def payload(**kwargs):
    return {'market':'cn','symbol':'600519','source':'akshare','startDate':'2024-01-01','endDate':'2024-01-03','adjustment':'none',**kwargs}


def test_download_json_and_csv_keep_conventions_without_writing_cache(ak,tmp_path,monkeypatch):
    import app.data.store as store
    monkeypatch.setattr(store,'DATA_DIR',tmp_path)
    response=client.post('/api/data/download',json=payload())
    assert response.status_code==200
    body=response.json()
    assert len(body['bars'])==3 and body['dataInfo']['adjustment']=='none'
    assert 'attachment' in response.headers['content-disposition']
    response=client.post('/api/data/download?format=csv',json=payload())
    frame=pd.read_csv(io.BytesIO(response.content))
    assert frame['meta_source'].eq('eastmoney').all()
    assert frame['meta_volumeUnit'].eq('lot100').all()
    assert frame['meta_adapter'].eq('akshare').all()
    assert list(tmp_path.rglob('*.parquet'))==[]


def test_source_change_requires_explicit_backed_up_replacement(ak,tmp_path,monkeypatch):
    import app.data.store as store
    monkeypatch.setattr(store,'DATA_DIR',tmp_path)
    old=describeBars(makeBars([100.,101.]),'cn','600519','day',source='tencent',adjustment='none',volumeUnit='lot100')
    path=saveBars(old,'cn','600519',dataDir=tmp_path)
    original=path.read_bytes()
    denied=client.post('/api/data/fetch',json=payload())
    assert denied.status_code==422 and path.read_bytes()==original
    accepted=client.post('/api/data/fetch',json=payload(replaceCache=True))
    assert accepted.status_code==200
    assert loadBars('cn','600519',dataDir=tmp_path).attrs['marketData']['source']=='eastmoney'
    assert path.with_suffix('.parquet.bak').read_bytes()==original


def test_configuration_changes_sdk_method_without_adapter_edits(ak,monkeypatch):
    sdk,_,_=ak
    calls=[]
    sdk.custom_daily=lambda **kwargs:(calls.append(kwargs) or akFrame())
    monkeypatch.setitem(integrations.PROVIDERS['akshare']['methods'],'cn_stock','custom_daily')
    SDKProvider('cn','akshare','none').fetchDailyBars('600519','2024-01-01','2024-01-03')
    assert len(calls)==1


def test_history_default_and_quote_default_are_independent(monkeypatch):
    monkeypatch.setitem(integrations.DEFAULT_PROVIDERS['history'],'cn','akshare')
    assert integrations.makeProvider('cn').source=='akshare'
    assert type(integrations.makeProvider('cn',operation='quotes')).__name__=='TencentProvider'
    response=client.get('/api/data/providers')
    assert response.status_code==200
    assert {item['id'] for item in response.json()}=={'tencent','yahoo','akshare','baostock'}
    assert 'host' not in response.text and 'password' not in response.text


@pytest.mark.parametrize('market,source',[('us','akshare'),('hk','baostock')])
def test_unsupported_market_rejected_without_sdk_request(market,source):
    response=client.post('/api/data/download',json=payload(market=market,source=source,symbol='AAPL' if market=='us' else '00700'))
    assert response.status_code==422


def test_index_rejects_stock_adjustment_and_unknown_source():
    response=client.post('/api/data/download',json=payload(symbol='sh000001',adjustment='qfq'))
    assert response.status_code==422
    response=client.post('/api/data/download',json=payload(source='unknown'))
    assert response.status_code==422


def test_disabled_source_rejected(monkeypatch):
    monkeypatch.setitem(integrations.PROVIDERS['akshare'],'enabled',False)
    assert client.post('/api/data/download',json=payload()).status_code==422


def test_tencent_url_and_timeout_are_managed_in_one_file(monkeypatch):
    settings=integrations.PROVIDERS['tencent']
    monkeypatch.setitem(settings['urls'],'history','https://configured.example/klines')
    monkeypatch.setitem(settings['timeouts'],'history',7)
    actual=httpx.Client
    seen=[]
    def factory(**kwargs):
        seen.append(kwargs)
        return actual(transport=httpx.MockTransport(lambda request:(seen.append(str(request.url)) or httpx.Response(200,json={'data':{}}))))
    monkeypatch.setattr(integrations.httpx,'Client',factory)
    integrations.tencentHistory('sh600519','2024-01-01','2024-01-03','day','none')
    assert seen[0]['timeout']==7 and seen[0]['trust_env'] is True
    assert seen[1].startswith('https://configured.example/klines?')


class Result:
    error_code='0'
    error_msg=''
    fields=['date','code','open','high','low','close','volume']
    def __init__(self): self.rows=iter([['2024-01-02','sh.600519','100','101','99','100','1000']])
    def next(self):
        self.row=next(self.rows,None)
        return self.row is not None
    def get_row_data(self):return self.row


@pytest.fixture
def bao(monkeypatch):
    calls=[]
    sdk=SimpleNamespace(login=lambda:SimpleNamespace(error_code='0',error_msg=''),
        logout=lambda:calls.append(('logout',)),
        query_history_k_data_plus=lambda *a,**kw:(calls.append((a,kw)) or Result()))
    constants=SimpleNamespace(BAOSTOCK_SERVER_IP='old',BAOSTOCK_SERVER_PORT=0)
    monkeypatch.setitem(sys.modules,'baostock',sdk)
    monkeypatch.setitem(sys.modules,'baostock.common.contants',constants)
    return sdk,calls,constants


def test_baostock_code_frequency_adjustment_and_logout(bao):
    _,calls,constants=bao
    before=socket.getdefaulttimeout()
    result=integrations.runBaostock(integrations.PROVIDERS['baostock'],'600519','2024-01-01','2024-01-03','day','qfq')
    args,kwargs=calls[0]
    assert args[0]=='sh.600519' and 'tradestatus' in args[1]
    assert kwargs['frequency']=='d' and kwargs['adjustflag']=='2'
    assert calls[-1]==('logout',) and len(result)==1
    assert constants.BAOSTOCK_SERVER_IP==integrations.PROVIDERS['baostock']['host']
    assert socket.getdefaulttimeout()==before


def test_baostock_failure_still_logs_out(bao):
    sdk,calls,_=bao
    sdk.query_history_k_data_plus=lambda *a,**kw:SimpleNamespace(error_code='1',error_msg='query failed')
    with pytest.raises(RuntimeError,match='query failed'):
        integrations.runBaostock(integrations.PROVIDERS['baostock'],'600519','2024-01-01','2024-01-03','day','none')
    assert calls[-1]==('logout',)


def test_baostock_failed_login_does_not_query(bao):
    sdk,calls,_=bao
    sdk.login=lambda:SimpleNamespace(error_code='1',error_msg='login failed')
    with pytest.raises(RuntimeError,match='login failed'):
        integrations.runBaostock(integrations.PROVIDERS['baostock'],'600519','2024-01-01','2024-01-03','day','none')
    assert calls==[]


def test_baostock_index_uses_no_stock_only_fields(bao):
    sdk,calls,_=bao
    class IndexResult(Result):
        def __init__(self): self.rows=iter([['2024-01-02','sh.000001','3000','3001','2999','3000','1000']])
    sdk.query_history_k_data_plus=lambda *a,**kw:(calls.append((a,kw)) or IndexResult())
    integrations.runBaostock(integrations.PROVIDERS['baostock'],'sh000001','2024-01-01','2024-01-03','month','none')
    args,kwargs=calls[0]
    assert args[0]=='sh.000001' and 'tradestatus' not in args[1]
    assert kwargs['frequency']=='m' and kwargs['adjustflag']=='3'


def test_baostock_timeout_terminates_child(monkeypatch):
    events=[]
    class Process:
        pid=1
        def start(self):events.append('start')
        def is_alive(self):return 'terminate' not in events
        def terminate(self):events.append('terminate')
        def join(self,timeout=None):events.append('join')
    receiver=SimpleNamespace(poll=lambda timeout:False,close=lambda:None)
    sender=SimpleNamespace(close=lambda:None)
    context=SimpleNamespace(Pipe=lambda **kw:(receiver,sender),Process=lambda **kw:Process())
    monkeypatch.setattr(integrations.multiprocessing,'get_context',lambda kind:context)
    with pytest.raises(TimeoutError,match='超时'):
        integrations.baostockHistory('600519','2024-01-01','2024-01-03','day','none')
    assert 'terminate' in events


def test_baostock_normalizes_shares_and_excludes_only_explicit_suspensions(monkeypatch):
    raw=pd.DataFrame({'date':['2024-01-01','2024-01-02'],'code':['sh.600519']*2,
        'open':['100',''],'high':['101',''],'low':['99',''],'close':['100',''],'volume':['1000','0'],'tradestatus':['1','0']})
    monkeypatch.setattr(integrations,'baostockHistory',lambda *a,**kw:raw)
    df=SDKProvider('cn','baostock','none').fetchDailyBars('600519','2024-01-01','2024-01-03')
    assert len(df)==1 and df['volume'].iloc[0]==1000
    assert df.attrs['marketData']['volumeUnit']=='share'
    assert df.attrs['marketData']['excludedSuspendedRows']==1


def test_new_named_source_can_be_registered_in_the_single_management_file(ak,monkeypatch):
    settings=copy.deepcopy(integrations.PROVIDERS['akshare'])
    settings['label']='AKShare备用配置'
    sdk,calls,_=ak
    sdk.alias_download=lambda **kw:(calls.append('alias') or akFrame())
    settings['methods']['cn_stock']='alias_download'
    monkeypatch.setitem(integrations.PROVIDERS,'ak_alternative',settings)
    response=client.post('/api/data/download',json=payload(source='ak_alternative'))
    assert response.status_code==200
    assert 'alias' in calls
    assert response.json()['dataInfo']['adapter']=='ak_alternative'
    assert response.json()['dataInfo']['source']=='eastmoney'


def test_history_only_sdk_cannot_be_configured_as_quote_provider():
    with pytest.raises(ValueError,match='未接入quotes'):
        integrations.makeProvider('cn',source='akshare',operation='quotes')
