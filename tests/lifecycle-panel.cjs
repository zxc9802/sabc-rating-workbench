const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const { renderToStaticMarkup } = require('react-dom/server');
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync('app/lifecycle-panel.tsx', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText, { exports: mod.exports, require });
for (const [stage, report, expected, advances] of [
  ['pre', false, '继续阶段访谈', false], ['pre', true, '进入试点中访谈', true],
  ['during', false, '继续阶段访谈', false], ['during', true, '进入试点后访谈', true],
  ['post', true, '继续阶段访谈', false],
]) {
  let clicked;
  const tree = mod.exports.LifecyclePanel({
    detail: { project: { lifecycle: { stage } }, assessments: report ? [{ result: { stage } }] : [] },
    busy: false, onFollowup: (message, advance) => { clicked = { message, advance }; },
  });
  const html = renderToStaticMarkup(tree);
  assert.ok(html.includes(expected));
  assert.ok(!html.includes('当前阶段执行与回访'));
  tree.props.children.at(-1).props.onClick();
  assert.equal(clicked.advance, advances);
  assert.ok(clicked.message.length > 0);
}
console.log('stage navigation cases passed');
