import type { Detail, Message, Stage } from './types';

export const interviewStages = { pre: '启动前', during: '试点中', post: '试点后', legacy: '历史访谈（阶段未标注）' };
export function interviewStage(message: Message, detail: Detail): Stage | 'legacy' {
  if (message.stage) return message.stage;
  // Historical snapshots are immutable; use the earliest matching snapshot.
  const reports = [...detail.assessments].sort((a, b) => a.created_at.localeCompare(b.created_at));
  for (const report of reports) {
    const matched = message.time && report.snapshot.project.messages?.some(m => m.time === message.time && m.role === message.role && m.content === message.content);
    const stage = report.result.stage || report.snapshot.project.lifecycle?.stage;
    if (matched && stage) return stage;
  }
  const event = message.time && [...(detail.project.lifecycle?.events || [])]
    .filter(e => e.time <= message.time! && ['set_stage', 'advance', 'start', 'complete'].includes(e.action))
    .sort((a, b) => b.time.localeCompare(a.time))[0];
  return event ? event.stage : 'legacy';
}
