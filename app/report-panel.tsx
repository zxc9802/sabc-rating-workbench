'use client';
import { useEffect, useRef, useState, type SetStateAction } from 'react';
import { Download, FileCheck2, RefreshCw, ArrowUpRight, ChevronDown, Printer } from 'lucide-react';
import { api, Detail, Dimension, Proposal, Score, Assumption, Assessment, Evidence, Lifecycle, gradeLabel } from '../lib/types';
import { ReportAssistant } from './report-assistant';
import { Field } from './workbench-forms';
import { deferralReason } from '../lib/deferral-reason';

type Run = (action: () => Promise<void>, success?: string) => Promise<void>;
function initialProposal(dimensions: Dimension[]): Proposal {
  return { dimensions: Object.fromEntries(dimensions.map(d => [d.key, { score: null, reason: '', basis: 'assumption', evidence_ids: [] }])),
    assumptions: ['目标客户或使用者确实存在需求', '收入或业务价值可以兑现', '关键人员与资源可以获得', '交付过程和合规条件可行'].map((claim, i) => ({ id: 'P0-0' + (i + 1), claim, evidence_ids: [], validation_method: '', pass_threshold: '', fail_threshold: '' })),
    pros: [], cons: [], policy_caps: [], vetoes: [], s_conditions: { repeatable: false, resources_available: false, portfolio_feasible: false, review_complete: false } };
}

function ReferenceSelect({ ids, evidence, onChange }: { ids: string[]; evidence: Evidence[]; onChange: (ids: string[]) => void }) {
  return <select aria-label="关联证据" multiple value={ids} onChange={e => onChange(Array.from(e.target.selectedOptions).map(o => o.value))} size={Math.min(3, Math.max(1, evidence.length))}>{evidence.length ? evidence.map(e => <option key={e.id} value={e.id}>{e.title} · E{e.level}</option>) : <option disabled>暂无证据，可先保留为假设</option>}</select>;
}

function EvidenceReferences({ ids, evidence }: { ids: string[]; evidence: Evidence[] }) {
  if (!ids.length) return null;
  return <div className="report-references">{ids.map(id => {
    const item = evidence.find(e => e.id === id);
    if (!item) return <p className="source-location" key={id}>引用的资料未包含在本次快照中，请复核引用。</p>;
    return <details key={id}><summary>{item.title}</summary><div className="evidence-content"><p className="source-location">来源：{item.source_locator || '未记录'}<br />数据期间：{item.data_period || '未记录'}<br />采集时间：{item.retrieved_at || '未记录'}<br />适用范围 / 口径：{item.scope || '未记录'}<br />核验状态：{item.verification_status === 'verified' ? '已核验' : '未核验'} · 登记等级：E{item.level}<br />有效至：{item.valid_until || '未设定'}{item.conflict && ' · 存在待解释冲突'}</p><pre>{item.content || '未保存正文'}</pre></div></details>;
  })}</div>;
}

function PilotRecommendation({ life }: { life?: Lifecycle }) {
  const review = life?.review;
  const plan = life?.draft_plan || life?.plan;
  if (!review && !plan) return null;
  return <section className="report-section">
    <h3>行动建议</h3>
    {review && <><p>{review.summary}</p><h4>下一步建议</h4><p>{review.next_action}</p>{review.next_review_days && <p>建议 {review.next_review_days} 天后回访复评。</p>}</>}
    {plan && <><h4>{life?.draft_plan ? '试点方案建议（待确认）' : `已确认试点方案 · 第 ${plan.version} 版`}</h4>
      <p><strong>验证目标：</strong>{plan.objective}</p><p><strong>参与范围：</strong>{plan.scope}</p><p><strong>验证方法：</strong>{plan.method}</p>
      {plan.metrics.map((metric, i) => <div className="validation-item" key={i}><h4>{metric.name}</h4><p>现状：{metric.baseline}</p><p>目标：{metric.target}</p><p>测量：{metric.measurement}</p></div>)}
      <p><strong>停止或调整条件：</strong>{plan.stop_conditions}</p>
      <p>负责人：{plan.owner} · 人员与资源：{plan.resources}</p>
      <p>现金预算上限：¥{plan.cash_budget.toLocaleString('zh-CN')} · 内部工时折算：¥{plan.internal_cost.toLocaleString('zh-CN')}</p>
      <p>最大可承受损失：¥{plan.max_loss.toLocaleString('zh-CN')} · 估计不可回收损失：¥{plan.loss_estimate.toLocaleString('zh-CN')}</p>
      <p>计划周期：{plan.duration_days} 天 · 开始后 {plan.checkin_after_days} 天首次回访{plan.planned_start && ` · 预计开始：${plan.planned_start}`}</p>
      <p><strong>需要保留的记录：</strong>{plan.records}</p>
    </>}
  </section>;
}

