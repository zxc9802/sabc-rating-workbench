'use client';

import { ReactNode, useEffect, useState } from 'react';
import { api } from '../lib/types';

export function SessionGate({ children }: { children: (logout: ReactNode) => ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [required, setRequired] = useState(false);
  const [loading, setLoading] = useState(true);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function check() {
    setLoading(true); setError('');
    try {
      const state = await api<{ authenticated: boolean; required: boolean }>('/auth/session');
      setAuthenticated(state.authenticated); setRequired(state.required);
    } catch (e) { setError(e instanceof Error ? e.message : '连接失败'); }
    finally { setLoading(false); }
  }
  useEffect(() => {
    check();
    const expired = () => { setAuthenticated(false); setRequired(true); setError('登录已过期，请重新登录'); };
    window.addEventListener('sabc-session-expired', expired);
    return () => window.removeEventListener('sabc-session-expired', expired);
  }, []);
  if (loading) return <main className="loading-page">正在连接工作空间…</main>;
  if (authenticated) return <>{error && <div role="alert">{error}</div>}{children(required && <button className="secondary session-logout" onClick={async () => {
    try { await api('/auth/logout', 'POST'); setAuthenticated(false); }
    catch { setError('退出失败，请重试'); }
  }}>退出登录</button>)}</>;
  return <main className="loading-page"><form className="session-card" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError('');
    try { await api('/auth/login', 'POST', { password }); setPassword(''); setAuthenticated(true); }
    catch (e) { setError(e instanceof Error ? e.message : '登录失败'); }
    finally { setBusy(false); }
  }}><h1>SABC 项目评级</h1><p>登录你的私有工作空间</p>
    {error && <p role="alert">{error}</p>}
    {required ? <><label htmlFor="access-password">访问密码</label><input id="access-password" type="password" autoComplete="current-password" required maxLength={512} value={password} onChange={e => setPassword(e.target.value)} /><button className="primary" disabled={busy || !password}>{busy ? '正在登录…' : '登录工作空间'}</button></> : <button type="button" className="secondary" onClick={check}>重新连接</button>}
  </form></main>;
}
