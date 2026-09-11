import type { Lifecycle, Rating } from './types';

// Older snapshots have no saved opening explanation; keep their data intact.
export function deferralReason(result: Rating, life?: Lifecycle): string {
  if (result.deferral_reason) return result.deferral_reason;
  const missing = result.missing.length ? result.missing.join('、') : '足以支持八维判断的关键依据';
  const labels: Record<string, string> = { unknown: '当前无法补足', external: '需外部核查', future: '需实际验证' };
  const details = Object.values(life?.coverage || {}).filter(item => labels[item.status] && item.reason.trim())
    .map(item => `${labels[item.status]}：${item.reason}`);
  return `暂缓评级：尚未形成可靠判断的关键依据包括${missing}；${details.length ? details.join('；') + '。' : ''}这些缺口会影响投入与验证是否可行的判断，当前无法给出可靠等级。`;
}
