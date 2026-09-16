'use client';
import { useEffect, useRef, useState, type SetStateAction } from 'react';
import { Download, FileCheck2, RefreshCw, ArrowUpRight, ChevronDown } from 'lucide-react';
import { api, Detail, Dimension, Proposal, Score, Assumption, Assessment, Evidence, Lifecycle, gradeLabel } from '../lib/types';
import { ReportAssistant } from './report-assistant';
import { Field } from './workbench-forms';
import { deferralReason } from '../lib/deferral-reason';

const evidenceLabels: Record<string, string> = { E0: '尚待核验（E0）', E1: '间接依据（E1）', E2: '小规模验证（E2）', E3: '重复验证（E3）' };

const dimensionLabels: Record<string, string> = { strategy: '是否符合公司方向', market: '有没有需求', return: '投入能否带来回报', resources: '人手和能力是否够用', replication: '能否复用和积累成果', cash: '资金能否周转', risk: '风险能否控制', opportunity: '是否值得优先做' };

type Run = (action: () => Promise<void>, success?: string) => Promise<void>;
function initialProposal(dimensions: Dimension[]): Proposal {
  return { dimensions: Object.fromEntries(dimensions.map(d => [d.key, { score: null, reason: '', basis: 'assumption', evidence_ids: [] }])),
    assumptions: ['目标客户或使用者确实存在需求', '收入或业务价值可以兑现', '关键人员与资源可以获得', '交付过程和合规条件可行'].map((claim, i) => ({ id: 'P0-0' + (i + 1), claim, evidence_ids: [], validation_method: '', pass_threshold: '', fail_threshold: '' })),
    pros: [], cons: [], policy_caps: [], vetoes: [], s_conditions: { repeatable: false, resources_available: false, portfolio_feasible: false, review_complete: false } };
}

function ReferenceSelect({ ids, evidence, onChange }: { ids: string[]; evidence: Evidence[]; onChange: (ids: string[]) => void }) {
  return <select aria-label="参考资料" multiple value={ids} onChange={e => onChange(Array.from(e.target.selectedOptions).map(o => o.value))} size={Math.min(3, Math.max(1, evidence.length))}>{evidence.length ? evidence.map(e => <option key={e.id} value={e.id}>{e.title} · {evidenceLabels[`E${e.level}`] || `E${e.level}`}</option>) : <option disabled>暂无资料，可先标为待验证</option>}</select>;
}

function EvidenceReferences({ ids, evidence }: { ids: string[]; evidence: Evidence[] }) {
  if (!ids.length) return null;
  return <div className="report-references">{ids.map(id => {
    const item = evidence.find(e => e.id === id);
    if (!item) return <p className="source-location" key={id}>这份报告未保存所引用的资料，请核对。</p>;
    return <details key={id}><summary>{item.title}</summary><div className="evidence-content"><p className="source-location">来源：{item.source_locator || '未记录'}<br />资料对应时间：{item.data_period || '未记录'}<br />收集时间：{item.retrieved_at || '未记录'}<br />适用范围：{item.scope || '未记录'}<br />是否核实：{item.verification_status === 'verified' ? '已核验' : '未核验'} · 依据：{evidenceLabels[`E${item.level}`] || `E${item.level}`}<br />有效至：{item.valid_until || '未设定'}{item.conflict && ' · 与其他资料不一致，待核对'}</p><pre>{item.content || '未保存正文'}</pre></div></details>;
  })}</div>;
}

