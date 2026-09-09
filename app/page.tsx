'use client';

import { useEffect, useState, useRef } from 'react';
import { ArrowUpRight, ArrowUp, ArrowLeft, Plus, PanelLeft, FolderOpen, Building2, Database, Settings2, Check, ChevronRight, FileText, MessageSquare, ShieldCheck, CircleHelp, LoaderCircle, Paperclip, RefreshCw, X, Search, ExternalLink, TriangleAlert } from 'lucide-react';
import { api, waitForJob, Bootstrap, Detail, Project, RecordData, Settings, displayDate, text } from '../lib/types';
import { CompanyForm, EvidencePanel, ProjectForm, SettingsForm } from './workbench-forms';
import { ReportPanel } from './report-panel';
import { SessionGate } from './session-gate';

type Page = 'projects' | 'company' | 'sources' | 'settings';
type ProjectTab = 'chat' | 'facts' | 'evidence' | 'report';

export default function Page() { return <SessionGate><Workbench /></SessionGate>; }

function Workbench() {
  const [data, setData] = useState<Bootstrap | null>(null);
  const [page, setPage] = useState<Page>('projects');
  const [detail, setDetail] = useState<Detail | null>(null);
  const [tab, setTab] = useState<ProjectTab>('chat');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [description, setDescription] = useState('');
  const [name, setName] = useState('');
  const [kind, setKind] = useState('growth');
  const [message, setMessage] = useState('');
  const [filter, setFilter] = useState('');
  const chatEnd = useRef<HTMLDivElement>(null);
  const running = useRef(false);

  async function reload() { const fresh = await api<Bootstrap>('/bootstrap'); setData(fresh); return fresh; }
  useEffect(() => { reload().then(() => { const id = sessionStorage.getItem('sabc-project'); if (id) return openProject(id); }).catch(e => setError(e.message)); }, []);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [detail?.project.messages.length]);
  async function run(action: () => Promise<void>, success = '') {
    if (running.current) return;
    running.current = true;
    setBusy(true); setError(''); setNotice('');
    try { await action(); if (success) setNotice(success); }
    catch (e) { setError(e instanceof Error ? e.message : '操作失败，请重试。'); }
    finally { running.current = false; setBusy(false); }
  }
  async function openProject(id: string) { await run(async () => {
    sessionStorage.setItem('sabc-project', id);
    const fresh = await api<Detail>('/projects/' + id);
    setDetail(fresh); setPage('projects'); setTab('chat');
    if (fresh.active_jobs?.length) {
      try { for (const job of fresh.active_jobs) await waitForJob(job.id); }
      finally { setDetail(await api<Detail>('/projects/' + id)); await reload(); }
    }
  }); }
  async function refreshProject() { if (detail) setDetail(await api<Detail>('/projects/' + detail.project.id)); await reload(); }
  async function createProject() {
    if (!description.trim()) { setError('先描述你想做的项目。'); return; }
    await run(async () => {
      const p = await api<Project>('/projects', 'POST', { name: name.trim() || description.trim().slice(0, 24), description, project_type: kind });
      sessionStorage.setItem('sabc-project', p.id);
      setDetail(await api<Detail>('/projects/' + p.id)); setTab('chat'); setDescription(''); setName(''); await reload();
    });
  }
  async function sendMessage() {
    if (!message.trim() || !detail) return;
    const last = detail.project.messages.at(-1);
    await run(async () => {
      await api('/projects/' + detail.project.id + '/chat', 'POST', { message, field: last?.role === 'assistant' ? last.field : undefined });
      setMessage(''); await refreshProject();
    });
  }
  const nav = [{ id: 'projects' as Page, title: '项目评估', icon: FolderOpen }, { id: 'company' as Page, title: '公司资料', icon: Building2 }, { id: 'sources' as Page, title: '数据来源', icon: Database }, { id: 'settings' as Page, title: '模型设置', icon: Settings2 }];
  const companyReady = !!data?.company.confirmed;
  const titles = { projects: '项目评估', company: '公司资料', sources: '数据来源', settings: '模型设置' };
  const projectFields = ['target_user', 'business_goal', 'value_mechanism', 'success_metric', 'timeframe', 'budget_requested', 'risks'];
  const completed = detail ? projectFields.filter(k => text(detail.project[k]) && !['未知', '不知道'].includes(text(detail.project[k]))).length : 0;

  return <div className="workspace">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="SABC 项目评级首页"><span className="brand-symbol"><span /><span /><span /><span /></span><strong>SABC<span>项目评级工作台</span></strong></a>
      <button className="new-project" onClick={() => { sessionStorage.removeItem('sabc-project'); setPage('projects'); setDetail(null); }}><Plus size={18} /> 新建项目评估</button>
      <nav aria-label="主导航">{nav.map(item => <button key={item.id} className={page === item.id ? 'nav-item active' : 'nav-item'} onClick={() => { setPage(item.id); setNotice(''); setError(''); }}><item.icon size={18} />{item.title}{item.id === 'projects' && !!data?.projects.length && <span className="nav-count">{data.projects.length}</span>}</button>)}</nav>
      <div className="sidebar-note"><ShieldCheck size={18} /><p>先看依据，再做决定<span>每次评级保留公司版本与证据。</span></p></div>
      <div className="sidebar-footer"><span className="workspace-avatar">本</span><div>私有工作空间<small>单公司 · 数据持久保存</small></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb"><PanelLeft size={17} /><span>工作空间</span><ChevronRight size={14} /><strong>{titles[page]}</strong></div><button className="baseline-status" onClick={() => setPage('company')}><span className={'status-dot ' + (companyReady ? 'ready' : '')} />{companyReady ? '公司基线 v' + text(data?.company.version) : '公司资料待完善'}<ChevronRight size={14} /></button></header>
      {error && <div className="feedback error" role="alert"><TriangleAlert size={18} /><span>{error}</span><button aria-label="关闭错误提示" onClick={() => setError('')}><X size={16} /></button></div>}
      {notice && <div className="feedback success" role="status"><Check size={18} /><span>{notice}</span><button aria-label="关闭成功提示" onClick={() => setNotice('')}><X size={16} /></button></div>}
      {!data ? <main className="loading-page"><LoaderCircle className="spin" /> <p>{error ? '应用服务尚未连接' : '正在打开工作台…'}</p><button className="secondary" onClick={() => run(async () => { await reload(); })}>重新连接</button></main> :
        page === 'company' ? <main className="page-content"><div className="page-heading"><div><h1>公司的现状，是评级的起点。</h1><p>维护一次，在各个项目中引用。变更后保存为新版本，历史报告保留原有依据。</p></div><Building2 className="heading-icon" size={30} /></div><CompanyForm company={data.company} busy={busy} save={body => run(async () => { await api('/company', 'PUT', body); await reload(); }, '公司资料已保存为新版本')} /></main> :
        page === 'settings' ? <main className="page-content narrow"><div className="page-heading"><div><h1>连接分析模型</h1><p>让智能体理解项目描述、选择关键追问，并提出有依据的评分建议。</p></div></div><SettingsForm settings={data.settings} busy={busy} save={body => run(async () => { await api<Settings>('/settings', 'PUT', body); await reload(); }, '模型配置已保存')} /><div className="quiet-note"><ShieldCheck size={18} /><p>最终等级始终由评分规则计算。模型只能提出建议，不能更改权重、证据上限或否决条件。</p></div></main> :
        page === 'sources' ? <main className="page-content"><div className="page-heading"><div><h1>让判断有出处。</h1><p>按项目所需选择来源。可在项目的证据资料中调用已提供的官方接口。</p></div><span className="count-label">{data.sources.length} 类候选来源</span></div><div className="source-table"><div className="source-row table-head"><span>数据来源</span><span>可以补充什么</span><span>访问方式</span><span>接入状态</span></div>{data.sources.map(source => <div className="source-row" key={source.id}><a href={source.url} target="_blank" rel="noreferrer">{source.name}<ExternalLink size={13} /></a><span>{source.purpose}</span><span>{source.access}</span><span className="status-label">{source.status === 'connected' ? '已取数入库' : source.status === 'available' ? '可取数' : source.status === 'browser' ? '需浏览器' : '待接入'}</span></div>)}</div><p className="footnote">“已取数入库”仅表示工作空间曾成功保存该来源的数据，不代表全部查询能力已实现或当前登录仍有效。浏览器来源需要实际采集后导入；详细限制见各来源访问方式。</p></main> :
        !detail ? <main className="page-content projects-home">
          <div className="home-heading"><h1>这个项目，现在值得做吗？</h1><p>先说说你的想法。我们一起把目标、投入与关键依据理清楚。</p></div>
          <div className="start-layout"><section className="project-composer" aria-label="新建项目"><div className="composer-heading"><span className="small-icon"><MessageSquare size={20} /></span><h2>从一个项目想法开始</h2></div><label className="sr-only" htmlFor="description">描述你的项目</label><textarea id="description" className="idea-input" value={description} onChange={e => setDescription(e.target.value)} placeholder="比如：我们想用 AI 客服处理重复咨询，让客服团队把时间放在成交上。现在每天大约有……" maxLength={12000} /><div className="composer-options"><label>项目名称<input value={name} onChange={e => setName(e.target.value)} placeholder="可选，方便之后查找" maxLength={100} /></label><label>项目类型<select value={kind} onChange={e => setKind(e.target.value)}>{Object.entries(data.types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label></div><div className="composer-bottom"><span><ShieldCheck size={14} /> 信息不够时，会先追问</span><button className="primary" disabled={busy || !description.trim()} onClick={createProject}>开始评估{busy ? <LoaderCircle className="spin" size={17} /> : <ArrowUpRight size={17} />}</button></div></section>
          <aside className="decision-guide"><h2>不是每个想法，都需要立刻下注。</h2><p>评级对应当前可采取的行动，随公司条件与证据变化而复评。</p><div className="grade-key">{[['S', '集中资源放大'], ['A', '分阶段正式投入'], ['B', '先做小规模验证'], ['C', '当前不建议立项']].map(([g, label]) => <div key={g}><span className={'grade-letter grade-' + g}>{g}</span><span>{label}</span></div>)}</div><div className="nr-explainer"><span className="grade-letter grade-NR">NR</span><span>资料不足，暂不评级<br /><small>“还不知道”不等于“不值得”。</small></span></div></aside></div>
          {!companyReady && <button className="company-prompt" onClick={() => setPage('company')}><Building2 size={21} /><span><strong>补充公司资料，让判断更贴近实际</strong><small>当前战略、可用预算和团队能力，会直接影响同一个项目的评级。</small></span><ArrowUpRight size={18} /></button>}
          <section className="recent-projects"><div className="section-heading"><h2>项目记录 <span>{data.projects.length}</span></h2>{!!data.projects.length && <label className="search-input"><Search size={16} /><input aria-label="搜索项目" placeholder="搜索项目" value={filter} onChange={e => setFilter(e.target.value)} /></label>}</div>{data.projects.length ? <div className="project-list">{data.projects.filter(p => p.name.includes(filter)).map(p => <button className="project-row" key={p.id} onClick={() => openProject(p.id)}><span className="document-icon"><FileText size={22} /></span><span className="project-row-title"><strong>{p.name}</strong><small>{data.types[p.project_type]} · {displayDate(p.updated_at)} 更新</small></span><span className={'grade-badge grade-' + (p.last_grade || 'NR')}>{p.last_grade || '待评估'}</span><ChevronRight size={17} /></button>)}</div> : <div className="empty-records"><FolderOpen size={25} /><p>你的第一份评估，会保存在这里。</p><span>可以随时补充证据，回来看评级如何变化。</span></div>}</section>
        </main> : <main className="page-content project-detail">
          <button className="back-link" onClick={() => { sessionStorage.removeItem('sabc-project'); setDetail(null); }}><ArrowLeft size={15} /> 全部项目</button><div className="project-title"><div><h1>{detail.project.name}</h1><p>{data.types[detail.project.project_type]}<span>·</span> 项目 v{detail.project.version}<span>·</span> {displayDate(detail.project.updated_at)} 更新</p></div><span className={'grade-badge large grade-' + (detail.project.last_grade || 'NR')}>{detail.project.last_grade || '待评估'}</span></div>
          <div className="project-tabs" role="tablist" aria-label="项目工作区">{[{ id: 'chat' as ProjectTab, label: '项目访谈', icon: MessageSquare }, { id: 'facts' as ProjectTab, label: '项目资料', icon: FileText }, { id: 'evidence' as ProjectTab, label: '证据资料', icon: Paperclip }, { id: 'report' as ProjectTab, label: '评级报告', icon: ShieldCheck }].map(t => <button role="tab" aria-selected={tab === t.id} key={t.id} className={tab === t.id ? 'selected' : ''} onClick={() => setTab(t.id)}><t.icon size={16} />{t.label}{t.id === 'evidence' && <span>{detail.evidence.length}</span>}</button>)}</div>
          {tab === 'chat' ? <div className="interview-layout"><section className="conversation"><div className="conversation-heading"><span className="assistant-mark">S</span><div><strong>项目分析助手</strong><small>{data.settings.configured ? '根据已有资料，追问关键问题' : '结构化引导 · 分析模型尚未连接'}</small></div></div><div className="messages">{!detail.project.messages.length && <><div className="message user"><div className="message-label">项目描述</div><p>{text(detail.project.description)}</p></div><div className="message assistant"><div className="message-label">分析助手</div><p>{data.settings.configured ? '说说你最想确认的问题，我会结合项目描述与公司资料继续分析。' : '我们先把项目的信息整理完整。点击下方发送“开始整理”，按顺序补充关键信息。连接分析模型后，可以进行自由对话和评分分析。'}</p></div></>}{detail.project.messages.map((m, i) => <div className={'message ' + m.role} key={i}><div className="message-label">{m.role === 'user' ? '你' : '分析助手'}</div><p>{m.content}</p></div>)}{busy && <div className="thinking"><LoaderCircle size={15} className="spin" />正在处理…</div>}<div ref={chatEnd} /></div><form className="chat-form" onSubmit={e => { e.preventDefault(); sendMessage(); }}><label className="sr-only" htmlFor="message">回答或补充项目内容</label><textarea id="message" value={message} onChange={e => setMessage(e.target.value)} placeholder={detail.project.messages.length ? '回答问题，或补充新的项目信息…' : '输入“开始整理”，或说说你最关心的问题…'} rows={2} maxLength={12000} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); sendMessage(); } }} /><div><span>Enter 发送 · Shift + Enter 换行</span><button className="send-button" aria-label="发送消息" disabled={busy || !message.trim()} type="submit"><ArrowUp size={20} /></button></div></form></section>
          <aside className="context-panel"><h2>这次评估的依据</h2><div className="context-block"><span>公司现状</span><strong>{text(data.company.name) || '尚未建立公司资料'}</strong><button className="text-button" onClick={() => setPage('company')}>{companyReady ? '查看公司基线' : '补充公司资料'}<ChevronRight size={14} /></button></div><div className="context-block"><span>项目关键信息</span><strong>{completed} / 7 项已整理</strong><div className="fact-progress" aria-label={`7项信息中已整理${completed}项`}>{projectFields.map(k => <i key={k} className={text(detail.project[k]) ? 'complete' : ''} />)}</div><button className="text-button" onClick={() => setTab('facts')}>检查项目资料<ChevronRight size={14} /></button></div><div className="context-block"><span>证据资料</span><strong>{detail.evidence.length} 条已保存</strong><button className="text-button" onClick={() => setTab('evidence')}>添加或核验资料<ChevronRight size={14} /></button></div><div className="context-tip"><CircleHelp size={17} /><p>不确定的信息可以直说。关键依据不足时，先补资料，不急着给等级。</p></div>{detail.project.pending_patch && Object.keys(detail.project.pending_patch).length > 0 && <button className="secondary" onClick={() => setTab('facts')}>核对模型整理的事实</button>}<button className="primary full" onClick={() => setTab('report')}>查看评级与下一步<ArrowUpRight size={16} /></button></aside></div> :
          tab === 'facts' ? <ProjectForm project={detail.project} types={data.types} busy={busy} save={body => run(async () => { await api('/projects/' + detail.project.id, 'PATCH', body); await refreshProject(); }, '项目资料已保存')} /> :
          tab === 'evidence' ? <EvidencePanel projectId={detail.project.id} evidence={detail.evidence} busy={busy} run={run} refresh={refreshProject} /> :
          <ReportPanel detail={detail} dimensions={data.dimensions} busy={busy} run={run} refresh={refreshProject} />}
        </main>}
      <footer className="page-footer"><span>SABC 项目评级</span><span>依据当前信息提供决策参考 · 实际准确性需历史案例验证</span></footer>
    </div>
  </div>;
}
