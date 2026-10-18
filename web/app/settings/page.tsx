'use client';
import {useEffect,useState} from 'react';
import AppShell from '@/components/AppShell';
import {api,Source} from '@/lib/api';

type Profile={name:string;contact_name:string;kind:string;city:string;state:string;inventory_format:string;batch_available:boolean;manufacturer_available:boolean};

export default function Page(){
  const [profile,setProfile]=useState<Profile|null>(null);
  const [source,setSource]=useState<Source|null>(null);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  useEffect(()=>{api<Profile>('/api/pharmacies/current').then(setProfile).catch(e=>setMessage(String(e)));api<Source>('/api/ingestion/status').then(setSource).catch(()=>{})},[]);
  async function save(){if(!profile)return;setBusy(true);setMessage('');try{await api('/api/pharmacies/current',{method:'PUT',body:JSON.stringify(profile)});setMessage('Pharmacy profile saved.')}catch(e){setMessage(String(e))}finally{setBusy(false)}}
  return <AppShell><div className="page-head"><div><span className="page-kicker">Workspace / Settings</span><h1>Settings</h1><p>Manage pharmacy context and review the shared CDSCO source status.</p></div></div><div className="split"><div className="card"><h2>Pharmacy context</h2>{profile?<><label className="field">Trading name<input value={profile.name} onChange={e=>setProfile({...profile,name:e.target.value})}/></label><label className="field">City<input value={profile.city} onChange={e=>setProfile({...profile,city:e.target.value})}/></label><label className="field">State<input value={profile.state} onChange={e=>setProfile({...profile,state:e.target.value})}/></label><button className="primary" disabled={busy} onClick={save}>Save profile</button></>:<p className="muted">Create your pharmacy profile in onboarding.</p>}</div><div className="card"><h2>Regulatory data</h2><p className="muted">PharmaOne checks CDSCO centrally. Your pharmacy does not need a TinyFish account or API key.</p><p>Source status: <span className="badge">{source?.state==='succeeded'?'Available':source?.state||'Checking…'}</span></p><p className="muted">{source?.last_checked?`Last successful check: ${new Date(source.last_checked).toLocaleString()}`:'No successful central check recorded yet.'}</p><a className="text-link" href="https://cdscoonline.gov.in/CDSCO/viewPublicNSQDrug" target="_blank" rel="noreferrer">Open official CDSCO database ↗</a><div className="notice mt">Source coverage is limited to selected reporting periods. An NSQ finding is not automatically a recall.</div></div></div>{message&&<div className="notice mt">{message}</div>}</AppShell>;
}
