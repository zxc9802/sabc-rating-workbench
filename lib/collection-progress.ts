import type { Lifecycle } from './types';

const DIMENSIONS = ['strategy', 'market', 'return', 'resources', 'replication', 'cash', 'risk', 'opportunity'] as const;

export function collectionProgress(life?: Lifecycle) {
  const complete = DIMENSIONS.filter(key => {
    const item = life?.coverage[key];
    return !!item?.reason.trim() && (item.status === 'known' ||
      (item.status === 'future' && life?.stage !== 'post'));
  }).length;
  const ready = !!life?.confirmed && complete === DIMENSIONS.length;
  return { complete, ready, percent: ready ? 100 : Math.min(99, Math.round(complete / DIMENSIONS.length * 100)) };
}
