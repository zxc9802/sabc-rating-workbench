'use client';

import { Fragment, ReactNode, useEffect, useState } from 'react';
import { api } from '../lib/types';

export function SessionGate({ children }: { children: (logout: ReactNode) => ReactNode }) {
  const [authenticated, setAuthenticated] = useState(false);
  const [required, setRequired] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loginUrl, setLoginUrl] = useState('');
  const [account, setAccount] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function check(quiet = false) {
    if (!quiet) setLoading(true);
    setError('');
    try {
      const state = await api<{ authenticated: boolean; required: boolean; mode?: string; login_url?: string; user?: { id: string; name: string } }>('/auth/session');
      setLoginUrl(state.mode === 'sso' ? state.login_url || '/api/sso/start' : '');
      if (state.user) {
        if (sessionStorage.getItem('sabc-account') !== state.user.id) {
          sessionStorage.removeItem('sabc-project');
          for (const key of Object.keys(localStorage)) if (key.startsWith('sabc-request-')) localStorage.removeItem(key);
          sessionStorage.setItem('sabc-account', state.user.id);
        }
        setAccount(state.user.id);
      }
      setAuthenticated(state.authenticated); setRequired(state.required);
    } catch (e) { setError(e instanceof Error ? e.message : '连接失败'); }
    finally { setLoading(false); }
  }
  useEffect(() => {
    check();
    const expired = () => { setAuthenticated(false); setRequired(true); setError('登录已过期，请重新登录'); };
    window.addEventListener('sabc-session-expired', expired);
    const refresh = () => { if (document.visibilityState === 'visible') void check(true); };
    window.addEventListener('focus', refresh);
    const timer = window.setInterval(refresh, 30000);
    return () => { window.removeEventListener('sabc-session-expired', expired); window.removeEventListener('focus', refresh); window.clearInterval(timer); };
  }, []);
  if (loading) return <main className="loading-page">正在连接工作空间…</main>;
  if (authenticated) return <Fragment key={account}>{error && <div role="alert">{error}</div>}{children(required && <button className="secondary session-logout" onClick={async () => {
    try { await api('/auth/logout', 'POST'); sessionStorage.removeItem('sabc-project'); setAuthenticated(false); }
    catch { setError('退出失败，请重试'); }
  }}>退出登录</button>)}</Fragment>;
  if (loginUrl) return <main className="loading-page"><div className="session-card"><h1>SABC 项目评级</h1><p>使用主站账号进入你的项目工作空间</p>{error && <p role="alert">{error}</p>}<a className="primary" href={loginUrl}>使用主站账号登录</a></div></main>;
  return <main className="loading-page"><form className="session-card" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError('');
    try { await api('/auth/login', 'POST', { password }); setPassword(''); setAuthenticated(true); }
    catch (e) { setError(e instanceof Error ? e.message : '登录失败'); }
    finally { setBusy(false); }
  }}><h1>SABC 项目评级</h1><p>登录你的私有工作空间</p>
    {error && <p role="alert">{error}</p>}
    {required ? <><label htmlFor="access-password">访问密码</label><input id="access-password" type="password" autoComplete="current-password" required maxLength={512} value={password} onChange={e => setPassword(e.target.value)} /><button className="primary" disabled={busy || !password}>{busy ? '正在登录…' : '登录工作空间'}</button></> : <button type="button" className="secondary" onClick={() => check()}>重新连接</button>}
  </form></main>;
}
