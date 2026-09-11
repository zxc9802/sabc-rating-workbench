'use client';

import { useEffect, useRef, useState } from 'react';
import { Mic, Square } from 'lucide-react';

type Props = { value: string; disabled: boolean; onChange: (text: string) => void; onBusy: (busy: boolean) => void };
type Session = { socket?: WebSocket; stream?: MediaStream; context?: AudioContext; worklet?: AudioWorkletNode; timer?: ReturnType<typeof setTimeout>; stopping: boolean };

export function VoiceInput({ value, disabled, onChange, onBusy }: Props) {
  const [state, setState] = useState<'idle' | 'connecting' | 'recording' | 'finishing'>('idle');
  const [error, setError] = useState('');
  const active = useRef<Session | null>(null);
  const callbacks = useRef({ onChange, onBusy });
  callbacks.current = { onChange, onBusy };

  function release(session: Session) {
    clearTimeout(session.timer);
    session.stream?.getTracks().forEach(track => track.stop());
    session.worklet?.disconnect();
    if (session.context && session.context.state !== 'closed') void session.context.close();
    session.socket?.close();
    if (active.current === session) {
      active.current = null;
      setState('idle');
      callbacks.current.onBusy(false);
    }
  }
  useEffect(() => () => { if (active.current) release(active.current); }, []);

  function stop() {
    const session = active.current;
    if (!session || session.stopping) return;
    if (!session.worklet) { release(session); return; }
    session.stopping = true;
    setState('finishing');
    session.worklet.port.postMessage('stop');
    clearTimeout(session.timer);
    session.timer = setTimeout(() => { setError('最后一段识别超时，已识别文字已保留。'); release(session); }, 12000);
  }

  async function start() {
    if (disabled || active.current) return;
    const session: Session = { stopping: false };
    active.current = session;
    setError(''); setState('connecting'); callbacks.current.onBusy(true);
    const prefix = value ? value.replace(/\s*$/, '') + '\n' : '';
    const fail = (message: string) => { if (active.current === session) { setError(message); release(session); } };
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('请使用支持麦克风的浏览器，并通过 HTTPS 访问。');
      session.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      if (active.current !== session) { session.stream.getTracks().forEach(track => track.stop()); return; }
      session.context = new AudioContext({ sampleRate: 16000 });
      await session.context.audioWorklet.addModule('/speech-pcm.js');
      await session.context.resume();
      if (active.current !== session) return;
      const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/speech/stream`);
      session.socket = socket;
      session.timer = setTimeout(() => fail('语音连接超时，请重试。'), 15000);
      socket.onmessage = event => {
        if (active.current !== session) return;
        try {
          const result = JSON.parse(event.data);
          if (result.error) { fail(result.error); return; }
          if (result.ready && !session.worklet) {
            clearTimeout(session.timer);
            const context = session.context!;
            const worklet = new AudioWorkletNode(context, 'speech-pcm');
            session.worklet = worklet;
            worklet.port.onmessage = ({ data }) => {
              if (active.current !== session || socket.readyState !== WebSocket.OPEN) return;
              if (data === 'stopped') {
                session.stream?.getTracks().forEach(track => track.stop());
                void context.close();
                socket.send('stop');
              } else if (socket.bufferedAmount < 128000) socket.send(data);
              else fail('网络较慢，录音已停止，已识别文字已保留。');
            };
            context.createMediaStreamSource(session.stream!).connect(worklet);
            worklet.connect(context.destination);
            setState('recording');
            session.timer = setTimeout(stop, 120000);
          }
          if (typeof result.text === 'string') callbacks.current.onChange((prefix + result.text).slice(0, 12000));
          if (result.done) release(session);
        } catch { fail('语音返回异常，请重试。'); }
      };
      socket.onerror = () => fail('语音连接失败，请检查网络或重新登录。');
      socket.onclose = () => { if (active.current === session) fail('语音连接已结束，已识别文字已保留。'); };
    } catch (e) {
      fail(e instanceof DOMException && e.name === 'NotAllowedError' ? '请允许使用麦克风后重试。' : e instanceof Error ? e.message : '无法启动语音输入。');
    }
  }

  return <div className="voice-input"><button type="button" className={`voice-button ${state !== 'idle' ? 'is-recording' : ''}`} disabled={state === 'idle' && disabled || state === 'finishing'} aria-pressed={state !== 'idle'} onClick={state === 'idle' ? start : stop}>
    {state === 'idle' ? <Mic size={24} /> : <Square size={20} />}<span>{state === 'idle' ? '语音输入' : state === 'connecting' ? '连接中 · 取消' : state === 'finishing' ? '正在完成转写' : '正在听 · 点击停止'}</span>
  </button><small role="status">{error || (state === 'recording' ? '边说边转写，最长2分钟；停止后可编辑发送' : '')}</small></div>;
}
