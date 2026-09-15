"""Browser checks for archived NR display and revision controls; API responses are fixtures."""
from copy import deepcopy
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from sabc import rating


def main():
    output = Path('artifacts/test-6-7-review-20260915')
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for case in ('tripadvisor', 'duolingo'):
            snapshot = json.loads((Path('tests/fixtures') / f'{case}-review.json').read_text())
            project = snapshot['project']
            project.update(id='qa-project', version=1, report_pipeline=None, updated_at='2026-09-14T12:00:00Z')
            report = {'id':'qa-report', 'project_id':project['id'], 'created_at':'2026-09-14T12:00:00Z',
                      'snapshot':snapshot, 'result':rating.assess(project, snapshot['company'], snapshot['evidence'], snapshot['proposal'])}
            dimensions = [{'key':key, 'name':name, 'weight':weight} for key,(name,weight) in rating.DIMENSIONS.items()]
            detail = {'project':project, 'evidence':snapshot['evidence'], 'assessments':[report], 'active_jobs':[]}
            jobs = {}
            requests = []

            def route(handler):
                path = handler.request.url.split('/api')[-1]
                if path == '/auth/session':
                    data = {'authenticated':True, 'required':False}
                elif path == '/bootstrap':
                    data = {'projects':[project], 'company':snapshot['company'], 'dimensions':dimensions,
                            'types':rating.TYPES, 'settings':{'configured':True}, 'sources':[], 'rule_version':rating.RULE_VERSION}
                elif path == '/projects/qa-project':
                    data = detail
                elif path == '/projects/qa-project/jobs':
                    body = handler.request.post_data_json
                    requests.append(body)
                    revised = deepcopy(report)
                    revised.update(id='qa-revised', created_at='2026-09-15T00:00:00Z')
                    revised['result']['revision'] = {'source_report_id':report['id'], 'changes':['现金流与资金效率的分数或依据']}
                    detail['assessments'] = [revised, report]
                    data = {'id':body['id'], 'project_id':project['id'], 'operation':'chat', 'status':'success',
                            'result':{'report_id':'qa-revised'}}
                    jobs[data['id']] = data
                elif path.startswith('/jobs/'):
                    data = jobs[path.split('/')[-1]]
                elif '/reports/' in path:
                    data = {'turns':[{'id':'qa-question', 'question':'集团现金能证明分部现金健康吗？',
                                      'reply':'需要根据原始资料复核现金口径。'}], 'active_job':None}
                else:
                    data = {}
                handler.fulfill(json=data)

            page = browser.new_page(viewport={'width':1440, 'height':1000})
            page.route('**/api/**', route)
            page.add_init_script("sessionStorage.setItem('sabc-project','qa-project')")
            page.goto(os.getenv('SABC_TEST_UI_ORIGIN', 'http://127.0.0.1:3015'))
            page.get_by_role('tab', name='历史报告与建议').click()
            document = page.locator('.rating-document')
            expect(document).to_be_visible()
            expect(document.locator('.dimension-result')).to_have_count(8)
            expect(document.locator('.rating-score')).to_contain_text('暂不计算')
            assert document.locator('.rating-score strong').evaluate('(el) => el.clientHeight < 60'), 'Score label wraps vertically'
            expect(document.locator('.rating-summary-text')).to_contain_text('E0')
            expect(document).to_contain_text('规范化来源 1 个')
            for title in ('项目基本信息', '八维业务判断', '正方结论', '反方结论', '最强反对意见', '关键判断与资源安排', '行动建议', '验证与退出'):
                expect(document.get_by_role('heading', name=title, exact=True)).to_be_visible()
            page.screenshot(path=str(output / f'{case}-desktop.png'), full_page=True)
            document.locator('.rating-summary').screenshot(path=str(output / f'{case}-summary.png'))
            page.set_viewport_size({'width':390, 'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'Mobile horizontal overflow'
            page.screenshot(path=str(output / f'{case}-mobile.png'), full_page=True)
            page.set_viewport_size({'width':1440, 'height':1000})
            page.get_by_role('button', name='查看问答', exact=True).click()
            page.get_by_role('button', name='根据此问题修订并生成新版本', exact=True).click()
            expect(document.get_by_role('heading', name='本次修订', exact=True)).to_be_visible()
            assert requests[-1]['payload']['revision_of'] == 'qa-report'
            assert requests[-1]['payload']['revision_turn_id'] == 'qa-question'
            assert requests[-1]['payload']['generate_report'] is True
            page.get_by_label('历史报告版本').select_option('qa-report')
            expect(document.get_by_role('heading', name='本次修订', exact=True)).to_have_count(0)
            print('PASS', case, 'eight dimensions, NR, source count, report sections, mobile, revision and old version')
            page.close()
        browser.close()


if __name__ == '__main__':
    main()
