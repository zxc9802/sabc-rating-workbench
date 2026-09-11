const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');
const moduleValue = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync('lib/collection-progress.ts', 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: moduleValue.exports });
const { collectionProgress } = moduleValue.exports;
const keys = ['strategy', 'market', 'return', 'resources', 'replication', 'cash', 'risk', 'opportunity'];
const life = { confirmed: true, stage: 'pre', coverage: Object.fromEntries(keys.map(k => [k, { status: 'known', reason: '当前判断依据' }])) };
assert.equal(collectionProgress().percent, 0);
assert.equal(collectionProgress(life).ready, true);
assert.equal(collectionProgress(life).percent, 100);
assert.equal(collectionProgress(life, ['费用能退多少？']).ready, false);
assert.ok(collectionProgress(life, ['费用能退多少？']).percent < 100);
for (const status of ['ask']) {
  life.coverage.risk.status = status;
  assert.equal(collectionProgress(life).ready, false);
  assert.equal(collectionProgress(life).percent, 88);
}
life.coverage.risk.status = 'future';
assert.equal(collectionProgress(life).ready, true);
life.stage = 'post';
assert.equal(collectionProgress(life).ready, true);
for (const status of ['unknown', 'external']) {
  life.coverage.risk.status = status;
  assert.equal(collectionProgress(life).ready, true);
  assert.equal(collectionProgress(life).percent, 100);
}
life.coverage.risk.status = 'known';
life.confirmed = false;
assert.equal(collectionProgress(life).percent, 99);
assert.equal(collectionProgress(life).ready, false);
life.confirmed = true;
life.coverage.risk.reason = '';
assert.equal(collectionProgress(life).ready, false);
console.log('collection progress cases passed');
