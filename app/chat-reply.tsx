import { ChatMarkdown } from './chat-markdown';
import type { Evidence, Message } from '../lib/types';

export function ChatReply({ message, evidence, onEvidence }: { message: Message; evidence: Evidence[]; onEvidence: () => void }) {
  // Historical transport notes are preserved, but no longer interrupt the interview.
  const pieces = message.content.split(/\n\n(?=选源说明：|取数结果：)/);
  const body = pieces[0];
  const refs = evidence.filter(e => message.evidence_ids?.includes(e.id) || body.includes(e.id));
  return <><ChatMarkdown evidence={evidence} onEvidence={onEvidence}>{body}</ChatMarkdown>
    {(refs.length > 0 || pieces.length > 1) && <details className="chat-references"><summary>参考资料</summary>
      {refs.map(e => <div key={e.id}><button type="button" className="text-button" onClick={onEvidence}>{e.title}</button><small>{e.verification_status === 'verified' ? '已核验' : '待核验'}</small></div>)}
      {pieces.length > 1 && <p>历史回复的取数信息已归档，可在证据资料中查看已保存的来源。</p>}
    </details>}
  </>;
}
