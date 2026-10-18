import { useRef, useState } from 'react';
import { LoaderCircle, UploadCloud } from 'lucide-react';
import { api } from './api';

export default function DocumentUpload() {
  const inputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function upload() {
    if (!file || busy) return;
    setMessage(''); setError('');
    if (file.size > 50 * 1024 * 1024) {
      setError('文件超过 50 MB，请选择较小的 PDF。');
      return;
    }
    setBusy(true);
    try {
      const body = new FormData();
      body.append('file', file);
      const result = await api('/api/documents/upload', { method: 'POST', body });
      setMessage(`${result.filename} 已保存到待处理目录。解析、切片与索引仍需按现有流程执行。`);
      setFile(null);
      if (inputRef.current) inputRef.current.value = '';
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return <section className="dash-panel data-upload" aria-labelledby="data-upload-title">
    <div className="data-upload-head">
      <div><span className="dash-kicker">资料接入</span><h2 id="data-upload-title">上传新文档</h2>
        <p>选择 PDF 后，文件会进入待处理目录。上传完成不代表内容已解析、切片或进入检索和图谱。</p></div>
      <UploadCloud size={28} aria-hidden="true"/>
    </div>
    <div className="data-upload-actions">
      <label className="data-upload-picker"><UploadCloud size={22}/><strong>{file?.name || '选择 PDF 文件'}</strong><span>仅 PDF，最大 50 MB</span>
        <input ref={inputRef} type="file" accept=".pdf,application/pdf" onChange={e=>{setFile(e.target.files?.[0] || null);setError('');setMessage('');}}/></label>
      <button className="dash-button dash-primary" type="button" onClick={upload} disabled={!file || busy}>
        {busy?<LoaderCircle className="spin" size={16}/>:<UploadCloud size={16}/>} {busy?'正在保存…':'保存到待处理目录'}
      </button>
    </div>
    {message && <div className="dash-notice" role="status">{message}</div>}
    {error && <div className="dash-error" role="alert">{error}</div>}
  </section>;
}