function DecisionBrief({ brief }: { brief?: Record<string, string> }) {
  if (!brief || !Object.values(brief).some(Boolean)) return null;
  const labels: Record<string, string> = { definition: '项目定义', goal_and_success: '经营目标与成功标准', biggest_risk: '最大单一风险', key_unknown: '关键未知与最缺证据', maximum_loss: '最大损失与承受上限', assets: '可沉淀资产', allocation: '人员、预算与周期建议', upgrade_a: '升级 A 还需要什么', upgrade_s: '升级 S 还需要什么', stop: '降级、停止与止损条件' };
  return <section className="report-section"><h3>关键判断与资源安排</h3>{Object.entries(labels).map(([key, label]) => brief[key] ? <p key={key}><strong>{label}：</strong>{brief[key]}</p> : null)}</section>;
}

export function ReportPanel({ detail, dimensions, busy, run, refresh, onGenerate, onRevise }: { detail: Detail; dimensions: Dimension[]; busy: boolean; run: Run; refresh: () => Promise<void>; onGenerate: () => void; onRevise: (reportId: string, turnId: string) => void }) {
  const [proposal, setProposalState] = useState<Proposal>(detail.project.proposal || initialProposal(dimensions));
  const draft = useRef({ projectId: detail.project.id, dirty: false });
  function setProposal(value: SetStateAction<Proposal>) { draft.current.dirty = true; setProposalState(value); }
  const reports = detail.assessments;
  const [selected, setSelected] = useState<Assessment | null>(reports[0] || null);
  const [confirmed, setConfirmed] = useState(false);
  const [edit, setEdit] = useState(false);
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
  const r = selected?.result;
  const pendingFacts = Object.entries(detail.project.pending_patch || {}).some(([key, value]) => detail.project[key] !== value);
  return <section className="report-area"><div className="section-heading"><div><h2>项目评估报告</h2><p>结合项目现状进行八维评估，历次访谈与报告持续保存。</p></div><div className="button-group">{selected && <><button className="secondary" onClick={() => window.print()}><Printer size={15} />打印</button><a className="secondary" href={'/api/assessments/' + selected.id + '/export'}><Download size={15} />导出快照</a></>}<button className="primary" disabled={busy} onClick={onGenerate}><RefreshCw size={15} />重新评估</button></div></div>
    {pendingFacts && <p className="review-note" role="status">报告将使用本轮整理的项目资料；如需更正，可返回访谈补充或在项目资料中修改。</p>}
    {reports.length > 0 && <label className="history-select">历史报告版本<select value={selected?.id || ''} onChange={e => setSelected(reports.find(a => a.id === e.target.value) || null)}>{reports.map((a, i) => <option key={a.id} value={a.id}>{new Date(a.created_at).toLocaleString('zh-CN')} · {gradeLabel(a.result.grade)}{i === 0 ? ' · 本次最新' : ''}</option>)}</select></label>}
    {!r ? <div className="report-empty"><FileCheck2 size={35} /><h3>报告尚未生成</h3><p>第一阶段问答完成后，系统自动整理并审查报告；审查完成后在这里展示最终报告。</p><PilotRecommendation life={detail.project.lifecycle} /></div> : <article className="rating-document">
      <div className="rating-summary"><div className={'final-grade grade-' + r.grade}>{gradeLabel(r.grade)}</div><div className="rating-summary-text"><h2>{r.grade === 'NR' ? '项目分析记录 · 暂缓评级' : r.action}</h2>{r.grade === 'NR' && <p className="deferral-reason">{deferralReason(r, selected!.snapshot.project.lifecycle)}</p>}<p>判断置信度：{r.confidence} · 证据：{r.evidence_evaluated || r.base_score !== null ? r.evidence_level : '本版未记录完整核算状态'}</p><span>评估于 {new Date(selected!.created_at).toLocaleString('zh-CN')}</span></div><div className="rating-score"><strong>{r.base_score === null ? '暂不计算' : r.base_score}{r.base_score !== null && <span>/100</span>}</strong><small>{r.base_score === null ? '关键依据不足，未知分数不按零分计算' : '八维业务分'}</small></div></div>
      {r.revision && <section className="report-section"><h3>本次修订</h3><p>已保存新版本，原报告仍可在历史版本中查看。</p><p>{r.revision.changes.length ? '调整内容：' + r.revision.changes.join('、') : '复核后未发现需要调整的分数或关键判断。'}</p></section>}
      <section className="report-section"><h3>项目基本信息</h3><p><strong>项目名称：</strong>{selected!.snapshot.project.name}</p><p><strong>评估对象：</strong>{selected!.snapshot.proposal.assessment_scope?.subject || selected!.snapshot.proposal.decision_brief?.definition || selected!.snapshot.project.name}</p><p><strong>历史资料期间：</strong>{String(selected!.snapshot.project.data_period || '见各项来源期间')}</p><p><strong>未来验证周期：</strong>{String(selected!.snapshot.project.timeframe || '未知，待确认')}</p></section>
      <section className="report-section"><div className="section-heading"><h3>八维业务判断</h3><span className="footnote">业务质量与证据强度分开计算</span></div><div className="dimension-results">{dimensions.map(meta => {
        const stored = r.dimensions.find(item => item.key === meta.key);
        const d = stored || { ...meta, score: null, weighted: null, basis: 'unknown', evidence_ids: [], reason: selected!.snapshot.proposal.dimensions[meta.key]?.reason || '本版未形成该维判断', missing_evidence: selected!.snapshot.proposal.dimensions[meta.key]?.missing_evidence };
        return <div className="dimension-result" key={d.key}><div><strong>{d.name}</strong><span>{d.score === null ? `未知 · 权重 ${d.weight}%` : `${d.weighted} / ${d.weight}（原始分 ${d.score} / 5）`}</span></div>{d.score !== null && <div className="score-track"><span style={{ width: `${d.score / 5 * 100}%` }} /></div>}<p><strong>{d.basis === 'fact' ? '来源支持的判断' : d.basis === 'unknown' ? '未知' : '假设 / 推断'}：</strong>{d.reason}</p><p><strong>缺失依据：</strong>{d.missing_evidence || '本版未单独记录，请结合来源局限核对'}</p>{Boolean(selected!.snapshot.proposal.dimensions[meta.key]?.support?.length) && <details className="report-references"><summary>评分原文依据</summary>{selected!.snapshot.proposal.dimensions[meta.key].support!.map((claim, index) => <div className="validation-item" key={index}><p>{claim.quote}</p><p className="source-location">{claim.use === 'background' ? '背景资料，不用于支持分数' : '评分依据'} · {claim.subject} · {claim.metric} · {claim.period} · {claim.unit}</p></div>)}</details>}<EvidenceReferences ids={d.evidence_ids} evidence={selected!.snapshot.evidence} /></div>;
      })}</div><h4>资料与证据状态</h4><p>保存资料 {r.evidence_count ?? selected!.snapshot.evidence.length} 条 · 规范化来源 {r.evidence_evaluated ? r.unique_sources : '未完整核算'} 个 · 发布主体 {r.publisher_count ?? '尚未核对'}。资料数量不代表独立验证次数。</p>{r.warnings.length > 0 && <ul>{r.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul>}{r.assumptions.length > 0 && <><h4>关键假设与证据</h4>{r.assumptions.map(a => <div className="assumption-result" key={a.id}><span className="evidence-level">{a.level}</span><div><strong>{a.claim}</strong><EvidenceReferences ids={a.evidence_ids} evidence={selected!.snapshot.evidence} /></div></div>)}</>}</section>
      <section className="report-section argument-columns"><div><h3>正方结论</h3><ol>{r.pros.map((p, i) => <li key={i}>{p}</li>)}</ol></div><div><h3>反方结论</h3><ol>{r.cons.map((p, i) => <li key={i}>{p}</li>)}</ol></div></section>
      <section className="report-section"><h3>最强反对意见</h3>{selected!.snapshot.proposal.strongest_objections?.length ? <ol>{selected!.snapshot.proposal.strongest_objections.map((item, i) => <li key={i}>{item}</li>)}</ol> : <p>本版未单独归纳，请结合反方结论复核。</p>}</section>
      <DecisionBrief brief={{ ...selected!.snapshot.proposal?.decision_brief, ...r.upgrade_requirements }} />
      <PilotRecommendation life={selected!.snapshot.project.lifecycle} />
      <section className="report-section"><h3>验证与退出</h3>{r.missing.length > 0 && <><h4>影响当前决策的关键缺口</h4><ul className="missing-list">{r.missing.map((m, i) => <li key={i}><span />{m}</li>)}</ul></>}{r.grade === 'NR' && <p>以下是补证任务；资料不足时不建议投入。</p>}{r.resource_plan.note && <p>{r.resource_plan.note}</p>}{r.resource_plan.available_limit != null && <p>当前可用资源上限：¥{r.resource_plan.available_limit.toLocaleString('zh-CN')}（{r.resource_plan.formula}）</p>}{r.validation_plan.map((v, i) => <div className="validation-item" key={i}><h4>{v.claim}</h4><p>{v.method}</p><p>通过：{v.pass}</p><p>停止 / 调整：{v.fail}</p></div>)}<h4>重新评估条件</h4><ul>{r.reassessment_triggers.map((t, i) => <li key={i}>{t}</li>)}</ul></section>
      <div className="report-meta">规则版本 {r.rule_version} · 证据与输入已保存快照 · 置信度不是项目成功概率</div>
    </article>}
    <div className="manual-review-heading"><div><h3>{detail.project.proposal ? '核对当前评分建议' : '需要人工评审？'}</h3><p>{detail.project.proposal ? '逐项检查依据，确认后由规则引擎计算等级。' : '可由评审人员填写八维判断与关键假设。系统不会将人工填写伪装成模型分析。'}</p></div><button className="secondary" onClick={() => { setEdit(!edit); }}>{edit ? '收起评审表' : '打开评审表'}<ChevronDown size={16} /></button></div>
    {edit && <form className="form-document manual-review" onSubmit={e => { e.preventDefault(); evaluate(true); }}><section className="form-section"><h3>八维判断</h3><p className="section-description">未知保持空白；低于3分需要已知负面事实，不能因为缺证据直接扣低业务分。</p>{dimensions.map(d => { const v = proposal.dimensions[d.key] || { score: null, reason: '', basis: 'unknown', evidence_ids: [] }; return <fieldset className="score-editor" key={d.key}><legend>{d.name}<span>权重 {d.weight}%</span></legend><div className="score-inputs"><Field label="业务原始分"><select value={v.score ?? ''} onChange={e => setDimension(d.key, { score: e.target.value === '' ? null : Number(e.target.value) })}><option value="">未知 / 无法判断</option>{Array.from({ length: 11 }, (_, i) => i / 2).map(n => <option key={n} value={n}>{n} / 5</option>)}</select></Field><Field label="判断性质"><select value={v.basis} onChange={e => setDimension(d.key, { basis: e.target.value })}><option value="assumption">假设或推断</option><option value="fact">已知事实</option><option value="unknown">未知</option></select></Field><Field label="关联证据"><ReferenceSelect evidence={detail.evidence} ids={v.evidence_ids} onChange={evidence_ids => setDimension(d.key, { evidence_ids })} /></Field></div><Field label="具体依据"><textarea rows={2} value={v.reason} onChange={e => setDimension(d.key, { reason: e.target.value })} placeholder="说明为什么给这个分数，区分事实、推断和未知。" /></Field></fieldset>; })}</section>
      <section className="form-section"><div className="section-heading"><h3>决定项目成立的关键假设</h3><button type="button" className="secondary" onClick={() => setProposal(p => ({ ...p, assumptions: [...p.assumptions, { id: "P0-" + crypto.randomUUID().slice(0, 8), claim: "", evidence_ids: [], validation_method: "", pass_threshold: "", fail_threshold: "" }] }))}>添加关键假设</button></div>{proposal.assumptions.map((a, i) => <fieldset className="assumption-editor" key={a.id}><legend>关键假设 {i + 1}</legend><button type="button" className="secondary" disabled={proposal.assumptions.length <= 1} onClick={() => setProposal(p => ({ ...p, assumptions: p.assumptions.filter((_, index) => index !== i) }))}>移除此假设</button><Field label="假设内容"><input value={a.claim} onChange={e => setAssumption(i, { claim: e.target.value })} /></Field><Field label="支持这个假设的证据"><ReferenceSelect ids={a.evidence_ids} evidence={detail.evidence} onChange={ids => setAssumption(i, { evidence_ids: ids })} /></Field><div className="form-grid"><Field label="验证方式"><input value={a.validation_method || ''} onChange={e => setAssumption(i, { validation_method: e.target.value })} /></Field><Field label="通过阈值"><input value={a.pass_threshold || ''} onChange={e => setAssumption(i, { pass_threshold: e.target.value })} /></Field><Field label="失败与止损阈值"><input value={a.fail_threshold || ''} onChange={e => setAssumption(i, { fail_threshold: e.target.value })} /></Field></div></fieldset>)}</section>
      <section className="form-section"><div className="section-heading"><h3>一票否决项</h3><button type="button" className="secondary" onClick={() => setProposal(p => ({ ...p, vetoes: [...p.vetoes, { reason: '', confirmed: false, evidence_ids: [] }] }))}>添加否决项</button></div><p className="section-description">只有已确认且有核验证据支持的否决事实才会触发C级；未确认的风险会限制评级上限。</p>{proposal.vetoes.length === 0 && <p>当前没有提出一票否决项。</p>}{proposal.vetoes.map((v, i) => <fieldset className="assumption-editor" key={i}><legend>否决项 {i + 1}</legend><Field label="否决事实与原因"><textarea required rows={2} value={v.reason} onChange={e => setProposal(p => ({ ...p, vetoes: p.vetoes.map((item, index) => index === i ? { ...item, reason: e.target.value } : item) }))} /></Field><Field label="支持否决事实的证据"><ReferenceSelect ids={v.evidence_ids} evidence={detail.evidence} onChange={evidence_ids => setProposal(p => ({ ...p, vetoes: p.vetoes.map((item, index) => index === i ? { ...item, evidence_ids } : item) }))} /></Field><label className="checkbox"><input type="checkbox" checked={v.confirmed} onChange={e => setProposal(p => ({ ...p, vetoes: p.vetoes.map((item, index) => index === i ? { ...item, confirmed: e.target.checked } : item) }))} />已核实这项事实构成无法解决的否决条件</label><button type="button" className="secondary" onClick={() => setProposal(p => ({ ...p, vetoes: p.vetoes.filter((_, index) => index !== i) }))}>移除此否决项</button></fieldset>)}</section>
      <section className="form-section"><h3>正反方与评级限制</h3><div className="form-grid"><Field label="支持理由，每行一条，至少3条"><textarea rows={4} value={proposal.pros.join('\n')} onChange={e => setProposal(p => ({ ...p, pros: e.target.value.split('\n') }))} /></Field><Field label="反对理由，每行一条，至少3条"><textarea rows={4} value={proposal.cons.join('\n')} onChange={e => setProposal(p => ({ ...p, cons: e.target.value.split('\n') }))} /></Field></div><Field label="B级封顶原因，每行一条" hint="如核心价值从未真实验证、老板是唯一关键人、重资产投入后才能测试。没有已知触发项时留空。"><textarea rows={3} value={proposal.policy_caps.join('\n')} onChange={e => setProposal(p => ({ ...p, policy_caps: e.target.value ? e.target.value.split('\n') : [] }))} /></Field><h4>S级额外条件</h4>{[['repeatable', '可复制性与重复验证已确认'], ['resources_available', '公司确实能够投入所需核心资源'], ['portfolio_feasible', '与现有项目的机会成本及资源组合合理'], ['review_complete', '已核对主要风险与反对理由并反映到以上判断']].map(([key, label]) => <label className="checkbox" key={key}><input type="checkbox" checked={proposal.s_conditions[key] === true} onChange={e => setProposal(p => ({ ...p, s_conditions: { ...p.s_conditions, [key]: e.target.checked } }))} />{label}</label>)}<div className="review-confirm"><label className="checkbox"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} required />我已核对以上事实、证据与判断，确认用于本次评级</label><button className="primary" disabled={busy || !confirmed || pendingFacts} type="submit">确认并计算评级<ArrowUpRight size={16} /></button></div></section>
    </form>}
    {selected && <ReportAssistant key={selected.id} projectId={detail.project.id} report={selected} disabled={busy} onRevise={onRevise} />}
  </section>;
}
