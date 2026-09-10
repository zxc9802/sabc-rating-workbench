import ReactMarkdown from 'react-markdown';
import { readableReply } from '../lib/readable-reply';
import remarkGfm from 'remark-gfm';

export function ChatMarkdown({ children, evidence = [], streaming = false, onEvidence }: { children: string; evidence?: { id: string; title: string }[]; streaming?: boolean; onEvidence?: () => void }) {
  return <div className="chat-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={{
    a: ({ children, href }) => href === '#evidence' ? <button type="button" className="text-button" onClick={onEvidence}>{children}</button> : <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
    img: ({ alt }) => <span>{alt || '图片'}</span>,
    table: ({ children }) => <div className="markdown-table"><table>{children}</table></div>,
  }}>{readableReply(children, evidence, streaming)}</ReactMarkdown></div>;
}
