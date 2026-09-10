'use client';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Evidence } from '../lib/types';

export function EvidenceSummary({ evidence }: { evidence: Evidence }) {
  let items: { url: string; summary: string }[] = [];
  try {
    const parsed = JSON.parse(evidence.content);
    if (Array.isArray(parsed.results)) items = parsed.results.map((r: { url?: unknown; snippet?: unknown }) => ({
      url: typeof r.url === 'string' ? r.url : '', summary: typeof r.snippet === 'string' ? r.snippet : '',
    }));
  } catch { /* Uploaded Markdown and ordinary text are rendered directly. */ }
  if (!items.length) items = [{ url: evidence.source_locator, summary: evidence.content || '暂无摘要' }];
  return <div className="evidence-content">{items.map((item, i) => <article key={i}>
    {/^https?:\/\//i.test(item.url) ? <p><a href={item.url} target="_blank" rel="noopener noreferrer">{item.url}</a></p> : <p>{item.url}</p>}
    <div className="chat-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item.summary || '暂无摘要'}</ReactMarkdown></div>
  </article>)}</div>;
}
