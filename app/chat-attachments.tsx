'use client';
import { useEffect, useRef, useState } from 'react';
import { waitForJob, type Evidence, type Job } from '../lib/types';

function event(target: HTMLVideoElement, name: string) {
  return new Promise<void>((resolve, reject) => {
    const done = () => { clearTimeout(timer); target.removeEventListener(name, ok); target.removeEventListener('error', fail); };
    const ok = () => { done(); resolve(); };
    const fail = () => { done(); reject(new Error('视频无法解码，请转为 MP4/H.264 后重试')); };
    const timer = setTimeout(fail, 15000);
    target.addEventListener(name, ok, { once: true }); target.addEventListener('error', fail, { once: true });
  });
}
const jpeg = (canvas: HTMLCanvasElement) => new Promise<Blob>((resolve, reject) => canvas.toBlob(b => b ? resolve(b) : reject(new Error('图片处理失败')), 'image/jpeg', 0.82));

async function prepare(file: File, status: (s: string) => void): Promise<{ file: File; label: string }> {
  if (file.type.startsWith('video/')) {
    const video = document.createElement('video'); const url = URL.createObjectURL(file);
    video.muted = true; video.preload = 'metadata'; video.playsInline = true;
    try {
      const loaded = event(video, 'loadedmetadata'); video.src = url; await loaded;
      if (!Number.isFinite(video.duration) || video.duration <= 0) throw new Error('无法读取视频时长');
      if (video.duration > 1800) throw new Error('视频超过30分钟，请按片段上传');
      const canvas = document.createElement('canvas'); canvas.width = 1280; canvas.height = 1170;
      const ctx = canvas.getContext('2d')!; ctx.fillStyle = '#111'; ctx.fillRect(0, 0, canvas.width, canvas.height);
      const stamps: string[] = [];
      for (let i = 0; i < 6; i++) {
        const at = video.duration * (i + 0.5) / 6;
        status(`本地抽帧 ${i + 1}/6（原视频不上传）`);
        const seeked = event(video, 'seeked'); video.currentTime = at; await seeked;
        const x = (i % 2) * 640; const y = Math.floor(i / 2) * 390;
        const scale = Math.min(640 / video.videoWidth, 360 / video.videoHeight);
        ctx.drawImage(video, x + (640 - video.videoWidth * scale) / 2, y, video.videoWidth * scale, video.videoHeight * scale);
        ctx.fillStyle = '#fff'; ctx.font = '20px sans-serif'; ctx.fillText(`${at.toFixed(1)} s`, x + 10, y + 380); stamps.push(at.toFixed(1));
      }
      return { file: new File([await jpeg(canvas)], 'video-frames.jpg', { type: 'image/jpeg' }), label: `${file.name}｜仅6帧 ${stamps.join(',')}秒 / ${video.duration.toFixed(1)}秒；无音频，不代表完整视频` };
    } finally { video.removeAttribute('src'); video.load(); URL.revokeObjectURL(url); }
  }
  if (file.type.startsWith('image/') && !/\.tiff?$/i.test(file.name)) {
    status('本地压缩图片…');
    const image = await createImageBitmap(file);
    try {
      const scale = Math.min(1, 1600 / Math.max(image.width, image.height));
      const canvas = document.createElement('canvas'); canvas.width = Math.max(1, Math.round(image.width * scale)); canvas.height = Math.max(1, Math.round(image.height * scale));
      const ctx = canvas.getContext('2d')!; ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height); ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      return { file: new File([await jpeg(canvas)], 'image.jpg', { type: 'image/jpeg' }), label: file.name + '｜等比压缩图片，细小文字请另传局部高清图' };
    } finally { image.close(); }
  }
  if (file.size > 20_000_000) throw new Error('文档最大20MB，请拆分后上传');
  return { file, label: file.name };
}

