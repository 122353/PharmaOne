'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import AppShell from '@/components/AppShell';
import {api} from '@/lib/api';

type Change={id:string;kind:'added'|'updated';alert_id:string;product_name:string;batch_number:string;quality_issue:string;source_url:string;observed_at:string;own_inventory_impact:boolean};
export default function Page(){
  const [items,setItems]=useState<Change[]>([]),[error,setError]=useState(''),[loaded,setLoaded]=useState(false);
  useEffect(()=>{api<Change[]>('/api/regulatory/changes').then(setItems).catch(e=>setError(String(e))).finally(()=>setLoaded(true))},[]);
  return <AppShell><div className="page-head"><div><span className="page-kicker">Meaningful source revisions</span><h1>Regulatory Change History</h1><p>New records and changed regulatory fields. Page layout changes are ignored.</p></div><Link className="secondary" href="/alerts">All alerts</Link></div>{error&&<div className="notice error" role="alert">{error}</div>}{!loaded?<div className="card empty">Loading change history…</div>:!error&&items.length===0?<div className="card empty">No recorded source changes yet.</div>:items.length>0?<div className="table-wrap"><table><thead><tr><th>Change</th><th>Medicine</th><th>Batch</th><th>Finding</th><th>Observed</th><th>Your inventory</th><th>Evidence</th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td><span className="badge">{item.kind}</span></td><td><Link href={'/alerts/'+item.alert_id}>{item.product_name}</Link></td><td>{item.batch_number}</td><td>{item.quality_issue}</td><td>{new Date(item.observed_at).toLocaleString()}</td><td>{item.own_inventory_impact?'Potential candidate':'No identified candidate'}</td><td><a href={item.source_url} target="_blank" rel="noreferrer">CDSCO ↗</a></td></tr>)}</tbody></table></div>:null}<div className="notice">Source extraction changes are candidates for review. Confirm the official CDSCO entry before taking action.</div></AppShell>;
}
