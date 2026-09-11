const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync('lib/interview-history.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: mod.exports });
const { interviewStage } = mod.exports;
const early = { role: 'user', content: '启动前预算', time: '2026-09-01T00:00:00Z' };
const detail = { project: { lifecycle: { stage: 'post', events: [{ action: 'advance', stage: 'during', time: '2026-09-02T00:00:00Z' }] } }, assessments: [
  { created_at: '2026-09-03', result: { stage: 'during' }, snapshot: { project: { messages: [early] } } },
  { created_at: '2026-09-01', result: { stage: 'pre' }, snapshot: { project: { messages: [early] } } },
] };
assert.equal(interviewStage(early, detail), 'pre');
assert.equal(interviewStage({ ...early, stage: 'post' }, detail), 'post');
assert.equal(interviewStage({ role: 'assistant', content: '执行情况', time: '2026-09-02T12:00:00Z' }, detail), 'during');
assert.equal(interviewStage({ role: 'user', content: '没有时间的旧记录' }, detail), 'legacy');
assert.equal(detail.assessments[0].result.stage, 'during');
console.log('interview history cases passed');
