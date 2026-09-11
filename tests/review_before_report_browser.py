"""访谈内对抗性审查的界面回归：入口出现时机、点击后不再核对、失败可重试。仅使用模拟接口。"""
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
    return {'bootstrap':{'projects':[project],'company':c,'dimensions':[{'key':k,'name':n,'weight':w} for k,(n,w) in DIMENSIONS.items()],'types':TYPES,'settings':{'configured':True},'sources':[],'rule_version':'test'},
            'detail':{'project':project,'assessments':[],'evidence':e,'active_jobs':[]}}

def run(page,state,outcome):
    current=fixture(*state)
    project=current['detail']['project']
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
            # 审查在访谈轮内完成：这一轮只补齐缺口，不出现生成入口。
            if outcome=='none' and data['status']=='running':
                data.update(status='success',result={'questions':['还需要确认每月租金？']})
            elif outcome=='review_failed' and data['status']=='running':
                data.update(status='failed',error='独立审查响应无效，请重试')
            elif outcome=='done' and data['status']=='running':
                current['detail']['assessments']=[report]
                data.update(status='success',result={'report_id':'qa-report'})
            r.fulfill(json=data);return
        elif '/reports/' in path: data={'turns':[],'active_job':None}
        else: data={}
        r.fulfill(json=data)
    page.route('**/api/**',route)
    page.add_init_script("sessionStorage.setItem('sabc-project','qa-project')")
    page.goto('http://127.0.0.1:3000');page.wait_for_load_state('networkidle')
    page.wait_for_timeout(500)
    generate=page.get_by_role('button',name='生成报告',exact=True)
    # 审查未完成时，生成入口不能出现，只能继续核对。
    if outcome!='done':
        expect(generate).to_have_count(0)
    if state==(False,False):
        expect(page.get_by_role('button',name='继续核对',exact=True)).to_be_visible()
        page.get_by_role('button',name='继续核对',exact=True).click()
        page.wait_for_timeout(500)
        print('  debug buttons:', [t for t in page.locator('button').all_inner_texts() if t.strip()])
        print('  debug requests:', requests)
        expect(page.get_by_role('button',name='生成报告',exact=True)).to_have_count(0)
        assert requests and requests[0]['payload'].get('generate_report') is not True
        print('PASS 审查未完成时无生成入口')
    elif outcome=='review_failed':
        expect(page.get_by_role('button',name='生成报告',exact=True)).to_be_visible()
        page.get_by_role('button',name='生成报告',exact=True).click()
        expect(page.get_by_text('独立审查响应无效，请重试',exact=True)).to_be_visible()
        expect(page.get_by_role('button',name='重试生成报告',exact=True)).to_be_visible()
        assert current['detail']['assessments']==[]
        print('PASS 生成失败不保存报告并可重试')
    else:
        expect(page.get_by_role('button',name='生成报告',exact=True)).to_be_visible()
        expect(page.get_by_role('button',name='继续补充',exact=True)).to_be_visible()
        page.get_by_role('button',name='生成报告',exact=True).click()
        expect(page.get_by_role('tab',name='历史报告与建议')).to_have_attribute('aria-selected','true')
        expect(page.locator('.rating-document')).to_be_visible()
        assert len(requests)==1 and requests[0]['payload']['generate_report'] is True
        print('PASS 点击生成直接出报告')

with sync_playwright() as playwright:
    browser=playwright.chromium.launch(headless=True)
    for state,outcome,label in [((False,False),'none','未审查'),((True,True),'done','已审查'),((True,True),'review_failed','生成失败')]:
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        run(page,state,outcome)
        assert not errors,errors
        print('  ->',label)
        page.close()
    browser.close()
print('PASS 访谈内审查前置界面回归')
