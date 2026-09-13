import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const compiled = ts.transpileModule(fs.readFileSync(new URL('../app/report-panel.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;

function panel() {
  const state = [], deps = [], exports = {};
  let cursor = 0, pending = [];
  const hooks = {
    useRef(initial) {
      const i = cursor++;
      if (!(i in state)) state[i] = { current: initial };
      return state[i];
    },
    useState(initial) {
      const i = cursor++;
      if (!(i in state)) state[i] = initial;
      return [state[i], value => { state[i] = typeof value === 'function' ? value(state[i]) : value; }];
    },
    useEffect(fn, next) {
      const i = cursor++;
      if (!deps[i] || next.some((value, k) => !Object.is(value, deps[i][k]))) pending.push(fn);
      deps[i] = next;
    },
  };
  vm.runInNewContext(compiled, { exports, require: name => name === 'react' ? hooks
    : name === 'react/jsx-runtime' ? require(name)
      : name === '../lib/types' ? { gradeLabel: value => value }
        : new Proxy({}, { get: (_, key) => key }) });
  let props = { detail: { project: { id: 'p', messages: [] }, assessments: [], evidence: [] },
    dimensions: [{ key: 'strategy', name: '战略', weight: 15 }], busy: false };
  return {
    render(update = {}) {
      props = { ...props, ...update };
      for (let i = 0; i < 8; i++) {
        cursor = 0; pending = [];
        const tree = exports.ReportPanel(props);
        if (!pending.length) return tree;
        pending.forEach(fn => fn());
      }
      throw new Error('unstable effects');
    },
    get props() { return props; },
  };
}

function nodes(tree, found = []) {
  if (Array.isArray(tree)) tree.forEach(child => nodes(child, found));
  else if (tree?.props) { found.push(tree); nodes(tree.props.children, found); }
  return found;
}
const editor = tree => nodes(tree).find(n => n.type === 'textarea' && n.props.placeholder?.startsWith('说明为什么'));

test('background refresh preserves an open review draft, switching project resets it', () => {
  const app = panel();
  let tree = app.render();
  nodes(tree).find(n => n.type === 'button' && JSON.stringify(n.props.children).includes('打开评审表')).props.onClick();
  tree = app.render();
  editor(tree).props.onChange({ target: { value: '尚未保存的评审依据' } });
  tree = app.render();
  assert.equal(editor(tree).props.value, '尚未保存的评审依据');
  tree = app.render({ dimensions: structuredClone(app.props.dimensions), detail: structuredClone(app.props.detail) });
  assert.equal(editor(tree).props.value, '尚未保存的评审依据');
  nodes(tree).find(n => n.type === 'button' && JSON.stringify(n.props.children).includes('收起评审表')).props.onClick();
  tree = app.render({ dimensions: structuredClone(app.props.dimensions) });
  nodes(tree).find(n => n.type === 'button' && JSON.stringify(n.props.children).includes('打开评审表')).props.onClick();
  assert.equal(editor(app.render()).props.value, '尚未保存的评审依据');
  tree = app.render({ detail: { ...app.props.detail, project: { id: 'other', messages: [] } } });
  assert.equal(editor(tree), undefined);
  nodes(tree).find(n => n.type === 'button' && JSON.stringify(n.props.children).includes('打开评审表')).props.onClick();
  assert.equal(editor(app.render()).props.value, '');
});
