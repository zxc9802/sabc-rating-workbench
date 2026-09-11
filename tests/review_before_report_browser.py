"""访谈内对抗性审查的界面回归：生成入口只在审查完成后出现，点击后直接出报告。仅使用模拟接口。"""
from copy import deepcopy
from playwright.sync_api import sync_playwright, expect
from sabc.rating import assess, DIMENSIONS, TYPES
from tests.test_rating import case

p,c,e,proposal=case(2)
p.update(id='qa-project',name='审查前置验收项目',messages=[{'role':'user','content':'最后的信息已补充'}],updated_at='2026-09-11T00:00:00Z',version=1)
result=assess(p,c,e,proposal)
report={'id':'qa-report','project_id':p['id'],'created_at':'2026-09-11T00:00:00Z','result':result,'snapshot':{'company':c,'project':p,'proposal':proposal,'evidence':e}}


def fixture(review_complete,report_ready):
    project=deepcopy(p)
    project.update(review_complete=review_complete,report_ready=report_ready)
    project['lifecycle']={'stage':'pre','mode':'continuous','confirmed':True,
                          'coverage':{k:{'status':'known','reason':'已提供'} for k in DIMENSIONS}}
    return {'bootstrap':{'projects':[project],'company':c,
                         'dimensions':[{'key':k,'name':n,'weight':w} for k,(n,w) in DIMENSIONS.items()],
                         'types':TYPES,'settings':{'configured':True},'sources':[],'rule_version':'test'},
            'detail':{'project':project,'assessments':[],'evidence':e,'active_jobs':[]}}


def run(page,review_complete,report_ready,closing_outcome):
    current=fixture(review_complete,report_ready)
    jobs={};requests=[]
    def route(r):
        path=r.request.url.split('/api')[-1]
        if path=='/auth/session': data={'authenticated':True,'required':False}
        elif path=='/bootstrap': data=current['bootstrap']
        elif path=='/projects/qa-project': data={**current['detail'],'active_jobs':[j for j in jobs.values() if j['status']=='running']}
        elif path=='/projects/qa-project/jobs':
            body=r.request.post_data_json;requests.append(body)
            data={'id':body['id'],'project_id':'qa-project','generate_report':body['payload'].get('generate_report',False),'status':'running'}
            jobs[data['id']]=data
        elif path.startswith('/jobs/'):
            data=jobs[path.split('/')[-1]]
            if data['status']=='running':
                if closing_outcome=='questions':
                    # 审查轮发现新的可答缺口：回到访谈，不出现生成入口。
                    data.update(status='success',result={'questions':['还需要确认每月租金？']})
                else:
                    current['detail']['assessments']=[report]
                    data.update(status='success',result={'report_id':'qa-report'})
            r.fulfill(json=data);return
        elif '/reports/' in path: data={'turns':[],'active_job':None}
        else: data={}
        r.fulfill(json=data)
    page.route('**/api/**',route)
    page.add_init_script("sessionStorage.setItem('sabc-project','qa-project')")
    page.goto('http://127.0.0.1:3000');page.wait_for_load_state('networkidle');page.wait_for_timeout(600)
    generate=page.get_by_role('button',name='生成报告',exact=True)
    if closing_outcome=='questions':
        # 审查还没完成时，只能继续核对，没有生成入口。
        expect(generate).to_have_count(0)
        expect(page.get_by_role('button',name='继续核对',exact=True)).to_be_visible()
        page.get_by_role('button',name='继续核对',exact=True).click()
        page.wait_for_timeout(1200)
        expect(page.get_by_role('button',name='生成报告',exact=True)).to_have_count(0)
        assert requests and requests[0]['payload'].get('generate_report') is not True
        assert current['detail']['assessments']==[]
        print('PASS 审查未完成：只有继续核对，没有生成入口')
    else:
        # 审查已在访谈内完成：出现生成报告与继续补充，点击后直接出报告。
        expect(page.get_by_role('button',name='生成报告',exact=True)).to_be_visible()
        expect(page.get_by_role('button',name='继续补充',exact=True)).to_be_visible()
        page.get_by_role('button',name='生成报告',exact=True).click()
        expect(page.get_by_role('tab',name='历史报告与建议')).to_have_attribute('aria-selected','true')
        expect(page.locator('.rating-document')).to_be_visible()
        assert len(requests)==1 and requests[0]['payload']['generate_report'] is True
        print('PASS 审查已完成：点击生成直接出报告')


with sync_playwright() as playwright:
    browser=playwright.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    run(page,False,False,'questions')
    assert not errors,errors
    page.close()
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.on('pageerror',lambda e:errors.append(str(e)))
    run(page,True,True,'report')
    assert not errors,errors
    page.close()
    browser.close()
print('PASS 访谈内审查前置界面回归')
