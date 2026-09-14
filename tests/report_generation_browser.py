"""Browser regression for two-stage reporting, private drafts and recovery. Mock APIs only."""
from tests.report_fixtures import checkpoint_items
from copy import deepcopy
import os
from playwright.sync_api import sync_playwright, expect
from sabc.rating import assess, DIMENSIONS, TYPES
from tests.test_rating import case
p,c,e,proposal=case(2)
p.update(id='qa-project',name='报告助手验收项目',messages=[{'role':'assistant','content':'本地界面验收记录'}],updated_at='2026-09-11T00:00:00Z',version=1)
result=assess(p,c,e,proposal)
r={'id':'qa-report','project_id':p['id'],'created_at':'2026-09-11T00:00:00Z','result':result,'snapshot':{'company':c,'project':p,'proposal':proposal,'evidence':e}}
r2={**r,'id':'qa-old','created_at':'2026-09-10T00:00:00Z'}
fixture={'bootstrap':{'projects':[p],'company':c,'dimensions':[{'key':k,'name':n,'weight':w} for k,(n,w) in DIMENSIONS.items()],'types':TYPES,'settings':{'configured':True},'sources':[],'rule_version':'test'},'detail':{'project':p,'assessments':[r,r2],'evidence':e}}

with sync_playwright() as playwright:
    browser=playwright.chromium.launch(headless=True)
    for outcome in ('success','failure','ask','review_failure','supplement'):
        page=browser.new_page(viewport={'width':1440,'height':1000})
        current=deepcopy(fixture)
        project=current['detail']['project']
        project.update(report_ready=False,analysis_complete=False,report_pipeline=None,proposal=None)
        project['lifecycle']={'stage':'pre','mode':'continuous','confirmed':True,'coverage':{d['key']:{'status':'known','reason':'已提供','items':checkpoint_items(d['key'])} for d in current['bootstrap']['dimensions']}}
        project['messages']=[{'role':'user','content':'已有八维资料'},{'role':'assistant','content':'持证代理的费用能退多少？'}]
        project['interview']={'state':'gathering','questions':['持证代理的费用能退多少？']}
        current['detail']['assessments']=[]
        jobs={};requests=[];step='interview'
        def route(route):
            path=route.request.url.split('/api')[-1]
            if path=='/auth/session': data={'authenticated':True,'required':False}
            elif path=='/bootstrap': data=current['bootstrap']
            elif path=='/projects/qa-project': data={**current['detail'],'active_jobs':[j for j in jobs.values() if j['status']=='running']}
            elif path=='/projects/qa-project/jobs':
                body=route.request.post_data_json;requests.append(body)
                data={'id':body['id'],'project_id':'qa-project','operation':'chat','generate_report':body['payload'].get('generate_report',False),'status':'running','phase':'working'}
                jobs[data['id']]=data
            elif path.startswith('/jobs/'):
                data=jobs[path.split('/')[-1]]
                if data['status']=='running' and step!='interview':
                    if outcome=='failure':data.update(status='failed',error='回答失败，请重试')
                    elif outcome=='ask' or step=='supplement':
                        project.update(report_ready=False,report_pipeline=None)
                        project['messages'].append({'role':'assistant','content':'每月租金多少？'})
                        project['interview']={'state':'gathering','questions':['每月租金多少？']}
                        data.update(status='success',result={'questions':['每月租金多少？']})
                    else:
                        project.update(report_ready=True,analysis_complete=True,report_pipeline={'step':step})
                        project['interview']={'state':'ready','questions':[]}
                        if step=='failed':
                            project['report_pipeline']={'step':'revising'}
                            data.update(status='failed',error='报告审查未完成，可继续审查')
                        elif step=='complete':
                            current['detail']['assessments']=[r]
                            project['report_pipeline']['report_id']='qa-report'
                            data.update(status='success',result={'report_id':'qa-report'})
                data={**data,'collection':{'lifecycle':project['lifecycle'],'report_ready':project['report_ready'],'report_pipeline':project['report_pipeline']}}
            elif '/reports/' in path: data={'turns':[],'active_job':None}
            else:data={}
            route.fulfill(json=data)
        page.route('**/api/**',route)
        page.add_init_script("sessionStorage.setItem('sabc-project','qa-project')")
        page.goto(os.getenv('SABC_TEST_UI_ORIGIN','http://127.0.0.1:3000'))
        expect(page.get_by_text('持证代理的费用能退多少？',exact=True)).to_be_visible()
        expect(page.get_by_text('第一阶段 · 正常问答',exact=True)).to_be_visible()
        expect(page.get_by_text('第二阶段 · 审查',exact=True)).to_be_visible()
        page.locator('#message').fill('可以退一半，其余信息已说明')
        page.get_by_role('button',name='发送消息',exact=True).click()
        expect(page.get_by_text('正在思考…',exact=True)).to_be_visible()
        step='preparing'
        if outcome=='failure':
            expect(page.get_by_role('button',name='重试回答',exact=True)).to_be_visible()
        elif outcome=='ask':
            expect(page.get_by_text('每月租金多少？',exact=True)).to_be_visible()
        else:
            expect(page.locator('.thinking')).to_contain_text('正在整理报告')
            assert not current['detail']['assessments'] and not project['proposal']
            step='reviewing'
            expect(page.locator('.thinking')).to_contain_text('第二阶段：报告审查中')
            page.reload()
            expect(page.locator('.thinking')).to_contain_text('第二阶段：报告审查中')
            page.get_by_role('tab',name='历史报告与建议').click()
            expect(page.get_by_text('报告尚未生成',exact=True)).to_be_visible()
            page.get_by_role('tab',name='项目访谈').click()
            step='revising'
            expect(page.locator('.thinking')).to_contain_text('第二阶段：审查修订中')
            if outcome=='review_failure':
                step='failed'
                expect(page.get_by_role('button',name='继续审查',exact=True)).to_be_visible()
                page.reload()
                expect(page.get_by_role('button',name='继续审查',exact=True)).to_be_visible()
                step='complete'
                page.get_by_role('button',name='继续审查',exact=True).click()
            else:step='complete'
            expect(page.get_by_role('tab',name='历史报告与建议')).to_have_attribute('aria-selected','true')
            expect(page.locator('.rating-document')).to_be_visible()
            assert len(requests)==(2 if outcome=='review_failure' else 1)
            if outcome=='supplement':
                step='supplement'
                page.get_by_role('button',name='继续评估',exact=True).click()
                expect(page.get_by_text('每月租金多少？',exact=True)).to_be_visible()
                assert len(current['detail']['assessments'])==1
        expect(page.get_by_role('button',name='生成报告',exact=True)).to_have_count(0)
        print('PASS',outcome)
        page.close()
    browser.close()
