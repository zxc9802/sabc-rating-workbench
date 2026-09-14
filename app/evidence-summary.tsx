'use client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Evidence } from '../lib/types';

type Item = { title: string; url: string; summary: string; limitation: string; kind: string };
const record = (value: unknown): Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const string = (value: unknown) => typeof value === 'string' ? value : '';
const locator = (row: Record<string, unknown>) => string(row.detail_url || row.url || row.html_url || row.trackViewUrl);
const labels: Record<string, string> = {
  title: '标题', description: '简介', metadata: '资料信息', rows: '数据记录', fields: '字段说明',
  article: '正文', text: '内容', pages: '原文', page: '页码', total_pages: '总页数', extracted_pages: '已读取页数',
  gbrq: '公布日期', sxrq: '生效日期', zdjgName: '发布机关', flxz: '法规类型', sxx: '效力状态',
  region: '地区', date: '期间', value: '数值', unit: '单位', indicator: '指标', country: '国家或地区',
  retrieved_rows: '已获取记录数', distinct_rows: '去重记录数', reported_total: '来源报告总数', coverage: '覆盖范围',
  published_at: '发布时间', approx_traffic: '搜索热度', full_name: '仓库名称', stargazers_count: '星标数',
  forks_count: '分支数', open_issues_count: '未关闭问题数', pushed_at: '最近推送', updated_at: '更新时间',
  archived: '已归档', language: '语言', license: '许可证', name: '名称', filings: '披露记录',
  tag: '财务指标', val: '数值', start: '开始日期', end: '结束日期', filed: '申报日期', form: '表单类型',
  filingDate: '申报日期', reportDate: '报告日期', accessionNumber: '申报编号', primaryDocument: '公告文件',
  trackName: '应用名称', sellerName: '开发者', version: '版本', currentVersionReleaseDate: '版本发布时间',
  averageUserRating: '平均评分', userRatingCount: '评分人数', price: '价格', currency: '币种', primaryGenreName: '应用类别',
};
const internalFields = /^(id|bbbs|score|status_codes|query|limitation|.*Highlight.*|.*CodeId|detail_url|url|html_url|trackViewUrl)$/i;

function readable(value: unknown): string {
  if (value == null || value === '') return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (Array.isArray(value)) return value.map(readable).filter(Boolean).join('\n\n');
  return Object.entries(record(value)).filter(([key]) => !internalFields.test(key)).map(([key, entry]) => {
    const content = readable(entry);
    return content ? `${labels[key] || key}：${content}` : '';
  }).filter(Boolean).join('\n\n');
}

function itemsFor(evidence: Evidence): Item[] {
  const base = { title: evidence.title, url: evidence.source_locator, summary: '', limitation: '', kind: '资料内容' };
  const content = evidence.content.trim();
  let parsed: unknown;
  try { parsed = JSON.parse(content.replace(/^```(?:json)?\s*\n([\s\S]*?)\n```$/i, '$1')); }
  catch {
    return [{ ...base, summary: /^(?:\{\s*"|\[\s*\{)/.test(content) || /^```json\b/i.test(content)
      ? '资料格式不完整，暂时无法整理为摘要，请重新采集或补充文字说明。' : evidence.content }];
  }
  const payload = record(parsed);
  base.limitation = string(payload.limitation);
  const facts = record(payload.facts);
  const results = Array.isArray(payload.results) ? payload.results : null;
  const rows = results ?? (Array.isArray(facts.rows) ? facts.rows : Array.isArray(payload.facts) ? payload.facts : []);
  const linkedRows = rows.map(record).filter(row => locator(row));
  if (linkedRows.length) return linkedRows.map(row => {
    const law = 'gbrq' in row || 'sxrq' in row || 'zdjgName' in row;
    const status = string(record(facts.status_codes)[String(row.sxx)]);
    const summary = law ? [
      row.flxz && `法规类型：${row.flxz}`, row.zdjgName && `发布机关：${row.zdjgName}`,
      row.gbrq && `公布日期：${row.gbrq}`, row.sxrq && `生效日期：${row.sxrq}`,
      row.sxx != null && `采集时效力状态：${status || '待核验'}`,
    ].filter(Boolean).join('；') + '。' : string(row.summary) || string(row.snippet) || string(row.content) || readable(row);
    return { ...base, title: string(row.title || row.trackName || row.full_name) || base.title,
      url: locator(row), summary, kind: law ? '法规检索' : results ? '网页摘要' : '来源数据' };
  });
  return [{ ...base, summary: readable(payload.facts ?? parsed), kind: '资料内容' }];
}

export function EvidenceSummary({ evidence }: { evidence: Evidence | Evidence[] }) {
  const items = (Array.isArray(evidence) ? evidence : [evidence]).flatMap(itemsFor);
  return <ol className="evidence-content" aria-label="证据资料列表">{items.map((item, i) => <li className="evidence-entry" key={i}>
    <span className="evidence-number" aria-hidden="true">{i + 1}</span>
    <article className="evidence-body">
      <header className="evidence-entry-heading"><h3>{item.title || '未命名资料'}</h3><span>{item.kind}</span></header>
      <div className="chat-markdown evidence-summary"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item.summary || '暂无摘要，请补充资料内容。'}</ReactMarkdown></div>
      {item.url && <div className="evidence-source"><span>{/^https?:\/\//i.test(item.url) ? '来源网址' : '资料位置'}</span>
        {/^https?:\/\//i.test(item.url) ? <a href={item.url} target="_blank" rel="noopener noreferrer">{item.url}</a> : <p>{item.url}</p>}
      </div>}
      {item.limitation && <p className="evidence-limitation">来源说明：{item.limitation}</p>}
    </article>
  </li>)}</ol>;
}
