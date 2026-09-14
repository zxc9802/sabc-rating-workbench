import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const compiled = ts.transpileModule(fs.readFileSync(new URL('../app/evidence-summary.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;
const exports = {};
vm.runInNewContext(compiled, { exports, require: name => name === 'react-markdown' ? ReactMarkdown
  : name === 'remark-gfm' ? remarkGfm : require(name) });
const evidence = (content, extra = {}) => ({ id: 'saved', title: '资料标题', source_locator: 'https://example.com/source',
  content: typeof content === 'string' ? content : JSON.stringify(content), ...extra });
const render = item => renderToStaticMarkup(createElement(exports.EvidenceSummary, { evidence: item }));

test('law search evidence shows readable facts and matching detail links instead of raw JSON', () => {
  const html = render(evidence({ facts: { rows: [{ bbbs: 'internal-id', title: '测试法规', gbrq: '2021-06-10',
    sxrq: '2021-09-01', sxx: 3, zdjgName: '测试发布机关', titleHighlightList: [{ value: '测试', highlight: true }],
    detail_url: 'https://example.com/law' }], status_codes: { 3: '有效' } }, limitation: '仅标题检索，尚非条文全文。' }));
  assert.doesNotMatch(html, /&quot;facts&quot;|bbbs|internal-id|titleHighlightList/);
  assert.match(html, /测试法规/);
  assert.match(html, /2021-06-10/);
  assert.match(html, /有效/);
  assert.match(html, /仅标题检索，尚非条文全文/);
  assert.ok(html.indexOf('测试发布机关') < html.indexOf('href="https://example.com/law"'));
});

test('every search result retains its full summary above its own URL', () => {
  const summary = '这是一段需要完整显示的市场资料。'.repeat(250) + '最后一句也必须显示。';
  const html = render(evidence({ results: [{ title: '网页一', url: 'https://example.com/one', snippet: summary },
    { title: '网页二', url: 'https://example.com/two', snippet: '第二份资料的摘要。' }], limitation: '未读取网页全文。' }));
  assert.ok(html.includes(summary));
  assert.ok(html.indexOf('最后一句也必须显示。') < html.indexOf('href="https://example.com/one"'));
  assert.ok(html.indexOf('第二份资料的摘要。') < html.indexOf('href="https://example.com/two"'));
  assert.match(html, /网页一/);
  assert.match(html, /未读取网页全文/);
});

test('the actual evidence panel numbers sources continuously across saved evidence batches', () => {
  const panelExports = {};
  const panelCode = ts.transpileModule(fs.readFileSync(new URL('../app/workbench-forms.tsx', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  vm.runInNewContext(panelCode, { exports: panelExports, require: name => name === './evidence-summary' ? exports
    : name === './source-fetch' ? { SourceFetch: () => null } : name === '../lib/types' ? {} : require(name) });
  const html = renderToStaticMarkup(createElement(panelExports.EvidencePanel, { projectId: 'p', evidence: [
    evidence({ results: [{ title: '第一条', url: 'https://example.com/1', snippet: '第一条摘要' },
      { title: '第二条', url: 'https://example.com/2', snippet: '第二条摘要' }] }),
    evidence('第三条摘要', { id: 'another', title: '第三条' }),
  ], busy: false, run: async () => {}, refresh: async () => {} }));
  assert.deepEqual([...html.matchAll(/class="evidence-number"[^>]*>(\d+)</g)].map(m => m[1]), ['1', '2', '3']);
  assert.equal((html.match(/class="evidence-entry"/g) || []).length, 3);
});

test('uploaded Markdown beginning with a link remains readable and complete', () => {
  const html = render(evidence('[原文](https://example.com/article)\n\n**已核对的资料内容。**\n\n最后一段。'));
  assert.match(html, /<strong>已核对的资料内容。<\/strong>/);
  assert.match(html, /最后一段。/);
});

test('other official facts and article pages render without raw JSON or lost zero values', () => {
  const html = render(evidence({ facts: { pages: [{ page: 1, text: '第一页全文。' }, { page: 2, text: '第二页全文。' }],
    value: 0 }, limitation: '需核对数据期间。' }));
  assert.match(html, /第一页全文。/);
  assert.match(html, /第二页全文。/);
  assert.match(html, /数值：0/);
  assert.doesNotMatch(html, /&quot;pages&quot;/);
});

test('empty or malformed data does not crash or expose raw JSON', () => {
  for (const value of [null, { results: [null, 3, {}] }, '{"facts":{"rows":[']) {
    const html = render(evidence(value));
    assert.doesNotMatch(html, /&quot;facts&quot;|&quot;results&quot;/);
  }
  assert.doesNotMatch(render(evidence('安全资料', { source_locator: 'javascript:alert(1)' })), /href="javascript:/);
});