function PilotRecommendation({ life }: { life?: Lifecycle }) {
  const review = life?.review;
  const plan = life?.draft_plan || life?.plan;
  if (!review && !plan) return null;
  return <section className="report-section">
    <h3>行动建议</h3>
    {review && <><p>{review.summary}</p><h4>下一步建议</h4><p>{review.next_action}</p>{review.next_review_days && <p>建议 {review.next_review_days} 天后再评估。</p>}</>}
    {plan && <><h4>{life?.draft_plan ? '试点方案建议（待确认）' : `已确认试点方案 · 第 ${plan.version} 版`}</h4>
      <p><strong>想确认什么：</strong>{plan.objective}</p><p><strong>参与范围：</strong>{plan.scope}</p><p><strong>怎么试：</strong>{plan.method}</p>
      {plan.metrics.map((metric, i) => <div className="validation-item" key={i}><h4>{metric.name}</h4><p>现状：{metric.baseline}</p><p>目标：{metric.target}</p><p>怎么记录：{metric.measurement}</p></div>)}
      <p><strong>停止或调整条件：</strong>{plan.stop_conditions}</p>
      <p>负责人：{plan.owner} · 人员与资源：{plan.resources}</p>
      <p>现金预算上限：¥{plan.cash_budget.toLocaleString('zh-CN')} · 人工时间折合费用：¥{plan.internal_cost.toLocaleString('zh-CN')}</p>
      <p>最大可承受损失：¥{plan.max_loss.toLocaleString('zh-CN')} · 预计无法收回的损失：¥{plan.loss_estimate.toLocaleString('zh-CN')}</p>
      <p>计划周期：{plan.duration_days} 天 · 开始后 {plan.checkin_after_days} 天首次回访{plan.planned_start && ` · 预计开始：${plan.planned_start}`}</p>
      <p><strong>需要保留的记录：</strong>{plan.records}</p>
    </>}
  </section>;
}

function DecisionBrief({ brief }: { brief?: Record<string, string> }) {
  if (!brief || !Object.values(brief).some(Boolean)) return null;
  const labels: Record<string, string> = { definition: '项目做什么', goal_and_success: '目标与效果', key_unknown: '还不清楚什么', maximum_loss: '最多能承受多少损失', assets: '能留下什么成果', allocation: '需要多少人、钱和时间', upgrade_a: '评为 A 还差什么', upgrade_s: '评为 S 还差什么', stop: '什么时候停止' };
  return <section className="report-section"><h3>项目要点</h3>{Object.entries(labels).map(([key, label]) => brief[key] ? <p key={key}><strong>{label}：</strong>{brief[key]}</p> : null)}</section>;
}

