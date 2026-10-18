'use client';
import {useEffect,useState} from 'react';
import {api} from '@/lib/api';
import {supabase} from '@/lib/supabase';

type Attachment={id:string;filename:string;size:number;created_at:string};
export default function EvidenceAttachments({recordId}:{recordId:string}){
  const [items,setItems]=useState<Attachment[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{api<Attachment[]>('/api/investigations/'+recordId+'/attachments').then(setItems).catch(e=>setError(String(e)))},[recordId]);
  async function upload(file:File){setBusy(true);setError('');try{const body=new FormData();body.set('file',file);await api('/api/investigations/'+recordId+'/attachments',{method:'POST',body});setItems(await api<Attachment[]>('/api/investigations/'+recordId+'/attachments'))}catch(e){setError(String(e))}finally{setBusy(false)}}
  async function download(item:Attachment){setError('');try{const session=(await supabase?.auth.getSession())?.data.session;if(!session)throw new Error('Sign in to continue');const base=process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000';const response=await fetch(`${base}/api/investigations/attachments/${item.id}`,{headers:{Authorization:`Bearer ${session.access_token}`},cache:'no-store'});if(!response.ok)throw new Error('Evidence download failed');const url=URL.createObjectURL(await response.blob());const link=document.createElement('a');link.href=url;link.download=item.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){setError(String(e))}}
  return <section className="card mt"><h2>Private evidence attachments</h2><p className="tiny muted">PNG, JPEG, or PDF up to 2 MB. Files are available only to this pharmacy.</p><label className="field">Add evidence file<input type="file" accept="image/png,image/jpeg,application/pdf" disabled={busy} onChange={e=>{const file=e.target.files?.[0];if(file)void upload(file);e.target.value=''}}/></label>{error&&<div className="notice error" role="alert">{error}</div>}{items.map(item=><div className="row" key={item.id}><span>{item.filename} · {Math.ceil(item.size/1024)} KB</span><button className="secondary" onClick={()=>download(item)}>Download</button></div>)}{items.length===0&&<p className="muted">No evidence files attached.</p>}</section>;
}
