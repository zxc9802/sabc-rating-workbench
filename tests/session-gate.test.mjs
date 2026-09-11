import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const compiled = ts.transpileModule(readFileSync(new URL('../app/session-gate.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;

// Exercise the component's asynchronous session checks and browser events.
function gate() {
  const state = [], effects = [], events = new Map(), storage = new Map();
  let cursor = 0, refresh, response = { authenticated: true, required: true, mode: 'sso', user: { id: 'a' } };
  const exports = {};
  vm.runInNewContext(compiled, {
    exports, Error,
    require: name => name === 'react' ? {
      Fragment: Symbol.for('react.fragment'),
      useState: initial => {
        const index = cursor++;
        if (!(index in state)) state[index] = initial;
        return [state[index], value => { state[index] = value; }];
      },
      useEffect: callback => { effects.push(callback); },
    } : name === '../lib/types' ? {
      api: async () => { if (response instanceof Error) throw response; return response; },
    } : require(name),
    sessionStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    localStorage: {}, document: { visibilityState: 'visible' },
    window: {
      addEventListener: (name, fn) => events.set(name, fn), removeEventListener: name => events.delete(name),
      setInterval: fn => { refresh = fn; return 1; }, clearInterval() {},
    },
  });
  let visible;
  function render() {
    cursor = 0; visible = false;
    exports.SessionGate({ children: () => { visible = true; return null; } });
    return visible;
  }
  async function settle() { await new Promise(resolve => setImmediate(resolve)); return render(); }
  render(); effects[0]();
  return { settle, events, check: async value => { response = value; refresh(); return settle(); } };
}

test('temporary session-check failures keep the workspace, but confirmed expiry removes it', async () => {
  const app = gate();
  assert.equal(await app.settle(), true);
  assert.equal(await app.check(new Error('Failed to fetch')), true);
  assert.equal(await app.check(new Error('主站登录校验暂时不可用')), true);
  assert.equal(await app.check({ authenticated: true, required: true, mode: 'sso', user: { id: 'a' } }), true);
  assert.equal(await app.check({ authenticated: false, required: true, mode: 'sso' }), false);
});

test('an API session-expired event still closes the workspace', async () => {
  const app = gate();
  assert.equal(await app.settle(), true);
  app.events.get('sabc-session-expired')();
  assert.equal(await app.settle(), false);
});
