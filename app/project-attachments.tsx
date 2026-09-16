'use client';

import { useState } from 'react';
import { FileText, Image, Paperclip, Video, X } from 'lucide-react';
import { ATTACHMENT_ACCEPT } from './chat-attachments';

export function ProjectAttachments({ files, disabled, onChange }: { files: File[]; disabled: boolean; onChange: (files: File[]) => void }) {
  const [error, setError] = useState('');
  const [dragging, setDragging] = useState(false);

  function add(selected: FileList | null) {
    if (!selected?.length || disabled) return;
    const next = [...files];
    for (const file of Array.from(selected)) {
      if (!file.type.startsWith('video/') && !ATTACHMENT_ACCEPT.split(',').some(ext => file.name.toLowerCase().endsWith(ext))) {
        setError(`${file.name}：暂不支持此格式，请选择文档、图片或视频。`); return;
      }
      if (!file.type.startsWith('video/') && !file.type.startsWith('image/') && file.size > 20_000_000) {
        setError(`${file.name}：单个文档最大20MB，请拆分后上传。`); return;
      }
      if (!next.some(item => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) next.push(file);
    }
    if (next.length > 5) { setError('每次最多选择5个文件，请移除部分文件后再添加。'); return; }
    setError(''); onChange(next);
  }

  return <div className={'project-attachments' + (dragging ? ' dragging' : '')}
    onDragOver={e => {
      if (!Array.from(e.dataTransfer.types).includes('Files')) return;
      e.preventDefault(); e.dataTransfer.dropEffect = disabled ? 'none' : 'copy';
      if (!disabled) setDragging(true);
    }}
    onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false); }}
    onDrop={e => { e.preventDefault(); setDragging(false); add(e.dataTransfer.files); }}>
    <div className="project-upload-heading">
      <label className="secondary upload-button" aria-disabled={disabled}>
        <Paperclip size={16} />上传文档 / 图片 / 视频
        <input type="file" aria-label="上传项目资料" multiple accept={ATTACHMENT_ACCEPT} disabled={disabled} onChange={e => { add(e.target.files); e.target.value = ''; }} />
      </label>
      <span>也可拖入此处，最多5个文件</span>
    </div>
    <p className="project-upload-help">文档≤20MB；视频≤30分钟，仅提取画面，不含音频。</p>
    {files.length > 0 && <>
      <ul className="project-upload-list" aria-label="待上传的项目资料">{files.map((file, index) => {
        const Icon = file.type.startsWith('video/') ? Video : file.type.startsWith('image/') ? Image : FileText;
        return <li key={`${file.name}-${file.size}-${file.lastModified}`}><Icon size={16} /><span title={file.name}>{file.name}</span><small>{file.size < 1_000_000 ? `${Math.max(1, Math.round(file.size / 1000))} KB` : `${(file.size / 1_000_000).toFixed(1)} MB`}</small><button type="button" disabled={disabled} aria-label={`移除 ${file.name}`} onClick={() => { setError(''); onChange(files.filter((_, i) => i !== index)); }}><X size={15} /></button></li>;
      })}</ul>
      <p className="project-upload-help" role="status">已选择 {files.length} 个文件，点击“开始评估”后上传并读取。也可以只上传资料开始。</p>
    </>}
    {error && <p className="project-upload-error" role="alert">{error}</p>}
  </div>;
}