export function ReportPanel({ detail, dimensions, busy, run, refresh, onGenerate, onRevise }: { detail: Detail; dimensions: Dimension[]; busy: boolean; run: Run; refresh: () => Promise<void>; onGenerate: () => void; onRevise: (reportId: string, turnId: string) => void }) {
  const [proposal, setProposalState] = useState<Proposal>(detail.project.proposal || initialProposal(dimensions));
  const draft = useRef({ projectId: detail.project.id, dirty: false });
  function setProposal(value: SetStateAction<Proposal>) { draft.current.dirty = true; setProposalState(value); }
  const reports = detail.assessments;
  const [selected, setSelected] = useState<Assessment | null>(reports[0] || null);
  const [confirmed, setConfirmed] = useState(false);
  const [edit, setEdit] = useState(false);
  const [exporting, setExporting] = useState(false);
  const reportRef = useRef<HTMLElement>(null);
  useEffect(() => { setConfirmed(false); }, [proposal]);
  useEffect(() => { setEdit(false); }, [detail.project.id]);
  useEffect(() => { setSelected(detail.assessments[0] || null); }, [detail.assessments]);
  useEffect(() => {
    if (draft.current.projectId !== detail.project.id) draft.current = { projectId: detail.project.id, dirty: false };
    if (!draft.current.dirty) setProposalState(detail.project.proposal || initialProposal(dimensions));
  }, [detail.project.id, detail.project.proposal, dimensions]);
  function setDimension(key: string, patch: Partial<Score>) { setConfirmed(false); setProposal(p => ({ ...p, dimensions: { ...p.dimensions, [key]: { ...p.dimensions[key], ...patch } } })); }
  function setAssumption(index: number, patch: Partial<Assumption>) { setConfirmed(false); setProposal(p => ({ ...p, assumptions: p.assumptions.map((a, i) => i === index ? { ...a, ...patch } : a) })); }
  async function evaluate(manual = false) {
    await run(async () => { const record = await api<Assessment>('/projects/' + detail.project.id + '/assess', 'POST', manual ? { proposal, confirmed } : {}); draft.current.dirty = false; setSelected(record); await refresh(); if (record.result.grade !== 'NR') setEdit(false); }, '本次评估已保存，历史结果不会被覆盖');
  }
  async function exportLongImage() {
    if (!selected || !reportRef.current || busy || exporting) return;
    const report = reportRef.current.cloneNode(true) as HTMLElement;
    const filename = `${selected.snapshot.project.name.slice(0, 60)}-项目评估报告-${selected.created_at}`;
    await run(async () => {
      setExporting(true);
      try {
        const { exportReportImage } = await import('../lib/report-image');
        await exportReportImage(report, filename);
      } finally {
        setExporting(false);
      }
    });
  }
  const r = selected?.result;
  const brief = selected?.snapshot.proposal.decision_brief;
  const objections = selected?.snapshot.proposal.strongest_objections || [];
  const mainRisk = objections.length === 1 ? objections[0] : brief?.biggest_risk;
  const pendingFacts = Object.entries(detail.project.pending_patch || {}).some(([key, value]) => detail.project[key] !== value);
  return <section className="report-area"><div className="section-heading"><div><h2>项目评估报告</h2><p>从八个方面判断项目是否值得做，保留每次访谈与报告。</p></div><div className="button-group">{selected && <button className="secondary" disabled={busy || exporting} aria-busy={exporting} onClick={exportLongImage}><Download size={15} />{exporting ? '正在导出…' : '导出长图'}</button>}<button className="primary" disabled={busy} onClick={onGenerate}><RefreshCw size={15} />重新评估</button></div></div>
    {pendingFacts && <p className="review-note" role="status">报告将使用本轮整理的项目资料；如需更正，可返回访谈补充或在项目资料中修改。</p>}
    {reports.length > 0 && <label className="history-select">历史报告版本<select disabled={exporting} value={selected?.id || ''} onChange={e => setSelected(reports.find(a => a.id === e.target.value) || null)}>{reports.map((a, i) => <option key={a.id} value={a.id}>{new Date(a.created_at).toLocaleString('zh-CN')} · {gradeLabel(a.result.grade)}{i === 0 ? ' · 本次最新' : ''}</option>)}</select></label>}
    {!r ? <div className="report-empty"><FileCheck2 size={35} /><h3>报告尚未生成</h3><p>第一阶段问答完成后，系统自动整理并审查报告；审查完成后在这里展示最终报告。</p><PilotRecommendation life={detail.project.lifecycle} /></div> : <article className="rating-document" ref={reportRef}>
      <div className="rating-summary"><div className={'final-grade grade-' + r.grade}>{gradeLabel(r.grade)}</div><div className="rating-summary-text"><h2>{r.grade === 'NR' ? '项目分析记录 · 暂缓评级' : r.action}</h2>{r.grade === 'NR' && <p className="deferral-reason">{deferralReason(r, selected!.snapshot.project.lifecycle)}</p>}<p>结论把握程度：{r.confidence} · 资料依据：{r.evidence_evaluated || r.base_score !== null ? evidenceLabels[r.evidence_level] || r.evidence_level : '本版未记录'}</p><span>评估于 {new Date(selected!.created_at).toLocaleString('zh-CN')}</span></div><div className="rating-score"><strong>{r.base_score === null ? '暂不计算' : r.base_score}{r.base_score !== null && <span>/100</span>}</strong><small>{r.base_score === null ? '资料不足，暂不打分' : '项目总分'}</small></div></div>
      {r.revision && <section className="report-section"><h3>本次修订</h3><p>已保存新版本，原报告仍可在历史版本中查看。</p><p>{r.revision.changes.length ? '调整内容：' + r.revision.changes.join('、') : '复核后未发现需要调整的分数或关键判断。'}</p></section>}
      <section className="report-section"><h3>项目基本信息</h3><p><strong>项目名称：</strong>{selected!.snapshot.project.name}</p><p><strong>本次评估范围：</strong>{selected!.snapshot.proposal.assessment_scope?.subject || selected!.snapshot.proposal.decision_brief?.definition || selected!.snapshot.project.name}</p><p><strong>资料对应时间：</strong>{String(selected!.snapshot.project.data_period || '见各项来源期间')}</p><p><strong>计划试多久：</strong>{String(selected!.snapshot.project.timeframe || '未知，待确认')}</p></section>
      <section className="report-section">
        <h3>这些资料能说明什么</h3>
        <p>这表示关键条件验证到了哪一步，不代表项目好坏。整份报告以关键条件中验证最少的一项为准，资料多不等于验证充分。</p>
        <ul>
          <li><strong>尚待核验（E0）：</strong>关键判断还缺少核实过的支持，不代表没有资料或没做过测试。</li>
          <li><strong>间接依据（E1）：</strong>有外部资料或类似案例可参考，还不能证明本项目的效果。</li>
          <li><strong>小规模验证（E2）：</strong>有核实过的试点或可直接参考的结果，结论仅适用于已测试的范围。</li>
          <li><strong>重复验证（E3）：</strong>关键条件已经多次验证，可以来自同一项目的不同周期或样本。</li>
        </ul>
        <p>前两种情况最高可评 B，小规模验证后最高可评 A，重复验证后才可能评 S。最终还要看评分、资源和风险；资料不足时暂不评级，达到证据要求也不会自动升级。</p>
      </section>
      <section className="report-section"><div className="section-heading"><h3>八个方面的判断</h3><span className="footnote">项目好不好、依据足不足，分别看</span></div><div className="dimension-results">{dimensions.map(meta => {
        const stored = r.dimensions.find(item => item.key === meta.key);
        const d = stored || { ...meta, score: null, weighted: null, basis: 'unknown', evidence_ids: [], reason: selected!.snapshot.proposal.dimensions[meta.key]?.reason || '本版未形成该维判断', missing_evidence: selected!.snapshot.proposal.dimensions[meta.key]?.missing_evidence };
        return <div className="dimension-result" key={d.key}><div><strong>{dimensionLabels[d.key] || d.name}</strong><span>{d.score === null ? `暂无法判断 · 占总分 ${d.weight}%` : `${d.weighted} / ${d.weight}（单项评分 ${d.score} / 5）`}</span></div>{d.score !== null && <div className="score-track"><span style={{ width: `${d.score / 5 * 100}%` }} /></div>}<p><strong>{d.basis === 'fact' ? '已有资料支持' : d.basis === 'unknown' ? '暂无法判断' : '根据现有信息推测'}：</strong>{d.reason}</p><p><strong>还需确认：</strong>{d.missing_evidence || '本版未单独记录，请结合资料中的限制查看'}</p>{Boolean(selected!.snapshot.proposal.dimensions[meta.key]?.support?.length) && <details className="report-references"><summary>查看评分依据</summary>{selected!.snapshot.proposal.dimensions[meta.key].support!.map((claim, index) => <div className="validation-item" key={index}><p>{claim.quote}</p><p className="source-location">{claim.use === 'background' ? '背景资料，不用于支持分数' : '评分依据'} · {claim.subject} · {claim.metric} · {claim.period} · {claim.unit}</p></div>)}</details>}<EvidenceReferences ids={d.evidence_ids} evidence={selected!.snapshot.evidence} /></div>;
      })}</div><h4>资料情况</h4><p>保存资料 {r.evidence_count ?? selected!.snapshot.evidence.length} 条 · 去重后的来源 {r.evidence_evaluated ? r.unique_sources : '未完整核算'} 个 · 发布方 {r.publisher_count ?? '尚未核对'}。资料数量不代表独立验证次数。</p>{r.warnings.length > 0 && <ul>{r.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}{r.assumptions.length > 0 && <><h4>需要确认的条件</h4><p>以下是项目成立的前提，是否已验证请看每项标签。</p>{r.assumptions.map(a => <div className="assumption-result" key={a.id}><span className="evidence-level">{evidenceLabels[a.level || ''] || a.level}</span><div><strong>{a.claim}</strong><EvidenceReferences ids={a.evidence_ids} evidence={selected!.snapshot.evidence} /></div></div>)}</>}</section>
      <section className="report-section argument-columns"><div><h3>项目优势</h3><ol>{r.pros.map((p, i) => <li key={i}>{p}</li>)}</ol></div><div><h3>项目劣势</h3><ol>{r.cons.map((p, i) => <li key={i}>{p}</li>)}</ol></div></section>
      <section className="report-section"><h3>最大隐患</h3><p>{mainRisk || '本版未单独归纳，请结合项目劣势查看。'}</p></section>
      <DecisionBrief brief={{ ...selected!.snapshot.proposal?.decision_brief, ...r.upgrade_requirements }} />
      <PilotRecommendation life={selected!.snapshot.project.lifecycle} />
      <section className="report-section"><h3>试点与停止条件</h3>{r.missing.length > 0 && <><h4>先补齐哪些信息</h4><ul className="missing-list">{r.missing.map((m, i) => <li key={i}><span />{m}</li>)}</ul></>}{r.grade === 'NR' && <p>先补齐以下资料，再决定是否投入。</p>}{r.resource_plan.note && <p>{r.grade === 'B' ? '先算清小规模试点需要多少钱，再由负责人批准。' : r.resource_plan.note}</p>}{r.resource_plan.available_limit != null && <p>公司可用资金上限：¥{r.resource_plan.available_limit.toLocaleString('zh-CN')}。这是可用额度，具体投入还需单独确认。</p>}{r.validation_plan.map((v, i) => <div className="validation-item" key={i}><h4>{v.claim}</h4><p>怎么试：{v.method}</p><p>怎样算有效：{v.pass}</p><p>何时停止或调整：{v.fail}</p></div>)}<h4>什么时候再评估</h4><ul>{r.reassessment_triggers.map((t, i) => <li key={i}>{t}</li>)}</ul></section>
      <div className="report-meta">规则版本 {r.rule_version} · 本次资料已留存 · 结论把握程度不等于成功概率</div>
    </article>}
    <div className="manual-review-heading"><div><h3>{detail.project.proposal ? '核对当前评分建议' : '需要人工评审？'}</h3><p>{detail.project.proposal ? '逐项检查依据，确认后由系统计算等级。' : '可由评审人员填写各项判断与待验证条件。系统不会将人工填写伪装成模型分析。'}</p></div><button className="secondary" onClick={() => { setEdit(!edit); }}>{edit ? '收起评审表' : '打开评审表'}<ChevronDown size={16} /></button></div>
    {edit && <form className="form-document manual-review" onSubmit={e => { e.preventDefault(); evaluate(true); }}><section className="form-section"><h3>八个方面的判断</h3><p className="section-description">无法判断时留空；低于3分需说明已确认的不利事实，不能只因缺资料扣分。</p>{dimensions.map(d => { const v = proposal.dimensions[d.key] || { score: null, reason: '', basis: 'unknown', evidence_ids: [] }; return <fieldset className="score-editor" key={d.key}><legend>{dimensionLabels[d.key] || d.name}<span>占总分 {d.weight}%</span></legend><div className="score-inputs"><Field label="单项评分"><select value={v.score ?? ''} onChange={e => setDimension(d.key, { score: e.target.value === '' ? null : Number(e.target.value) })}><option value="">未知 / 无法判断</option>{Array.from({ length: 11 }, (_, i) => i / 2).map(n => <option key={n} value={n}>{n} / 5</option>)}</select></Field><Field label="判断依据"><select value={v.basis} onChange={e => setDimension(d.key, { basis: e.target.value })}><option value="assumption">根据现有信息推测</option><option value="fact">已知事实</option><option value="unknown">未知</option></select></Field><Field label="参考资料"><ReferenceSelect evidence={detail.evidence} ids={v.evidence_ids} onChange={evidence_ids => setDimension(d.key, { evidence_ids })} /></Field></div><Field label="具体依据"><textarea rows={2} value={v.reason} onChange={e => setDimension(d.key, { reason: e.target.value })} placeholder="说明为什么给这个分数，区分事实、推断和未知。" /></Field></fieldset>; })}</section>
      <section className="form-section"><div className="section-heading"><h3>项目成立需要哪些条件</h3><button type="button" className="secondary" onClick={() => setProposal(p => ({ ...p, assumptions: [...p.assumptions, { id: "P0-" + crypto.randomUUID().slice(0, 8), claim: "", evidence_ids: [], validation_method: "", pass_threshold: "", fail_threshold: "" }] }))}>添加条件</button></div>{proposal.assumptions.map((a, i) => <fieldset className="assumption-editor" key={a.id}><legend>条件 {i + 1}</legend><button type="button" className="secondary" disabled={proposal.assumptions.length <= 1} onClick={() => setProposal(p => ({ ...p, assumptions: p.assumptions.filter((_, index) => index !== i) }))}>移除此条件</button><Field label="需要确认什么"><input value={a.claim} onChange={e => setAssumption(i, { claim: e.target.value })} /></Field><Field label="支持这个条件的资料"><ReferenceSelect ids={a.evidence_ids} evidence={detail.evidence} onChange={ids => setAssumption(i, { evidence_ids: ids })} /></Field><div className="form-grid"><Field label="怎么验证"><input value={a.validation_method || ''} onChange={e => setAssumption(i, { validation_method: e.target.value })} /></Field><Field label="怎样算有效"><input value={a.pass_threshold || ''} onChange={e => setAssumption(i, { pass_threshold: e.target.value })} /></Field><Field label="何时停止或调整"><input value={a.fail_threshold || ''} onChange={e => setAssumption(i, { fail_threshold: e.target.value })} /></Field></div></fieldset>)}</section>
      <section className="form-section"><div className="section-heading"><h3>必须停止的情况</h3><button type="button" className="secondary" onClick={() => setProposal(p => ({ ...p, vetoes: [...p.vetoes, { reason: '', confirmed: false, evidence_ids: [] }] }))}>添加停止原因</button></div><p className="section-description">只有已经核实、确实让方案无法继续的问题，才会直接评为 C；还没确认的风险会限制可评等级。</p>{proposal.vetoes.length === 0 && <p>目前没有确认必须停止的问题。</p>}{proposal.vetoes.map((v, i) => <fieldset className="assumption-editor" key={i}><legend>停止原因 {i + 1}</legend><Field label="为什么必须停止"><textarea required rows={2} value={v.reason} onChange={e => setProposal(p => ({ ...p, vetoes: p.vetoes.map((item, index) => index === i ? { ...item, reason: e.target.value } : item) }))} /></Field><Field label="支持这一判断的资料"><ReferenceSelect ids={v.evidence_ids} evidence={detail.evidence} onChange={evidence_ids => setProposal(p => ({ ...p, vetoes: p.vetoes.map((item, index) => index === i ? { ...item, evidence_ids } : item) }))} /></Field><label className="checkbox"><input type="checkbox" checked={v.confirmed} onChange={e => setProposal(p => ({ ...p, vetoes: p.vetoes.map((item, index) => index === i ? { ...item, confirmed: e.target.checked } : item) }))} />已核实这一问题，且当前方案无法解决</label><button type="button" className="secondary" onClick={() => setProposal(p => ({ ...p, vetoes: p.vetoes.filter((_, index) => index !== i) }))}>移除此原因</button></fieldset>)}</section>
      <section className="form-section"><h3>项目优劣与评级条件</h3><div className="form-grid"><Field label="项目优势，每行一条，至少3条"><textarea rows={4} value={proposal.pros.join('\n')} onChange={e => setProposal(p => ({ ...p, pros: e.target.value.split('\n') }))} /></Field><Field label="项目劣势，每行一条，至少3条"><textarea rows={4} value={proposal.cons.join('\n')} onChange={e => setProposal(p => ({ ...p, cons: e.target.value.split('\n') }))} /></Field></div><Field label="只能小规模试点的原因，每行一条" hint="如核心价值从未真实验证、老板是唯一关键人、重资产投入后才能测试。没有已知触发项时留空。"><textarea rows={3} value={proposal.policy_caps.join('\n')} onChange={e => setProposal(p => ({ ...p, policy_caps: e.target.value ? e.target.value.split('\n') : [] }))} /></Field><h4>评为 S 还需满足</h4>{[['repeatable', '已经多次验证，且能交给其他人复用'], ['resources_available', '公司确实能够投入所需核心资源'], ['portfolio_feasible', '与其他项目相比值得优先投入，且不挤占主业所需资源'], ['review_complete', '已核对主要风险与反对理由并反映到以上判断']].map(([key, label]) => <label className="checkbox" key={key}><input type="checkbox" checked={proposal.s_conditions[key] === true} onChange={e => setProposal(p => ({ ...p, s_conditions: { ...p.s_conditions, [key]: e.target.checked } }))} />{label}</label>)}<div className="review-confirm"><label className="checkbox"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} required />我已核对以上事实、证据与判断，确认用于本次评级</label><button className="primary" disabled={busy || !confirmed || pendingFacts} type="submit">确认并计算评级<ArrowUpRight size={16} /></button></div></section>
    </form>}
    {selected && <ReportAssistant key={selected.id} projectId={detail.project.id} report={selected} disabled={busy} onRevise={onRevise} />}
  </section>;
}
