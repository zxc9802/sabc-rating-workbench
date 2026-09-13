"""Real browser regression for draft preservation; synthetic API data only."""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from sabc.rating import DIMENSIONS, TYPES

fixture = {
    'bootstrap': {'projects': [], 'company': {}, 'dimensions': [
        {'key': key, 'name': name, 'weight': weight} for key, (name, weight) in DIMENSIONS.items()],
        'types': TYPES, 'settings': {'configured': False}, 'sources': [], 'rule_version': 'test'},
    'detail': {'project': {'id': 'qa-draft', 'name': '合成评审草稿回归', 'project_type': 'internal',
                           'messages': [{'role': 'assistant', 'content': '合成访谈记录'}],
                           'updated_at': '2026-09-13T00:00:00Z', 'version': 1},
               'evidence': [], 'assessments': []},
}

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
    counts = {'bootstrap': 0}
    def route(request):
        path = request.request.url.split('/api')[-1]
        if path == '/auth/session': data = {'authenticated': True, 'required': False}
        elif path == '/bootstrap':
            counts['bootstrap'] += 1
            data = fixture['bootstrap']
        elif path == '/projects/qa-draft': data = fixture['detail']
        else: data = {}
        request.fulfill(json=data)
    page.route('**/api/**', route)
    page.add_init_script("sessionStorage.setItem('sabc-project','qa-draft')")
    page.clock.install()
    page.goto(os.getenv('SABC_TEST_UI_ORIGIN', 'http://127.0.0.1:3000'))
    page.get_by_role('tab', name='历史报告与建议').click()
    page.get_by_role('button', name='打开评审表').click()
    field = page.get_by_placeholder('说明为什么给这个分数，区分事实、推断和未知。').first
    draft = '合成回归：后台刷新不能清除这段未保存的评分依据'
    field.fill(draft)
    confirm = page.get_by_label('我已核对以上事实、证据与判断，确认用于本次评级')
    confirm.check()
    previous = counts['bootstrap']
    page.clock.fast_forward(61_000)
    expect(field).to_have_value(draft)
    expect(confirm).to_be_checked()
    assert counts['bootstrap'] > previous
    page.get_by_role('button', name='收起评审表').click()
    page.clock.fast_forward(61_000)
    page.get_by_role('button', name='打开评审表').click()
    expect(field).to_have_value(draft)
    expect(confirm).to_be_checked()
    output = Path('artifacts/security-fix-20260913')
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / 'review-draft-preserved.png'), full_page=True)
    print('PASS: draft and confirmation survive refresh, collapse and reopen; mocked API')
    browser.close()
