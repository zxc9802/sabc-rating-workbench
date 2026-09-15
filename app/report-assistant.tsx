'use client';
import { useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, Send } from 'lucide-react';
import { api, Assessment, Job } from '../lib/types';
import { ChatMarkdown } from './chat-markdown';

type Turn = { id: string; question: string; reply: string };
type ReportJob = Job & { question?: string };
type History = { turns: Turn[]; active_job: ReportJob | null };

export function ReportAssistant({ projectId, report, disabled, onRevise }: { projectId: string; report: Assessment; disabled: boolean; onRevise?: (reportId: string, turnId: string) => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [job, setJob] = useState<ReportJob | null>(null);
  const [question, setQuestion] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);
  const alive = useRef(true);
  const pending = useRef<{ id: string; message: string } | null>(null);
  const dock = useRef<HTMLElement>(null);
  const historyPath = `/projects/${projectId}/reports/${report.id}/chat`;

  useEffect(() => {
    alive.current = true;
    const element = dock.current;
    const area = element?.closest<HTMLElement>('.report-area');
    const resize = new ResizeObserver(() => { if (area && element) area.style.paddingBottom = `${element.offsetHeight + 24}px`; });
    if (element) resize.observe(element);
    return () => { alive.current = false; resize.disconnect(); if (area) area.style.paddingBottom = ''; };
  }, []);

  useEffect(() => {
    let stopped = false;
    setLoading(true);
    api<History>(historyPath).then(data => {
      if (stopped) return;
      setTurns(data.turns); setJob(data.active_job); setError('');
      if (data.active_job) setExpanded(true);
    }).catch(e => { if (!stopped) setError(e.message); }).finally(() => { if (!stopped) setLoading(false); });
    return () => { stopped = true; };
  }, [historyPath, reload]);

  useEffect(() => {
    if (!job?.id) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const current = await api<ReportJob>('/jobs/' + job!.id);
        if (stopped) return;
        setJob(current);
        if (current.status === 'running') timer = setTimeout(poll, 700);
        else if (current.status === 'success') {
          const data = await api<History>(historyPath);
          if (!stopped) { setTurns(data.turns); setJob(null); setError(''); }
        } else { setJob(null); setError(current.error || '回答已停止，可以重新提问'); setQuestion(current.question || ''); }
      } catch (e) { if (!stopped) { setError((e as Error).message); timer = setTimeout(poll, 3000); } }
    }
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, [historyPath, job?.id]);

  useEffect(() => {
    const panel = dock.current?.querySelector('.report-qa-history');
    if (panel && (panel.scrollHeight - panel.scrollTop - panel.clientHeight < 160 || !job?.partial_reply)) panel.scrollTop = panel.scrollHeight;
  }, [expanded, turns.length, job?.id, job?.partial_reply]);

  async function send() {
    const message = question.trim();
    if (!message || sending || loading || job || disabled) return;
    setSending(true); setExpanded(true); setError('');
    if (pending.current?.message !== message) pending.current = { id: crypto.randomUUID(), message };
    try {
      const submitted = await api<ReportJob>(`/projects/${projectId}/jobs`, 'POST', {
        id: pending.current!.id, operation: 'report_chat', payload: { assessment_id: report.id, message },
      });
      if (!alive.current) return;
      pending.current = null;
      setJob(submitted); setQuestion('');
    } catch (e) { if (alive.current) setError((e as Error).message); }
    finally { if (alive.current) setSending(false); }
  }

  return <aside ref={dock} className="report-assistant" aria-label="报告问答助手">
    <div className="report-assistant-inner">
      <header><div><strong>报告问答助手</strong><small>正在解读 {new Date(report.created_at).toLocaleString('zh-CN')} 的报告</small></div>
        <button type="button" className="text-button" aria-expanded={expanded} aria-controls="report-qa-history" onClick={() => setExpanded(!expanded)}>{expanded ? '收起回答' : '查看问答'}{expanded ? <ChevronDown size={16} /> : <ChevronUp size={16} />}</button>
      </header>
      {expanded && <div id="report-qa-history" className="report-qa-history">
        {!turns.length && !job && <p className="source-location">可以问我评分依据、风险判断，或试点建议该怎么执行。</p>}
        {turns.map(turn => <div className="report-qa-turn" key={turn.id}><p><strong>你：</strong>{turn.question}</p><ChatMarkdown evidence={report.snapshot.evidence}>{turn.reply}</ChatMarkdown>{onRevise && <button type="button" className="secondary" disabled={disabled || !!job || sending} onClick={() => onRevise(report.id, turn.id)}>根据此问题修订并生成新版本</button>}</div>)}
        {job && <div className="report-qa-turn"><p><strong>你：</strong>{job.question}</p>{job.partial_reply ? <ChatMarkdown streaming evidence={report.snapshot.evidence}>{job.partial_reply}</ChatMarkdown> : <p role="status">正在结合这份报告回答…</p>}</div>}
      </div>}
      {error && <p className="report-qa-error" role="alert">{error} <button type="button" className="text-button" onClick={() => setReload(v => v + 1)}>重新连接</button></p>}
      <form onSubmit={e => { e.preventDefault(); void send(); }}>
        <textarea aria-label="向报告助手提问" placeholder="对这份报告有什么疑问？" rows={2} maxLength={6000} value={question} disabled={loading || sending || !!job || disabled} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }} />
        <button className="primary" type="submit" disabled={!question.trim() || loading || sending || !!job || disabled}><Send size={16} />{job || sending ? '回答中' : '发送'}</button>
      </form>
    </div>
  </aside>;
}
