'use client';
import { Detail, Stage } from '../lib/types';

const stages: Record<Stage, string> = { pre: '启动前', during: '试点中', post: '试点后' };

type Props = { detail: Detail; busy: boolean; onFollowup: (message: string, advance: boolean) => void };

export function LifecyclePanel({ detail, busy, onFollowup }: Props) {
  const stage = detail.project.lifecycle?.stage || 'pre';
  const hasReport = detail.assessments.some(a => (a.result.stage || a.snapshot.project.lifecycle?.stage) === stage);
  const advance = hasReport && stage !== 'post';
  const target = advance ? (stage === 'pre' ? 'during' : 'post') : stage;
  const message = target === 'during'
    ? '请结合启动前报告，先和我讨论试点实际执行情况、已有记录与原计划的差异，再逐项重新梳理八维。未提供的结果请询问，不要假设已经验证。'
    : target === 'post'
      ? '请结合试点中报告，先和我讨论试点最终结果、成本与原计划的差异，再综合历史报告和本次补充重新梳理八维。不要自动生成报告。'
      : '请结合当前项目和已有资料，继续梳理启动前八维信息，不要假设已有试点结果。';
  return <section className="stage-strip" aria-label="项目阶段">
    <div className="stage-steps">{Object.entries(stages).map(([key, label], i) => <span key={key} className={stage === key ? 'current' : ''}>{i + 1}. {label}</span>)}</div>
    <p>{advance ? `结合本阶段报告，进入${stages[target]}访谈` : '结合已有资料与本次补充，完成本阶段八维判断'}</p>
    <button className="secondary" disabled={busy} onClick={() => onFollowup(message, advance)}>{advance ? `进入${stages[target]}访谈` : '继续阶段访谈'}</button>
  </section>;
}
