const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function load(file, overrides = {}) {
  const mod = { exports: {} };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, { exports: mod.exports, require: id => overrides[id] || require(id) });
  return mod.exports;
}
const { ReportPanel } = load('app/report-panel.tsx', {
  '../lib/types': load('lib/types.ts'),
  '../lib/deferral-reason': load('lib/deferral-reason.ts'),
  './report-assistant': { ReportAssistant: () => null },
  './workbench-forms': { Field: () => null },
});

function renderReport(report) {
  return renderToStaticMarkup(React.createElement(ReportPanel, {
    detail: { project: report.snapshot.project, evidence: report.snapshot.evidence, assessments: [report] },
    dimensions: Object.entries({ strategy: 15, market: 15, return: 20, resources: 15, replication: 10, cash: 10, risk: 10, opportunity: 5 })
      .map(([key, weight]) => ({ key, weight, name: key })),
    busy: false, run: async () => {}, refresh: async () => {}, onGenerate: () => {}, onRevise: () => {},
  }));
}

if (require.main === module) {
  const snapshot = JSON.parse(fs.readFileSync('tests/fixtures/duolingo-review.json', 'utf8'));
  const report = { id: 'readability-test', created_at: '2026-09-16T00:00:00Z', snapshot, result: snapshot.result };
  snapshot.proposal.decision_brief = { ...snapshot.proposal.decision_brief, biggest_risk: '当前收入尚不能证明扣除全部成本后仍有回报。' };
  snapshot.proposal.strongest_objections = ['旧版第一项', '旧版第二项', '旧版第三项'];
  let before = JSON.stringify(report);
  let html = renderReport(report);
  assert.ok(html.includes('<h3>最大隐患</h3><p>当前收入尚不能证明扣除全部成本后仍有回报。</p>'));
  assert.equal((html.match(/class="dimension-result"/g) || []).length, 8);
  assert.ok(html.includes('暂不计算'));
  assert.equal(JSON.stringify(report), before);
  snapshot.proposal.strongest_objections = ['还没有实际计时记录，暂时无法确认新流程是否更省时间。'];
  before = JSON.stringify(report);
  html = renderReport(report);
  assert.ok(html.includes('<h3>最大隐患</h3><p>还没有实际计时记录，暂时无法确认新流程是否更省时间。</p>'));
  assert.ok(!html.includes('当前收入尚不能证明扣除全部成本后仍有回报。'));
  for (const label of ['项目优势', '项目劣势', '项目要点', '试点与停止条件']) assert.ok(html.includes(`<h3>${label}</h3>`));
  assert.equal(JSON.stringify(report), before);
  console.log('PASS: single main risk, legacy report compatibility, eight dimensions, unchanged snapshots');
}

module.exports = { renderReport };
