'use client';
import {useEffect,useState} from 'react';import Link from 'next/link';import AppShell from '@/components/AppShell';import {api,Alert,Source} from '@/lib/api';
export default function Page(){
  const [items,setItems]=useState<Alert[]>([]),[source,setSource]=useState<Source|null>(null),[query,setQuery]=useState('');
  const [error,setError]=useState(''),[sourceError,setSourceError]=useState(false),[loaded,setLoaded]=useState(false);
  useEffect(()=>{api<Alert[]>('/api/alerts').then(setItems).catch(e=>setError(String(e))).finally(()=>setLoaded(true));api<Source>('/api/ingestion/status').then(setSource).catch(()=>setSourceError(true))},[]);
  const filtered=items.filter(a=>a.product_name.toLowerCase().includes(query.toLowerCase()));
  const sourceMessage=source?.state==='succeeded'&&source.last_checked
    ?`Last successful source check: ${new Date(source.last_checked).toLocaleString()}. ${source.record_count} records in that run.`
    :source?.state==='unavailable'||source?.state==='failed'
      ?'Source unavailable. Previously retrieved records may be stale.'
      :source?.state==='historical_snapshot'
        ?`Historical snapshot: ${source.snapshot_reporting_period||'reporting period unavailable'}. No live source check is recorded for this import.`
        :sourceError?'Source status unavailable. Check CDSCO before acting.':source===null?'Checking source status…':'No successful central source sync yet. Previously verified records remain visible when available.';
  return <AppShell><div className="page-head"><div><span className="page-kicker">Official-source records</span><h1>Regulatory alerts</h1><p>Retrieved CDSCO NSQ records with source provenance. NSQ does not itself mean recall.</p></div><div className="toolbar"><Link href="/changes" className="secondary">Change history</Link><Link href="/settings" className="secondary">Source settings</Link></div></div><div className="notice">{sourceMessage} <a target="_blank" rel="noreferrer" href="https://cdscoonline.gov.in/CDSCO/viewPublicNSQDrug">Open CDSCO ↗</a></div><div className="toolbar"><input className="search" placeholder="Search product" value={query} onChange={e=>setQuery(e.target.value)}/></div>{error&&<div className="notice error" role="alert">{error}</div>}{!loaded?<div className="card empty">Loading regulatory alerts…</div>:!error&&items.length===0?<div className="card empty">No source-backed records stored yet.</div>:items.length>0&&filtered.length===0?<div className="card empty">No medicines match your search.</div>:filtered.length>0?<div className="table-wrap"><table><thead><tr><th>Product</th><th>Manufacturer</th><th>Batch</th><th>Class</th><th>Period</th><th>Checked</th><th>Source</th></tr></thead><tbody>{filtered.map(a=><tr key={a.fingerprint}><td><Link href={'/alerts/'+a.fingerprint}>{a.product_name}</Link></td><td>{a.manufacturer}</td><td>{a.batch_number}</td><td><span className="badge">NSQ</span></td><td>{a.reporting_period}</td><td>{new Date(a.retrieved_at).toLocaleDateString()}</td><td><a href={a.source_url} target="_blank" rel="noreferrer">CDSCO ↗</a></td></tr>)}</tbody></table></div>:null}</AppShell>
}
