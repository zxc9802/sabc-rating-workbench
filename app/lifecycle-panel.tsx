'use client';
import { useEffect, useState } from 'react';
import { api, Detail, PilotPlan, Stage, Lifecycle, Dimension } from '../lib/types';

const stages: Record<Stage, string> = { pre: '启动前', during: '试点中', post: '试点后' };
const conclusions: Record<string, string> = { trial: '值得小范围试点', adjust: '调整后再继续', not_recommended: '当前方案不适合做', needs_info: '仍需补充关键依据', continue: '建议继续', pause: '建议暂停', finish: '建议结束试点并复盘' };
const statuses: Record<string, string> = { known: '已有判断依据', ask: '待补充', unknown: '暂不清楚', external: '需要核查', future: '等待实际验证' };
function localDate() { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()); }
function afterDays(days: number) { const date = new Date(localDate() + 'T00:00:00+08:00'); date.setUTCDate(date.getUTCDate() + days); return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(date); }

type Props = { detail: Detail; dimensions: Dimension[]; busy: boolean; refresh: () => Promise<void>; run: (fn: () => Promise<void>, success?: string) => Promise<void>; full?: boolean; onFollowup?: (message: string) => void };

export function LifecyclePanel({ detail, dimensions, busy, refresh, run, full, onFollowup }: Props) {
  const life: Lifecycle = detail.project.lifecycle || { stage: 'pre', confirmed: false, paused: false, coverage: {}, reviews: [], plan_history: [], events: [] };
  const [stage, setStage] = useState<Stage>(life.stage);
  const [started, setStarted] = useState(life.actual_start || localDate());
  const [ended, setEnded] = useState(localDate());
  const [reason, setReason] = useState('');
  const [scheduled, setScheduled] = useState(life.next_review_on || localDate());
  const [plan, setPlan] = useState<PilotPlan | null>(life.draft_plan || life.plan || null);
  useEffect(() => { setStage(life.stage); setPlan(life.draft_plan || life.plan || null); setScheduled(life.next_review_on || localDate()); }, [detail.project.version]); // Refresh preserves server-confirmed dates and versions.
  async function act(action: string, payload: object) {
    await run(async () => { await api('/projects/' + detail.project.id + '/lifecycle', 'POST', { action, payload, version: detail.project.version }); await refresh(); }, '项目阶段记录已保存');
  }
  const rawDue = detail.project.followup;
  const due = rawDue ? { ...rawDue, due: rawDue.date <= localDate() } : null;
  const review = life.review;
  if (!full) return <section className="stage-strip" aria-label="项目阶段">
    <div className="stage-steps">{Object.entries(stages).map(([key, label], i) => <span key={key} className={life.confirmed && life.stage === key ? 'current' : ''}>{i + 1}. {label}</span>)}</div>
    {!life.confirmed ? <p>请在“阶段评价与方案”中确认项目实际阶段，历史周期不会自动视为已完成。</p> : <p>{life.paused ? '已暂停回访' : due ? `${due.due ? '已到回访时间' : '下次回访'}：${due.date}` : '根据实际进度安排下一次回访'}{life.actual_start && ` · 实际开始 ${life.actual_start}`}{life.expected_end && life.stage === 'during' && ` · 预计结束 ${life.expected_end}`}</p>}
    {life.confirmed && !life.paused && onFollowup && <button className="secondary" disabled={busy} onClick={() => onFollowup(life.stage === 'pre' ? '请结合当前项目阶段和已有资料继续启动前评价，并核对是否已经实际启动；不要假设已有试点结果。' : life.stage === 'during' ? '开始本次试点回访。请先结合已确认方案和我已上传的记录分析，再问实际执行进度和最关键的差异；不要假定试点已经完成。' : '请开始试点后复盘。先总结已有记录、对照原方案，再补问综合评分所需的关键缺口。')}>{due?.due ? '开始本次回访' : '继续阶段访谈'}</button>}
  </section>;

  return <section className="stage-panel">
    <h2>{stages[life.stage]}评价与方案</h2>
    {review ? <article className="stage-review"><h3>{conclusions[review.conclusion]}</h3><p>{review.summary}</p><p>{review.next_action}</p><small>基于当前资料的阶段判断 · {new Date(review.time).toLocaleString('zh-CN')}</small></article> : <p>通过多轮访谈形成当前阶段评价。启动前不会要求尚未发生的试点结果。</p>}
    <div className="stage-dimensions">{dimensions.map(d => { const item = life.coverage[d.key]; return <div key={d.key}><strong>{d.name}</strong><span>{item ? statuses[item.status] : '尚未梳理'}</span><p>{item?.reason || '已有资料将先用于分析，只追问影响当前决策的缺口。'}</p></div>; })}</div>
    <details className="stage-controls" open={!life.confirmed}><summary>{life.confirmed ? '核对或更正实际阶段' : '确认实际项目阶段'}</summary><div className="stage-fields">
      <label>当前阶段<select value={stage} onChange={e => setStage(e.target.value as Stage)}>{Object.entries(stages).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      {stage !== 'pre' && <label>实际开始日期<input type="date" value={started} max={localDate()} onChange={e => setStarted(e.target.value)} /></label>}
      {stage === 'post' && <label>实际结束日期<input type="date" value={ended} min={started} max={localDate()} onChange={e => setEnded(e.target.value)} /></label>}
      <label>更正说明<input value={reason} onChange={e => setReason(e.target.value)} placeholder="已有记录与实际情况不符时说明原因" /></label>
    </div><button className="secondary" disabled={busy} onClick={() => act('set_stage', { stage, actual_start: started, actual_end: ended, reason })}>确认实际阶段</button></details>
    {plan && life.stage !== 'post' && <details className="pilot-editor" open={!!life.draft_plan}><summary>{life.draft_plan ? '核对试点方案草稿' : `已确认试点方案 · 第 ${life.plan?.version} 版`}</summary><p>修改后确认保存为新版本；保存方案不会自动启动试点。原目标和修改原因会保留。</p>
      <div className="stage-fields">{([['objective', '要验证的问题'], ['scope', '参与范围'], ['method', '验证方法'], ['stop_conditions', '成功之外的停止／调整条件'], ['owner', '负责人'], ['resources', '人员与资源安排'], ['records', '需要记录的资料']] as const).map(([key, label]) => <label key={key}>{label}<textarea value={plan[key]} onChange={e => setPlan({ ...plan, [key]: e.target.value })} /></label>)}</div>
      {plan.metrics.map((metric, i) => <fieldset key={i}><legend>指标 {i + 1}</legend><div className="stage-fields">{([['name', '指标'], ['baseline', '现状基线或补测方法'], ['target', '通过目标'], ['measurement', '测量方法与统计范围']] as const).map(([key, label]) => <label key={key}>{label}<input value={metric[key]} onChange={e => setPlan({ ...plan, metrics: plan.metrics.map((m, j) => j === i ? { ...m, [key]: e.target.value } : m) })} /></label>)}</div></fieldset>)}
      <div className="stage-fields">{([['cash_budget', '现金预算上限（元）'], ['internal_cost', '内部工时折算（元）'], ['max_loss', '最大可承受损失（元）'], ['loss_estimate', '估计不可收回的损失（元）'], ['duration_days', '计划试点天数'], ['checkin_after_days', '开始后多少天首次回访']] as const).map(([key, label]) => <label key={key}>{label}<input type="number" min={key.endsWith('days') ? 1 : 0} value={plan[key]} onChange={e => setPlan({ ...plan, [key]: Number(e.target.value) })} /></label>)}<label>预计开始日期<input type="date" value={plan.planned_start || ''} onChange={e => setPlan({ ...plan, planned_start: e.target.value || null })} /></label><label>本次调整原因<input value={reason} onChange={e => setReason(e.target.value)} placeholder={life.plan ? '修改已确认方案时必填' : '首次确认可留空'} /></label></div>
      <button className="primary" disabled={busy} onClick={() => { const { version, confirmed_at, change_reason, ...draft } = plan; void version; void confirmed_at; void change_reason; return act('confirm_plan', { plan: draft, reason }); }}>确认并保存试点方案</button>
    </details>}
    {life.confirmed && <div className="stage-controls"><h3>实际进度与回访安排</h3>
      {life.stage === 'pre' && life.plan && <div className="stage-action"><label>实际开始日期<input type="date" value={started} max={localDate()} onChange={e => setStarted(e.target.value)} /></label><button className="primary" disabled={busy} onClick={() => act('start', { date: started })}>确认已开始试点</button></div>}
      {life.stage === 'during' && <div className="stage-action"><label>实际结束日期<input type="date" value={ended} min={life.actual_start || undefined} max={localDate()} onChange={e => setEnded(e.target.value)} /></label><label>结束情况<input value={reason} onChange={e => setReason(e.target.value)} placeholder="正常完成或提前停止，以及原因" /></label><button className="primary" disabled={busy || !reason.trim()} onClick={() => act('complete', { date: ended, reason })}>确认结束，进入复盘</button></div>}
      <div className="stage-action"><label>下次回访日期<input type="date" min={localDate()} value={scheduled} onChange={e => setScheduled(e.target.value)} /></label><label>安排原因<input value={reason} onChange={e => setReason(e.target.value)} placeholder="延期、补充记录或阶段检查" /></label><button className="secondary" disabled={busy || !reason.trim()} onClick={() => act('schedule', { date: scheduled, reason })}>保存回访日期</button>{review?.next_review_days && <button className="secondary" disabled={busy} onClick={() => act('schedule', { date: afterDays(review.next_review_days!), reason: `采用本次评价建议：${review.next_review_days}天后回访` })}>采用建议：{review.next_review_days}天后回访</button>}<button className="secondary" disabled={busy || !reason.trim()} onClick={() => act(life.paused ? 'resume' : 'pause', { reason })}>{life.paused ? '恢复回访' : '暂停回访'}</button></div>
      <p>到期会在项目列表和访谈页提示。日期不会自动证明试点已开始或结束，可提前回访。</p>
    </div>}
    {!!life.plan_history.length && <details><summary>历史方案（{life.plan_history.length}）</summary>{life.plan_history.map(p => <article className="stage-history" key={p.version}><strong>第 {p.version} 版 · {p.objective}</strong><p>{p.change_reason || '首次确认'} · {p.confirmed_at}</p><p>{p.method}</p>{p.metrics.map((m, i) => <p key={i}>{m.name}：{m.baseline} → {m.target}；{m.measurement}</p>)}<p>现金预算 {p.cash_budget} 元 · 损失上限 {p.max_loss} 元 · 周期 {p.duration_days} 天</p></article>)}</details>}
    {life.reviews.length > 1 && <details><summary>历史阶段评价（{life.reviews.length}）</summary>{life.reviews.slice().reverse().map((r, i) => <article className="stage-history" key={i}><strong>{stages[r.stage]} · {conclusions[r.conclusion]}</strong><p>{r.summary}</p><p>{r.next_action}</p><small>{r.time}</small></article>)}</details>}
  </section>;
}