function upload(projectId: string, file: File, label: string, progress: (s: string) => void) {
  return new Promise<Job>((resolve, reject) => {
    const xhr = new XMLHttpRequest(); xhr.open('POST', `/api/projects/${projectId}/attachments`); xhr.timeout = 120000;
    xhr.upload.onprogress = e => { if (e.lengthComputable) progress(`上传 ${Math.round(e.loaded / e.total * 100)}%`); };
    xhr.onerror = () => reject(new Error('上传连接失败，请检查项目记录后重试'));
    xhr.ontimeout = () => reject(new Error('上传超时，请检查项目中是否已有附件后再重试'));
    xhr.onload = () => {
      try { const data = JSON.parse(xhr.responseText); if (xhr.status < 200 || xhr.status >= 300) throw new Error(data.detail || '上传失败'); resolve(data); }
      catch (e) { reject(e); }
    };
    const form = new FormData(); form.append('file', file); form.append('label', label); xhr.send(form);
  });
}

export function ChatAttachments({ projectId, disabled, onBusy, onSaved }: { projectId: string; disabled: boolean; onBusy: (busy: boolean) => void; onSaved: () => Promise<void> }) {
  const [status, setStatus] = useState(''); const active = useRef(false); const input = useRef<HTMLInputElement>(null);
  const zone = useRef<HTMLDivElement>(null);
  const depth = useRef(0);
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    const target = zone.current?.closest('.conversation') || zone.current;
    if (!target) return;
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types || []).includes('Files');
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault(); depth.current++;
      if (!disabled && !active.current) setDragging(true);
    };
    const over = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = disabled || active.current ? 'none' : 'copy';
    };
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth.current = Math.max(0, depth.current - 1);
      if (!depth.current) setDragging(false);
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault(); depth.current = 0; setDragging(false);
      if (disabled || active.current) { setStatus('请等待当前处理完成后再上传'); return; }
      void add(e.dataTransfer?.files || null);
    };
    target.addEventListener('dragenter', enter as EventListener);
    target.addEventListener('dragover', over as EventListener);
    target.addEventListener('dragleave', leave as EventListener);
    target.addEventListener('drop', drop as EventListener);
    return () => {
      target.removeEventListener('dragenter', enter as EventListener);
      target.removeEventListener('dragover', over as EventListener);
      target.removeEventListener('dragleave', leave as EventListener);
      target.removeEventListener('drop', drop as EventListener);
    };
  });
  async function add(files: FileList | null) {
    if (!files?.length || disabled || active.current) return;
    if (files.length > 5) { setStatus('每批最多5个文件'); return; }
    active.current = true; onBusy(true); const start = performance.now();
    try {
      for (const file of Array.from(files)) {
        setStatus(`准备 ${file.name}`); const prepared = await prepare(file, setStatus);
        const job = await upload(projectId, prepared.file, prepared.label, setStatus);
        setStatus('上传完成，正在提取内容 / 识别画面…');
        await waitForJob<Evidence>(job.id);
      }
      await onSaved(); setStatus(`附件已保存，待核验；用时 ${((performance.now() - start) / 1000).toFixed(1)} 秒。发送问题后参与分析。`);
    } catch (e) { setStatus(e instanceof Error ? e.message : '附件处理失败'); }
    finally { active.current = false; onBusy(false); if (input.current) input.current.value = ''; }
  }
  return <div ref={zone} className="chat-attachments">{dragging && <div className="chat-drop-overlay" aria-hidden="true">松开即可上传文档、图片或视频<span>每批最多5个文件</span></div>}<label className="secondary upload-button">上传或拖入文档 / 图片 / 视频<input ref={input} type="file" multiple disabled={disabled} accept=".txt,.md,.csv,.json,.docx,.xlsx,.pptx,.pdf,.png,.jpg,.jpeg,.webp,.gif,.bmp,.tif,.tiff,video/*" onChange={e => void add(e.target.files)} /></label><small>文档≤20MB</small><p role="status">{status}</p></div>;
}
