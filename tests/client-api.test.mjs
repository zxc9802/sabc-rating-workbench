import { test } from 'node:test';
import assert from 'node:assert/strict';
import { api } from '../lib/types.ts';

test('a stalled save aborts without retrying the mutation', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    calls++;
    return await new Promise((_resolve, reject) => {
      options?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
    });
  });
  const pending = assert.rejects(api('/projects/example', 'PATCH', { timeframe: '6周' }), /操作可能已保存/);
  t.mock.timers.tick(30000);
  await pending;
  assert.equal(calls, 1);
});

test('timeout also covers a stalled response body', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  t.mock.method(globalThis, 'fetch', async (_url, options) => ({
    ok: true, status: 200,
    json: () => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener('abort', () => reject(new Error('aborted body')));
    }),
  }));
  const pending = assert.rejects(api('/bootstrap'), /连接超时/);
  await Promise.resolve();
  t.mock.timers.tick(30000);
  await pending;
});

test('a successful response remains usable and server errors are preserved', async t => {
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => new Response('{"version":3}'));
  assert.deepEqual(await api('/projects/example'), { version: 3 });
  fetchMock.mock.mockImplementation(async () => new Response('{"detail":"项目不存在"}', { status: 404 }));
  await assert.rejects(api('/projects/example'), /项目不存在/);
});

function storage(t) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  const value = Object.create(null);
  Object.defineProperties(value, {
    getItem: { value: key => value[key] ?? null },
    setItem: { value: (key, item) => { value[key] = item; } },
    removeItem: { value: key => { delete value[key]; } },
  });
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value });
  t.after(() => { if (previous) Object.defineProperty(globalThis, 'localStorage', previous); else delete globalThis.localStorage; });
  return value;
}

test('a network retry resumes the accepted job rather than submitting a duplicate', async t => {
  const cache = storage(t), ids = [];
  let interrupted = true;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url.endsWith('/jobs')) {
      const body = JSON.parse(options.body); ids.push(body.id);
      return Response.json({ id: body.id, status: 'running' }, { status: 202 });
    }
    if (interrupted) throw new Error('disconnected');
    return Response.json({ id: ids[0], status: 'success', result: { reply: 'recovered' } });
  });
  await assert.rejects(api('/projects/p/chat', 'POST', { message: 'hello' }), /disconnected/);
  assert.equal(Object.keys(cache).length, 1);
  interrupted = false;
  assert.deepEqual(await api('/projects/p/chat', 'POST', { message: 'hello' }), { reply: 'recovered' });
  assert.equal(ids[0], ids[1]);
  assert.equal(Object.keys(cache).length, 0);
});

test('after a project refresh includes completed work, identical text starts a new turn', async t => {
  const cache = storage(t), ids = [];
  let interrupted = true;
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    if (url === '/api/projects/p') return Response.json({ completed_job_ids: [ids[0]], project: { id: 'p' } });
    if (url.endsWith('/jobs')) {
      const body = JSON.parse(options.body); ids.push(body.id);
      return Response.json({ id: body.id, status: 'running' }, { status: 202 });
    }
    if (interrupted) throw new Error('disconnected');
    return Response.json({ id: ids.at(-1), status: 'success', result: { reply: 'new turn' } });
  });
  await assert.rejects(api('/projects/p/chat', 'POST', { message: 'hello' }), /disconnected/);
  await api('/projects/p');
  assert.equal(Object.keys(cache).length, 0);
  interrupted = false;
  assert.deepEqual(await api('/projects/p/chat', 'POST', { message: 'hello' }), { reply: 'new turn' });
  assert.notEqual(ids[0], ids[1]);
});
