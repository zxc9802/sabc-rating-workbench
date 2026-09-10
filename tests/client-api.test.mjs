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
