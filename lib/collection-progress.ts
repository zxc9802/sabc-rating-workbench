import type { Lifecycle } from './types';

const DIMENSIONS = ['strategy', 'market', 'return', 'resources', 'replication', 'cash', 'risk', 'opportunity'] as const;

const COUNTS: Record<string, number> = { strategy: 3, market: 3, return: 8, resources: 3, replication: 3, cash: 5, risk: 3, opportunity: 3 };

export function collectionProgress(life?: Lifecycle, pendingQuestions: string[] = [], completedAnalysis = false) {
  const complete = DIMENSIONS.filter(key => {
    const item = life?.coverage[key];
    return !!item?.reason.trim() && item.status !== 'ask' && Object.values(item.items || {}).length === COUNTS[key]
      && Object.values(item.items || {}).every(check => check.verified && ['known', 'unknown', 'external', 'future'].includes(check.status));
  }).length;
  const ready = completedAnalysis && !!life?.confirmed && complete === DIMENSIONS.length && !pendingQuestions.length;
  const resolved = DIMENSIONS.reduce((count, key) => count + Object.values(life?.coverage[key]?.items || {})
    .filter(check => check.verified && ['known', 'unknown', 'external', 'future'].includes(check.status)).length, 0);
  const total = Object.values(COUNTS).reduce((sum, count) => sum + count, 0);
  // This bar measures phase-one collection only; report review has its own stage.
  return { complete, ready, percent: ready ? 100 : Math.min(99, Math.round(resolved / total * 100)) };
}
