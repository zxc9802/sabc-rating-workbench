import httpx

from scripts.probe_server_data import probe, run_rounds


ITEM={'id':'fujian','name':'福建','example':'fujian/search:森林公园'}


def test_probe_requires_rows_not_http_success():
    def fetch(client,query):
        return {'facts':{'rows':[]},'title':'空目录'}
    result=probe(ITEM,1,5,fetcher=fetch)
    assert result['status']=='no_usable_data'


def test_probe_summarizes_real_records_without_saving_values():
    def fetch(client,query):
        return {'facts':{'rows':[{'name':'not-for-report'}],'reported_total':100},
                'title':'目录','locator':'https://example.org/data','period':'2023','limitation':'预览'}
    result=probe(ITEM,1,5,fetcher=fetch)
    assert result['status']=='success' and result['rows']==1
    assert result['reported_total']==100
    assert 'not-for-report' not in str(result)


def test_retry_rounds_finish_other_regions_first():
    calls=[]
    def one(item,attempt,timeout):
        calls.append((item['id'],attempt))
        return {'region':item['id'],'retryable':item['id']=='a','status':'network_error'}
    records=list(run_rounds([{'id':'a'},{'id':'b'}],3,5,probe_fn=one))
    assert calls==[('a',1),('b',1),('a',2),('a',3),('a',4)]
    assert len(records)==5


def test_access_denied_not_retried_and_timeout_retryable():
    def denied(client,query):
        httpx.Response(403,request=httpx.Request('GET','https://example.org')).raise_for_status()
    def timeout(client,query):
        raise httpx.ReadTimeout('timed out')
    assert probe(ITEM,1,5,fetcher=denied)['retryable'] is False
    assert probe(ITEM,1,5,fetcher=denied)['status']=='http_error'
    assert probe(ITEM,1,5,fetcher=timeout)['retryable'] is True
