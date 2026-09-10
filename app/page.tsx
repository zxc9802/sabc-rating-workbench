'use client';

import type { Stage, Job } from '../lib/types';
import { LifecyclePanel } from './lifecycle-panel';
import { useEffect, useState, useRef, type ReactNode } from 'react';
import { ArrowUpRight, ArrowUp, ArrowLeft, Plus, PanelLeft, FolderOpen, Building2, Database, Settings2, Check, ChevronRight, FileText, MessageSquare, ShieldCheck, CircleHelp, LoaderCircle, Paperclip, RefreshCw, X, Search, ExternalLink, TriangleAlert } from 'lucide-react';
import { api, waitForJob, Bootstrap, Detail, Project, RecordData, Settings, displayDate, text } from '../lib/types';
import { CompanyForm, EvidencePanel, ProjectForm, SettingsForm } from './workbench-forms';
import { ReportPanel } from './report-panel';
import { SessionGate } from './session-gate';
import { collectionProgress } from '../lib/collection-progress';
import { ChatAttachments } from './chat-attachments';
import { ChatReply } from './chat-reply';
import { ChatMarkdown } from './chat-markdown';

type Page = 'projects' | 'company' | 'sources' | 'settings';
const SCORE_CONFIRMATION = '我已核对当前资料，没有其他补充，请开始当前阶段评分，给出评价结论和下一步建议。';

type ProjectTab = 'chat' | 'facts' | 'evidence' | 'report';

export default function Page() { return <SessionGate>{logout => <Workbench logout={logout} />}</SessionGate>; }

