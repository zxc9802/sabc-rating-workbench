import os
"""Local browser regression with synthetic reports and mocked model jobs.
Run against Next dev at 127.0.0.1:3000, with Playwright installed.
"""
from playwright.sync_api import sync_playwright, expect
from sabc.rating import assess, DIMENSIONS, TYPES
from tests.test_rating import case
p,c,e,proposal=case(2)
p.update(id='qa-project',name='报告助手验收项目',messages=[{'role':'assistant','content':'本地界面验收记录'}],updated_at='2026-09-11T00:00:00Z',version=1)
result=assess(p,c,e,proposal)
r={'id':'qa-report','project_id':p['id'],'created_at':'2026-09-11T00:00:00Z','result':result,'snapshot':{'company':c,'project':p,'proposal':proposal,'evidence':e}}
r2={**r,'id':'qa-old','created_at':'2026-09-10T00:00:00Z'}
fixture={'bootstrap':{'projects':[p],'company':c,'dimensions':[{'key':k,'name':n,'weight':w} for k,(n,w) in DIMENSIONS.items()],'types':TYPES,'settings':{'configured':True},'sources':[],'rule_version':'test'},'detail':{'project':p,'assessments':[r,r2],'evidence':e}}
turns={'qa-report':[],'qa-old':[]};jobs={};submissions=[];complete=False
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':900})
    errors=[];page.on('pageerror',lambda e: errors.append(str(e)))
    def route(r):
        path=r.request.url.split('/api')[-1]
        if path=='/auth/session': data={'authenticated':True,'required':False}
        elif path=='/bootstrap': data=fixture['bootstrap']
        elif path=='/projects/qa-project': data=fixture['detail']
        elif '/reports/' in path:
            rid=path.split('/reports/')[1].split('/')[0];data={'turns':turns[rid],'active_job':next((j for j in jobs.values() if j['assessment_id']==rid and j['status']=='running'),None)}
        elif path=='/projects/qa-project/jobs':
            body=r.request.post_data_json;submissions.append(body);rid=body['payload']['assessment_id']
            turn={'id':body['id'],'question':body['payload']['message'],'reply':'报告建议先验证需求，再决定扩大投入。'}
            data={'id':body['id'],'assessment_id':rid,'status':'running','question':turn['question'],'partial_reply':'正在核对报告中的试点建议'}
            jobs[body['id']]={**data,'result':turn}
        elif path.startswith('/jobs/'):
            data=jobs[path.split('/')[-1]]
            if complete and data['status']=='running':
                turns[data['assessment_id']].append(data['result']);data['status']='success'
        else: data={}
        r.fulfill(json=data)
    page.route('**/api/**',route)
    page.add_init_script("sessionStorage.setItem('sabc-project','qa-project')")
    page.goto(os.getenv('SABC_TEST_UI_ORIGIN', 'http://127.0.0.1:3000'));page.wait_for_load_state('networkidle')
    page.get_by_role('tab',name='历史报告与建议').click()
    dock=page.get_by_role('complementary',name='报告问答助手')
    expect(dock).to_be_visible()
    box1=dock.bounding_box()
    page.evaluate('window.scrollTo(0,document.body.scrollHeight)')
    page.wait_for_timeout(250)
    box2=dock.bounding_box()
    assert abs(box1['y']-box2['y'])<2
    assert abs(box2['y']+box2['height']-900)<2
    page.get_by_role('textbox',name='向报告助手提问').fill('为什么建议先试点？')
    page.get_by_role('button',name='发送',exact=True).click()
    expect(dock.get_by_text('正在核对报告中的试点建议')).to_be_visible()
    page.reload();page.wait_for_load_state('networkidle')
    page.get_by_role('tab',name='历史报告与建议').click()
    expect(dock.get_by_text('正在核对报告中的试点建议')).to_be_visible()
    complete=True
    expect(dock.get_by_text('报告建议先验证需求，再决定扩大投入。')).to_be_visible()
    page.locator('.history-select select').select_option('qa-old')
    expect(dock.get_by_text('报告建议先验证需求，再决定扩大投入。')).to_have_count(0)
    page.locator('.history-select select').select_option('qa-report')
    page.get_by_role('button',name='查看问答',exact=True).click()
    expect(dock.get_by_text('报告建议先验证需求，再决定扩大投入。')).to_be_visible()
    page.reload();page.wait_for_load_state('networkidle')
    page.get_by_role('tab',name='历史报告与建议').click()
    page.get_by_role('button',name='查看问答',exact=True).click()
    expect(dock.get_by_text('报告建议先验证需求，再决定扩大投入。')).to_be_visible()
    page.screenshot(path='/tmp/sabc-report-assistant-desktop.png')
    page.set_viewport_size({'width':390,'height':844})
    page.evaluate('window.scrollTo(0,document.body.scrollHeight)');page.wait_for_timeout(250)
    box=dock.bounding_box();assert box['x']==0 and box['width']==390
    assert abs(box['y']+box['height']-844)<2
    assert page.evaluate('document.documentElement.scrollWidth')==390
    page.screenshot(path='/tmp/sabc-report-assistant-mobile.png')
    page.emulate_media(media='print');expect(dock).not_to_be_visible()
    assert submissions[0]['operation']=='report_chat'
    assert not errors,errors
    print('PASS: fixed desktop/mobile, send, version isolation, pending refresh recovery, refresh history, print exclusion; mocked API')
    browser.close()
