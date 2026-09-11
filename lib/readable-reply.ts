type Reference = { id: string; title: string };

export function readableWarning(content: string, evidence: Reference[]): string {
  const item = evidence.find(e => content.startsWith(e.id + '：'));
  if (item) return `${item.title}：${content.slice(item.id.length + 1)}`;
  return content.replace(/^(?:[a-f0-9]{32}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})：/i, '相关资料：');
}

// Keep original records and URLs intact; translate internal references only for display.
export function readableReply(content: string, evidence: Reference[] = [], streaming = false): string {
  const label = (id: string) => {
    const item = evidence.find(e => e.id === id);
    const title = (item?.title || '相关资料').replace(/[\\[\]()`*_]/g, '');
    return `[${title}](#evidence)`;
  };
  let result = content.replace(/https?:\/\/[^\s)]+|(?:证据\s*(?:ID|编号)\s*(?:为|是|：|:)?\s*)?\b(?:[a-f0-9]{32}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})\b/gi, value => {
    if (/^https?:/.test(value)) return value;
    const id = value.match(/(?:[a-f0-9]{32}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})$/i)![0];
    return label(id);
  });
  if (streaming) result = result.replace(/(?:证据\s*(?:ID|编号)\s*(?:为|是|：|:)?\s*[a-f0-9-]*|[a-f0-9-]{8,35})$/i, '');
  const types: Record<string, string> = { growth: '商业增长', internal: '内部AI / 提效', strategic: '战略能力 / 资产', asset: '重资产 / 扩张' };
  result = result.replace(/https?:\/\/[^\s)]+|\b(growth|internal|strategic|asset)\b/g, (value, type) => type ? types[type] : value);
  return result.replace(/https?:\/\/[^\s)]+|\bNR\b/g, value => value === 'NR' ? '暂缓评级' : value);
}
