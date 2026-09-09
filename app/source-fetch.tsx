'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/types';

const choices = {
  local: ['地方公共数据', 'dazhou/search:人口', '地区/search:关键词，或地区/目录编号'],
  trends: ['Google Trends', 'US', '两位地区代码；当前热门搜索 RSS'],
  worldbank: ['World Bank', 'CHN/SP.POP.TOTL', '国家代码/指标代码'],
  github: ['GitHub', 'fastapi/fastapi', '仓库所有者/仓库名'],
  sec: ['SEC EDGAR', '320193/facts', 'CIK/facts 获取财务指标；仅 CIK 获取披露索引'],
  stats: ['国家统计局', 'https://www.stats.gov.cn/…/文章.html', '官方统计文章完整网址'],
  miit: ['工信部', 'https://wap.miit.gov.cn/…/文章.html', '官方统计文章完整网址'],
  cninfo: ['巨潮资讯', 'https://static.cninfo.com.cn/finalpage/…/公告.PDF', '官方公告 PDF 完整网址'],
  law: ['国家法律法规数据库', '个人信息保护法', '关键词检索；输入 id:法规编号 获取官方 PDF 条文'],
  apple: ['Apple Search', 'us/notion', '商店地区/搜索关键词'],
};

export function SourceFetch({ projectId, busy, refresh, run }: { projectId: string; busy: boolean; refresh: () => Promise<void>; run: (task: () => Promise<void>, message?: string) => Promise<void> }) {
  const [source, setSource] = useState<keyof typeof choices>('worldbank');
  const [query, setQuery] = useState('');
  const [local, setLocal] = useState<{regions:{id:string;name:string;url:string;method:string;note:string;example?:string}[];captures:{id:string;region:string;title:string;data_period:string;retrieved_at:string;scope:string}[]}>();
  const [localError,setLocalError] = useState('');
  useEffect(() => { api<NonNullable<typeof local>>('/local-sources').then(setLocal).catch(e => setLocalError(e.message)); }, []);
  return <details className="evidence-item"><summary>从官方接口或地方数据获取外部证据</summary><form className="form-section" onSubmit={e => {
    e.preventDefault(); run(async () => { await api(`/projects/${projectId}/sources/${source}`, 'POST', { query }); await refresh(); }, '真实数据已保存到证据库，请核对适用范围');
  }}><div className="form-grid"><label>数据来源<select value={source} onChange={e => { setSource(e.target.value as keyof typeof choices); setQuery(''); }}>{Object.entries(choices).map(([id, value]) => <option key={id} value={id}>{value[0]}</option>)}</select></label><label>{choices[source][2]}<input required maxLength={200} value={query} placeholder={choices[source][1]} onChange={e => setQuery(e.target.value)} /></label></div><p className="footnote">采集后保留原始来源与数据期间。外部资料只能提供间接依据，不能替代本项目验证。</p><button className="primary" disabled={busy || !query.trim()}>{busy ? '正在获取…' : '获取并保存证据'}</button></form>
    {source==='local' && <div className="form-section"><h3>各地区接入方式</h3>{localError && <p role="alert">{localError}</p>}{local?.regions.map(region=><div className="evidence-item" key={region.id}><strong><a href={region.url} target="_blank" rel="noreferrer">{region.name}</a> · {region.method}</strong><p className="footnote">{region.note}</p>{region.example && <button type="button" disabled={busy} onClick={()=>setQuery(region.example!)}>填入已验证目录</button>}</div>)}
    <h3>已采集的浏览器快照</h3><p className="footnote">使用快照会保留原采集时间，不会重新抓取。先核对地区、期间与样本范围。</p>{local?.captures.map(capture=><div className="evidence-item" key={capture.id}><strong>{capture.title}</strong><p className="footnote">数据期间：{capture.data_period}；采集时间：{capture.retrieved_at}</p><p className="footnote">{capture.scope}</p><button type="button" disabled={busy} onClick={()=>run(async()=>{await api(`/projects/${projectId}/local-captures/${capture.id}`,'POST',{});await refresh();},'快照已加入本项目证据，请核对后使用')}>加入本项目证据</button></div>)}
    <label>导入新的浏览器采集记录（JSON）<input type="file" accept=".json" disabled={busy} onChange={event=>{const file=event.target.files?.[0];if(!file)return;run(async()=>{if(file.size>1_000_000)throw new Error('采集记录不得超过1MB');await api('/local-captures','POST',JSON.parse(await file.text()));setLocal(await api('/local-sources'));},'采集记录已导入，可以加入项目证据');event.target.value='';}} /></label></div>}
  </details>;
}
