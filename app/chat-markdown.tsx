import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function ChatMarkdown({ children }: { children: string }) {
  return <div className="chat-markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={{
    a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
    img: ({ alt }) => <span>{alt || '图片'}</span>,
    table: ({ children }) => <div className="markdown-table"><table>{children}</table></div>,
  }}>{children}</ReactMarkdown></div>;
}
