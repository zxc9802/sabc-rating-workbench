"""Browser regression for report confirmation, progress, recovery and failure. Mock APIs only."""
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
    for outcome in ('success','failure','ask','stale','supplement','report_failure'):
        page=browser.new_page(viewport={'width':1440,'height':1000})
        current=deepcopy(fixture)
        project=current['detail']['project']
        project.update(report_ready=False,analysis_complete=False)
        project['lifecycle']={'stage':'pre','mode':'continuous','confirmed':True,'coverage':{d['key']:{'status':'known','reason':'已提供','items':checkpoint_items(d['key'])} for d in current['bootstrap']['dimensions']}}
        project['messages']=[{'role':'user','content':'已有八维资料'},{'role':'assistant','content':'持证代理的费用能退多少？'}]
        project['interview']={'state':'gathering','questions':['持证代理的费用能退多少？']}
        current['detail']['assessments']=[]
        jobs={};requests=[];finish=False
        def route(r):
            path=r.request.url.split('/api')[-1]
            if path=='/auth/session': data={'authenticated':True,'required':False}
            elif path=='/bootstrap': data=current['bootstrap']
            elif path=='/projects/qa-project': data={**current['detail'],'active_jobs':[j for j in jobs.values() if j['status']=='running']}
            elif path=='/projects/qa-project/jobs':
                body=r.request.post_data_json;requests.append(body)
                generating=body['payload'].get('generate_report',False)
                data={'id':body['id'],'project_id':'qa-project','generate_report':generating,'status':'running','partial_reply':'正在生成报告…' if generating else '八维信息已梳理完成。'}
                jobs[data['id']]=data
            elif path.startswith('/jobs/'):
                data=jobs[path.split('/')[-1]]
                if finish and data['status']=='running':
                    if data['generate_report']:
                        if outcome=='report_failure':
                            data.update(status='failed',error='报告生成超时，请重试')
                        elif outcome=='stale':
                            project['report_ready']=False;project['analysis_complete']=False
                            data.update(status='success',result={'needs_collection':True})
                        else:
                            current['detail']['assessments']=fixture['detail']['assessments']
                            data.update(status='success',result={'report_id':'qa-report'})
                    elif outcome=='failure': data.update(status='failed',error='模型响应无效，请重试')
                    elif outcome=='ask':
                        project['lifecycle']['coverage']['cash']={'status':'ask','reason':'缺少租金'}
                        project['messages'].append({'role':'assistant','content':'还需要确认每月租金？'})
                        project['interview']={'state':'gathering','questions':['还需要确认每月租金？']}
                        data.update(status='success',result={'questions':['还需要确认每月租金？']})
                    else:
                        project.update(report_ready=True,analysis_complete=True)
                        project['pending_patch']={'risks':'本轮整理的风险'}
                        project['interview']={'state':'ready','questions':[]}
                        project['messages'].append({'role':'assistant','content':'信息已整理完成。'})
                        data.update(status='success',result={})
            elif '/reports/' in path: data={'turns':[],'active_job':None}
            else: data={}
            r.fulfill(json=data)
        page.route('**/api/**',route)
        page.add_init_script("sessionStorage.setItem('sabc-project','qa-project')")
        page.goto(os.getenv('SABC_TEST_UI_ORIGIN', 'http://127.0.0.1:3000'));page.wait_for_load_state('networkidle')
        expect(page.get_by_role('button',name='生成报告',exact=True)).to_have_count(0)
        expect(page.get_by_role('button',name='继续核对',exact=True)).to_have_count(0)
        expect(page.get_by_text('持证代理的费用能退多少？',exact=True)).to_be_visible()
        expect(page.get_by_text('信息收集 100%',exact=True)).to_have_count(0)
        page.locator('#message').fill('可以退一半，其余信息已说明')
        page.get_by_role('button',name='发送消息',exact=True).click()
        expect(page.get_by_text('正在思考…',exact=True)).to_be_visible()
        expect(page.get_by_text('八维信息已梳理完成。',exact=True)).to_have_count(0)
        expect(page.get_by_role('button',name='生成报告',exact=True)).to_have_count(0)
        assert not current['detail']['assessments']
        finish=True
        if outcome=='failure':
            expect(page.get_by_role('button',name='重试回答',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='生成报告',exact=True)).to_have_count(0)
        elif outcome=='ask':
            expect(page.get_by_text('还需要确认每月租金？',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='生成报告',exact=True)).to_have_count(0)
        else:
            expect(page.get_by_role('button',name='生成报告',exact=True)).to_be_visible()
            expect(page.get_by_role('button',name='继续补充',exact=True)).to_be_visible()
            expect(page.get_by_text('信息已整理完成，现在生成报告吗？',exact=True)).to_have_count(1)
            assert len(requests)==1 and not requests[0]['payload']['generate_report']
            assert not current['detail']['assessments']
            if outcome=='supplement':
                page.get_by_role('button',name='继续补充',exact=True).click()
                expect(page.get_by_role('button',name='生成报告',exact=True)).to_have_count(0)
                expect(page.locator('#message')).to_be_focused()
                assert len(requests)==1 and not current['detail']['assessments']
                print('PASS',outcome)
                page.close()
                continue
            finish=False
            page.get_by_role('button',name='生成报告',exact=True).click()
            expect(page.locator('.thinking').filter(has_text='正在生成报告…')).to_be_visible()
            page.reload(wait_until='domcontentloaded')
            expect(page.locator('.thinking').filter(has_text='正在生成报告…')).to_be_visible()
            finish=True
            if outcome=='success':
                expect(page.get_by_role('tab',name='历史报告与建议')).to_have_attribute('aria-selected','true')
                expect(page.locator('.rating-document')).to_be_visible()
            elif outcome=='report_failure':
                expect(page.get_by_role('button',name='重试生成报告',exact=True)).to_be_visible()
                assert not current['detail']['assessments']
            else:
                expect(page.get_by_role('button',name='继续核对',exact=True)).to_have_count(0)
                expect(page.get_by_role('button',name='生成报告',exact=True)).to_have_count(0)
            assert len(requests)==2 and requests[1]['payload']['generate_report']
        print('PASS',outcome)
        page.close()
    browser.close()