function Workbench({ logout }: { logout: ReactNode }) {
  const [data, setData] = useState<Bootstrap | null>(null);
  const [page, setPage] = useState<Page>('projects');
  const [detail, setDetail] = useState<Detail | null>(null);
  const [tab, setTab] = useState<ProjectTab>('chat');
  const [busy, setBusy] = useState(false);
  const [attachmentBusy, setAttachmentBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [description, setDescription] = useState('');
  const [name, setName] = useState('');
  const [kind, setKind] = useState('growth');
  const [initialStage, setInitialStage] = useState<Stage>('pre');
  const [actualStart, setActualStart] = useState('');
  const [actualEnd, setActualEnd] = useState('');
  const [streamReply, setStreamReply] = useState('');
  const [currentJob, setCurrentJob] = useState<Job | null>(null);
  const [message, setMessage] = useState('');
  const [pendingMessage, setPendingMessage] = useState('');
  const [filter, setFilter] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const chatEnd = useRef<HTMLDivElement>(null);
  const running = useRef(false);
  const taskFinished = useRef<Promise<void>>(Promise.resolve());

  async function reload() { const fresh = await api<Bootstrap>('/bootstrap'); setData(fresh); return fresh; }
  useEffect(() => { reload().then(() => { const id = sessionStorage.getItem('sabc-project'); if (id) return openProject(id); }).catch(e => setError(e.message)); }, []);
  useEffect(() => { const timer = setInterval(() => { if (document.visibilityState === 'visible') reload().catch(() => {}); }, 60_000); return () => clearInterval(timer); }, []);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [detail?.project.messages.length, pendingMessage, busy, streamReply]);
  async function run(action: () => Promise<void>, success = '') {
    if (running.current) return;
    running.current = true;
    let finish!: () => void;
    taskFinished.current = new Promise<void>(resolve => { finish = resolve; });
    setBusy(true); setError(''); setNotice('');
    try { await action(); if (success) setNotice(success); }
    catch (e) { if (e instanceof Error && e.message === '已停止回答') setNotice('已停止回答，已保存的项目和资料仍然保留。'); else setError(e instanceof Error ? e.message : '操作失败，请重试。'); }
    finally { running.current = false; setBusy(false); finish(); }
  }
  async function openProject(id: string) { await run(async () => {
    sessionStorage.setItem('sabc-project', id);
    const fresh = await api<Detail>('/projects/' + id);
    setDetail(fresh); setPage('projects'); setTab('chat');
    if (fresh.active_jobs?.length) {
      try { for (const job of fresh.active_jobs) { setCurrentJob(job); await waitForJob(job.id, setStreamReply, setCurrentJob); } }
      finally { const fresh = await api<Detail>('/projects/' + id); setDetail(fresh); setStreamReply(''); await reload(); }
    } else if (!fresh.project.messages.length) {
      await initialReply(id);
    }
  }); }
  async function initialReply(id: string, retry = false) {
    try {
      const job = await api<Job>('/projects/' + id + '/start-interview' + (retry ? '?retry=true' : ''), 'POST');
      setCurrentJob(job);
      if (job.id) await waitForJob(job.id, setStreamReply, setCurrentJob);
    } finally { const fresh = await api<Detail>('/projects/' + id); setDetail(fresh); setStreamReply(''); await reload(); }
  }
  async function stopReply() {
    if (!currentJob || currentJob.status !== 'running') return false;
    try { setCurrentJob(await api<Job>('/jobs/' + currentJob.id + '/cancel', 'POST')); setStreamReply(''); return true; }
    catch (e) { setError(e instanceof Error ? e.message : '停止失败，请重试'); return false; }
  }
  async function refreshProject() { if (detail) setDetail(await api<Detail>('/projects/' + detail.project.id)); await reload(); }
  async function createProject() {
    if (!description.trim()) { setError('先描述你想做的项目。'); return; }
    await run(async () => {
      const p = await api<Project>('/projects', 'POST', { name: name.trim() || description.trim().slice(0, 24), description, project_type: kind, stage: initialStage, actual_start: actualStart, actual_end: actualEnd, auto_start: true });
      sessionStorage.setItem('sabc-project', p.id);
      setDetail({ project: p, evidence: [], assessments: [] }); setTab('chat'); setDescription(''); setName(''); setMessage('');
      setStreamReply('');
      await reload();
      await initialReply(p.id);
    });
  }
  async function sendMessage(content = message) {
    if (!content.trim() || !detail || attachmentBusy || running.current) return;
    const sent = content.trim();
    const last = detail.project.messages.at(-1);
    await run(async () => {
      setPendingMessage(sent); setMessage(''); setStreamReply(''); setCurrentJob(null);
      try {
        await api('/projects/' + detail.project.id + '/chat', 'POST', { message: sent, field: last?.role === 'assistant' ? last.field : undefined }, setStreamReply, setCurrentJob);
      } catch (error) {
        setMessage(draft => draft || sent);
        throw error;
      } finally {
        // Reconcile the persisted conversation before removing the optimistic turn.
        try {
          const fresh = await api<Detail>('/projects/' + detail.project.id);
          setDetail(fresh);
        } finally { setPendingMessage(''); setStreamReply(''); }
        await reload();
      }
    });
  }
  async function confirmScoring() {
    await sendMessage(SCORE_CONFIRMATION);
  }
  async function deleteProjects(ids: string[]) {
    if (!ids.length || (busy && currentJob?.status !== 'running')) return;
    if (busy && currentJob?.project_id && !ids.includes(currentJob.project_id)) { setNotice('请先停止当前回答，再删除其他项目。'); return; }
    if (!window.confirm(`确认删除这 ${ids.length} 个项目？进行中的任务会一并停止。项目及关联资料将不再显示，后台保留历史审计记录。`)) return;
    if (running.current && currentJob?.status === 'running') {
      if (!await stopReply()) return;
      await taskFinished.current;
    }
    await run(async () => {
      await api('/projects/delete', 'POST', { ids });
      if (ids.includes(sessionStorage.getItem('sabc-project') || '')) sessionStorage.removeItem('sabc-project');
      if (detail && ids.includes(detail.project.id)) setDetail(null);
      setSelected([]); await reload();
    }, '项目已删除');
  }
  const visibleProjects = data?.projects.filter(p => p.name.includes(filter)) || [];
  const nav = [{ id: 'projects' as Page, title: '项目评估', icon: FolderOpen }, { id: 'company' as Page, title: '公司资料', icon: Building2 }, ];
  const companyReady = !!data?.company.confirmed;
  const titles = { projects: '项目评估', company: '公司资料', sources: '数据来源', settings: '模型设置' };
  const projectFields = ['target_user', 'business_goal', 'value_mechanism', 'success_metric', 'timeframe', 'budget_requested', 'risks'];
  const completed = detail ? projectFields.filter(k => text(detail.project.pending_patch?.[k] ?? detail.project[k]) && !['未知', '不知道'].includes(text(detail.project.pending_patch?.[k] ?? detail.project[k]))).length : 0;

  const coverage = detail?.project.lifecycle?.coverage;
  const collection = collectionProgress(detail?.project.lifecycle);
  const informationReady = collection.ready;
  const lastUserTurn = detail?.project.messages.filter(m => m.role === 'user').at(-1);
  const scoringRequested = lastUserTurn?.content === SCORE_CONFIRMATION && !!lastUserTurn.time &&
    !!detail?.project.lifecycle?.review?.time && detail.project.lifecycle.review.time >= lastUserTurn.time;

  return <div className="workspace">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="SABC 项目评级首页"><span className="brand-symbol"><span /><span /><span /><span /></span><strong>SABC<span>项目评级工作台</span></strong></a>
      <button className="new-project" onClick={() => { sessionStorage.removeItem('sabc-project'); setPage('projects'); setDetail(null); }}><Plus size={18} /> 新建项目评估</button>
      <nav aria-label="主导航">{nav.map(item => <button key={item.id} className={page === item.id ? 'nav-item active' : 'nav-item'} onClick={() => { setPage(item.id); setNotice(''); setError(''); }}><item.icon size={18} />{item.title}{item.id === 'projects' && !!data?.projects.length && <span className="nav-count">{data.projects.length}</span>}</button>)}</nav>
      <div className="sidebar-note"><ShieldCheck size={18} /><p>先看依据，再做决定<span>每次评级保留公司版本与证据。</span></p></div>
      <div className="sidebar-footer"><span className="workspace-avatar">本</span><div>私有工作空间<small>当前账号 · 数据独立保存</small></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><PanelLeft size={17} /><span>工作空间</span><ChevronRight size={14} /><strong>{titles[page]}</strong></div><div className="topbar-actions">{logout}<button className="baseline-status" onClick={() => setPage('company')}><span className={'status-dot ' + (companyReady ? 'ready' : '')} />{companyReady ? '公司基线 v' + text(data?.company.version) : '公司资料待完善'}<ChevronRight size={14} /></button></div></header>
      {currentJob?.status === 'running' && <div className="feedback" role="status"><LoaderCircle size={18} className="spin" /><span>{currentJob.phase === 'queued' ? '任务已提交，正在排队…' : streamReply ? '正在回答…' : '任务已提交，正在分析…'}</span><button className="secondary" onClick={stopReply}>停止回答</button></div>}
      {error && <div className="feedback error" role="alert"><TriangleAlert size={18} /><span>{error}</span><button aria-label="关闭错误提示" onClick={() => setError('')}><X size={16} /></button></div>}
      {notice && <div className="feedback success" role="status"><Check size={18} /><span>{notice}</span><button aria-label="关闭成功提示" onClick={() => setNotice('')}><X size={16} /></button></div>}
      {!data ? <main className="loading-page"><LoaderCircle className="spin" /> <p>{error ? '应用服务尚未连接' : '正在打开工作台…'}</p><button className="secondary" onClick={() => run(async () => { await reload(); })}>重新连接</button></main> :
        page === 'company' ? <main className="page-content"><div className="page-heading"><div><h1>公司的现状，是评级的起点。</h1><p>维护一次，在各个项目中引用。变更后保存为新版本，历史报告保留原有依据。</p></div><Building2 className="heading-icon" size={30} /></div><CompanyForm company={data.company} busy={busy} save={body => run(async () => { await api('/company', 'PUT', body); await reload(); }, '公司资料已保存为新版本')} /></main> :
        page === 'settings' ? <main className="page-content narrow"><div className="page-heading"><div><h1>连接分析模型</h1><p>让智能体理解项目描述、选择关键追问，并提出有依据的评分建议。</p></div></div>{data.settings.primary_model && <p className="review-note">访谈模型：{data.settings.primary_model} · 选源模型：{data.settings.planner_model} · 兜底模型：{data.settings.fallback_model || '未配置'}。</p>}<SettingsForm settings={data.settings} busy={busy || !!data.settings.managed} save={body => run(async () => { await api<Settings>('/settings', 'PUT', body); await reload(); }, '模型配置已保存')} /><div className="quiet-note"><ShieldCheck size={18} /><p>最终等级始终由评分规则计算。模型只能提出建议，不能更改权重、证据上限或否决条件。</p></div></main> :
        page === 'sources' ? <main className="page-content"><div className="page-heading"><div><h1>让判断有出处。</h1><p>按项目所需选择来源。可在项目的证据资料中调用已提供的官方接口。</p></div><span className="count-label">{data.sources.length} 类候选来源</span></div><div className="source-table"><div className="source-row table-head"><span>数据来源</span><span>可以补充什么</span><span>访问方式</span><span>接入状态</span></div>{data.sources.map(source => <div className="source-row" key={source.id}><a href={source.url} target="_blank" rel="noreferrer">{source.name}<ExternalLink size={13} /></a><span>{source.purpose}</span><span>{source.access}</span><span className="status-label">{source.status === 'connected' ? '已取数入库' : source.status === 'available' ? '可取数' : source.status === 'browser' ? '需浏览器' : '待接入'}</span></div>)}</div><p className="footnote">“已取数入库”仅表示工作空间曾成功保存该来源的数据，不代表全部查询能力已实现或当前登录仍有效。浏览器来源需要实际采集后导入；详细限制见各来源访问方式。</p></main> :
        !detail ? <main className="page-content projects-home">
          <div className="home-heading"><h1>这个项目，现在值得做吗？</h1><p>先说说你的想法。我们一起把目标、投入与关键依据理清楚。</p></div>
          {!companyReady && <button className="company-prompt" onClick={() => setPage('company')}><Building2 size={21} /><span><strong>先填写公司信息，再进行项目评估会更准确</strong><small>填写公司的战略、预算和团队情况，让评估更贴近实际。</small></span><span className="company-prompt-action">填写公司信息 <ArrowUpRight size={18} /></span></button>}
          <div className="start-layout"><section className="project-composer" aria-label="新建项目"><div className="composer-heading"><span className="small-icon"><MessageSquare size={20} /></span><h2>从一个项目想法开始</h2></div><label className="sr-only" htmlFor="description">描述你的项目</label><textarea id="description" className="idea-input" value={description} onChange={e => setDescription(e.target.value)} placeholder="比如：我们想用 AI 客服处理重复咨询，让客服团队把时间放在成交上。现在每天大约有……" maxLength={12000} /><div className="composer-options"><label>项目名称<input value={name} onChange={e => setName(e.target.value)} placeholder="可选，方便之后查找" maxLength={100} /></label><label>项目类型<select value={kind} onChange={e => setKind(e.target.value)}>{Object.entries(data.types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label></div><div className="composer-options"><label>项目实际阶段<select value={initialStage} onChange={e => setInitialStage(e.target.value as Stage)}><option value="pre">启动前（尚未试点）</option><option value="during">试点中（已实际开始）</option><option value="post">试点后（已结束或停止）</option></select></label>{initialStage !== 'pre' && <label>实际开始日期<input type="date" value={actualStart} onChange={e => setActualStart(e.target.value)} /></label>}{initialStage === 'post' && <label>实际结束日期<input type="date" value={actualEnd} onChange={e => setActualEnd(e.target.value)} /></label>}</div><div className="composer-bottom"><span><ShieldCheck size={14} /> 信息不够时，会先追问</span><button className="primary" disabled={busy || !description.trim()} onClick={createProject}>开始评估{busy ? <LoaderCircle className="spin" size={17} /> : <ArrowUpRight size={17} />}</button></div></section>
          <aside className="decision-guide"><h2>不是每个想法，都需要立刻下注。</h2><p>评级对应当前可采取的行动，随公司条件与证据变化而复评。</p><div className="grade-key">{[['S', '集中资源放大'], ['A', '分阶段正式投入'], ['B', '先做小规模验证'], ['C', '当前不建议立项']].map(([g, label]) => <div key={g}><span className={'grade-letter grade-' + g}>{g}</span><span>{label}</span></div>)}</div><div className="nr-explainer"><span className="grade-letter grade-NR">NR</span><span>资料不足，暂不评级<br /><small>“还不知道”不等于“不值得”。</small></span></div></aside></div>
          <section className="recent-projects"><div className="section-heading"><h2>项目记录 <span>{data.projects.length}</span></h2>{!!data.projects.length && <label className="search-input"><Search size={16} /><input aria-label="搜索项目" placeholder="搜索项目" value={filter} onChange={e => { setFilter(e.target.value); setSelected([]); }} /></label>}</div>{!!visibleProjects.length && <div className="project-selection"><label><input type="checkbox" aria-label="选择当前搜索结果" checked={visibleProjects.every(p => selected.includes(p.id))} onChange={e => setSelected(e.target.checked ? visibleProjects.map(p => p.id) : [])} /> 全选当前结果</label><button className="secondary" disabled={(busy && currentJob?.status !== 'running') || !selected.length} onClick={() => deleteProjects(selected)}>删除所选（{selected.length}）</button></div>}{data.projects.length ? <div className="project-list">{visibleProjects.map(p => <div className="project-list-item" key={p.id}><input type="checkbox" aria-label={'选择项目：' + p.name} checked={selected.includes(p.id)} onChange={e => setSelected(e.target.checked ? [...selected, p.id] : selected.filter(id => id !== p.id))} /><button className="project-row" onClick={() => openProject(p.id)}><span className="document-icon"><FileText size={22} /></span><span className="project-row-title"><strong>{p.name}</strong><small>{data.types[p.project_type]} · {displayDate(p.updated_at)} 更新{p.followup && ` · ${p.followup.due ? '待回访' : '下次回访'} ${p.followup.date}`}</small></span><span className={'grade-badge grade-' + (p.last_grade || 'NR')}>{p.last_grade || '待评估'}</span><ChevronRight size={17} /></button><button className="text-button project-delete" disabled={busy && currentJob?.status !== 'running'} aria-label={'删除项目：' + p.name} onClick={() => deleteProjects([p.id])}>删除</button></div>)}</div> : <div className="empty-records"><FolderOpen size={25} /><p>你的第一份评估，会保存在这里。</p><span>可以随时补充证据，回来看评级如何变化。</span></div>}</section>
        </main> : <main className="page-content project-detail">
          <button className="back-link" onClick={() => { sessionStorage.removeItem('sabc-project'); setDetail(null); }}><ArrowLeft size={15} /> 全部项目</button><div className="project-title"><div><h1>{detail.project.name}</h1><p>{data.types[detail.project.project_type]}<span>·</span> 项目 v{detail.project.version}<span>·</span> {displayDate(detail.project.updated_at)} 更新</p></div><span className={'grade-badge large grade-' + (detail.project.last_grade || 'NR')}>{detail.project.last_grade || '待评估'}</span></div>
          <LifecyclePanel detail={detail} dimensions={data.dimensions} busy={busy || attachmentBusy} run={run} refresh={refreshProject} onFollowup={sendMessage} />
          <div className="project-tabs" role="tablist" aria-label="项目工作区">{[{ id: 'chat' as ProjectTab, label: '项目访谈', icon: MessageSquare }, { id: 'facts' as ProjectTab, label: '项目资料', icon: FileText }, { id: 'evidence' as ProjectTab, label: '证据资料', icon: Paperclip }, { id: 'report' as ProjectTab, label: '阶段评价与方案', icon: ShieldCheck }].map(t => <button role="tab" aria-selected={tab === t.id} key={t.id} className={tab === t.id ? 'selected' : ''} onClick={() => setTab(t.id)}><t.icon size={16} />{t.label}{t.id === 'evidence' && <span>{detail.evidence.length}</span>}</button>)}</div>
          {tab === 'chat' ? <div className="interview-layout"><section className="conversation"><div className="conversation-heading"><span className="assistant-mark">S</span><div><strong>项目分析助手</strong><small>{data.settings.configured ? '根据已有资料，追问关键问题' : '结构化引导 · 分析模型尚未连接'}</small></div></div><div className="messages">{!detail.project.messages.length && <><div className="message user"><div className="message-label">项目描述</div><p>{text(detail.project.description)}</p></div>{!busy && <div className="message assistant"><p>首次回答尚未完成，可以重试。</p><button className="primary" disabled={attachmentBusy} onClick={() => run(() => initialReply(detail.project.id, true))}>重试回答</button></div>}</>}{detail.project.messages.map((m, i) => <div className={'message ' + m.role} key={i}><div className="message-label">{m.role === 'user' ? '你' : '分析助手'}</div>{m.role === 'assistant' ? <ChatReply message={m} evidence={detail.evidence} onEvidence={() => setTab('evidence')} /> : <p>{m.content}</p>}</div>)}{pendingMessage && <div className="message user"><div className="message-label">你</div><p>{pendingMessage}</p></div>}{busy && streamReply && <div className="message assistant"><div className="message-label">分析助手 · 正在生成</div><ChatMarkdown evidence={detail.evidence} streaming onEvidence={() => setTab('evidence')}>{streamReply}</ChatMarkdown></div>}{busy && !streamReply && <div className="thinking" role="status"><LoaderCircle size={15} className="spin" />正在思考…</div>}{!busy && informationReady && <div className="message assistant scoring-confirmation" role="status">
  {scoringRequested && detail.project.lifecycle?.review ? <><strong>本轮阶段评价已生成</strong><p>{detail.project.lifecycle.review.summary}</p><button className="primary" onClick={() => setTab('report')}>查看评价与下一步</button><p>如有补充，可继续在下方发送，我们会重新核对。</p></> : <><strong>评分信息已收集完整</strong><p>八个维度已完成本阶段梳理。现在可以评分，还是有其他信息需要补充？</p>{data.dimensions.some(d => coverage?.[d.key]?.status !== 'known') && <p>尚未知、需外部核查或等待试点验证的内容会保留，不会当作已验证事实。</p>}<div className="scoring-actions"><button className="primary" disabled={attachmentBusy} onClick={confirmScoring}>开始评分</button><button className="secondary" onClick={() => document.getElementById('message')?.focus()}>我还有信息要补充</button></div><p>补充后会重新核对，再请你确认是否评分。</p></>}
</div>}<div ref={chatEnd} /></div><div className="composer-tools"><ChatAttachments key={detail.project.id} projectId={detail.project.id} disabled={busy || attachmentBusy} onBusy={setAttachmentBusy} onSaved={refreshProject} /><div className="collection-progress" aria-live="polite"><span>信息收集 {collection.percent}%</span><progress aria-label="本阶段八维信息收集进度" max={100} value={collection.percent} /><small>{collection.complete}/8 维已梳理{busy ? ' · 核对中' : ''}</small></div></div><form className="chat-form" onSubmit={e => { e.preventDefault(); sendMessage(); }}><label className="sr-only" htmlFor="message">回答或补充项目内容</label><textarea id="message" value={message} onChange={e => setMessage(e.target.value)} placeholder="回答问题，或补充新的项目信息…" rows={2} maxLength={12000} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); sendMessage(); } }} /><div><span>Enter 发送 · Shift + Enter 换行</span>{busy ? <button className="send-button" aria-label="停止回答" title="停止回答" type="button" disabled={currentJob?.status !== 'running'} onClick={stopReply}><X size={20} /></button> : <button className="send-button" aria-label="发送消息" disabled={attachmentBusy || !message.trim()} type="submit"><ArrowUp size={20} /></button>}</div></form></section>
          <aside className="context-panel"><h2>这次评估的依据</h2><div className="context-block"><span>公司现状</span><strong>{text(data.company.name) || '尚未建立公司资料'}</strong><button className="text-button" onClick={() => setPage('company')}>{companyReady ? '查看公司基线' : '补充公司资料'}<ChevronRight size={14} /></button></div><div className="context-block"><span>项目关键信息</span><strong>{completed} / 7 项已整理</strong><div className="fact-progress" aria-label={`7项信息中已整理${completed}项`}>{projectFields.map(k => <i key={k} className={text(detail.project.pending_patch?.[k] ?? detail.project[k]) ? 'complete' : ''} />)}</div><button className="text-button" onClick={() => setTab('facts')}>检查项目资料<ChevronRight size={14} /></button></div><div className="context-block"><span>证据资料</span><strong>{detail.evidence.length} 条已保存</strong><button className="text-button" onClick={() => setTab('evidence')}>添加或核验资料<ChevronRight size={14} /></button></div><div className="context-tip"><CircleHelp size={17} /><p>不确定的信息可以直说。关键依据不足时，先补资料，不急着给等级。</p></div>{detail.project.pending_patch && Object.keys(detail.project.pending_patch).length > 0 && <button className="secondary" onClick={() => setTab('facts')}>核对模型整理的事实</button>}<button className="primary full" onClick={() => setTab('report')}>查看阶段评价与下一步<ArrowUpRight size={16} /></button></aside></div> :
          tab === 'facts' ? <ProjectForm project={detail.project} types={data.types} busy={busy} save={body => run(async () => { await api('/projects/' + detail.project.id, 'PATCH', body); await refreshProject(); }, '项目资料已保存')} /> :
          tab === 'evidence' ? <EvidencePanel projectId={detail.project.id} evidence={detail.evidence} busy={busy} run={run} refresh={refreshProject} /> :
          <><LifecyclePanel full detail={detail} dimensions={data.dimensions} busy={busy} run={run} refresh={refreshProject} />{detail.project.lifecycle?.confirmed && detail.project.lifecycle.stage === 'post' && <ReportPanel detail={detail} dimensions={data.dimensions} busy={busy} run={run} refresh={refreshProject} />}</>}
        </main>}
      <footer className="page-footer"><span>SABC 项目评级</span><span>依据当前信息提供决策参考 · 实际准确性需历史案例验证</span></footer>
    </div>
  </div>;
}
