'use client';

import Link from 'next/link';
import {useEffect, useRef, useState} from 'react';
import {useParams, useSearchParams} from 'next/navigation';
import AppShell from '@/components/AppShell';
import TranslatedFinding from '@/components/TranslatedFinding';
import EvidenceAttachments from '@/components/EvidenceAttachments';
import {api, Alert, Match} from '@/lib/api';

type Investigation = {
  id: string; match_id: string; status: string; physical_status: string; simulated_hold: boolean;
  note: string; updated_at: string; record_reviewed: boolean; physical_verified: boolean;
};
type Event = {id: string; action: string; created_at: string; detail: {note?: string}};
type Version = {id: string; quality_issue: string; observed_at: string};

export default function Page() {
  const params = useParams();
  const search = useSearchParams();
  const id = String(params.id);
  const [alert, setAlert] = useState<Alert | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [matches, setMatches] = useState<Match[]>([]);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [note, setNote] = useState('');
  const [recordReviewed, setRecordReviewed] = useState(false);
  const [physicalVerified, setPhysicalVerified] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const selected = matches.find(match => match.id === search.get('match')) || matches.find(match => match.alert.fingerprint === id);
  const investigation = investigations.find(item => item.match_id === selected?.id);

  useEffect(() => {
    api<Alert>('/api/alerts/' + id).then(setAlert).catch(error => setMessage(String(error)));
    api<Version[]>('/api/alerts/' + id + '/versions').then(setVersions).catch(() => {});
    api<Match[]>('/api/matches').then(setMatches).catch(() => {});
    api<Investigation[]>('/api/investigations').then(setInvestigations).catch(() => {});
  }, [id]);

  useEffect(() => {
    if (!investigation) { setNote(''); setRecordReviewed(false); setPhysicalVerified(false); setEvents([]); return; }
    setNote(investigation.note);
    setRecordReviewed(investigation.record_reviewed);
    setPhysicalVerified(investigation.physical_verified);
    api<Event[]>('/api/investigations/' + investigation.id + '/events').then(setEvents).catch(() => {});
  }, [selected?.id, investigation?.id]);

  async function act(status: string) {
    if (!selected || inFlight.current) return;
    if (status === 'simulated_hold' && !window.confirm('Record a simulated hold? This does not restrict actual stock or dispensing.')) return;
    inFlight.current = true;
    setBusy(true);
    setMessage('');
    try {
      const saved = await api<Investigation>('/api/investigations', {
        method: 'POST', body: JSON.stringify({match_id: selected.id, status, note, record_reviewed: recordReviewed,
          physical_verified: status === 'physical_verification_pending' ? false : physicalVerified}),
      });
      setInvestigations(await api<Investigation[]>('/api/investigations'));
      setEvents(await api<Event[]>('/api/investigations/' + saved.id + '/events'));
      setNote(saved.note);
      setRecordReviewed(saved.record_reviewed);
      setPhysicalVerified(saved.physical_verified);
      setMessage('Review decision saved.');
    } catch (error) {
      setMessage(String(error));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return <AppShell>
    <div className="page-head"><div><span className="page-kicker">CDSCO evidence / Investigation</span><h1>{alert?.product_name || 'Loading record…'}</h1><p>NSQ record · {alert?.reporting_period || '—'} · retrieved {alert ? new Date(alert.retrieved_at).toLocaleString() : '—'}</p></div>{alert && <a className="secondary" href={alert.source_url} target="_blank" rel="noreferrer">Open official source ↗</a>}</div>
    {message && <div className="notice" role="status">{message}</div>}
    {alert && <div className="split"><div className="card">
      <span className="badge">NSQ · Not automatically a recall</span><h2 className="mt">Official record</h2>
      <div className="comparison"><div><small>Product</small>{alert.product_name}</div><div><small>Batch number</small>{alert.batch_number}</div><div><small>Manufacturer</small>{alert.manufacturer || 'Not provided'}</div><div><small>Reporting period</small>{alert.reporting_period}</div><div><small>Reported quality result</small>{alert.quality_issue || 'See official source'}</div><div><small>Reporting source</small>{alert.reporting_source || 'See official source'}</div></div>
      {alert.pharma_classify && <p className="tiny muted">PharmaClassify v{alert.pharma_classify.version} advisory category: {alert.pharma_classify.category.replaceAll('_', ' ')}. Trained on synthetic examples; verify the official finding.</p>}
      <TranslatedFinding alert={alert}/><p className="tiny muted">Source: CDSCO public NSQ database. The source link opens the database; filter to {alert.reporting_period} and locate this batch. No direct record URL was supplied by the source.</p>
    </div><div className="card"><h2>Your inventory comparison</h2>
      {selected ? <><p><b>{selected.inventory.medicine_name}</b><br/><span className="badge">{selected.status.replaceAll('_', ' ')}</span></p>
        <div className="comparison">{(['product','batch','manufacturer'] as const).map(key => {const value=selected.explanation[key];return <div key={key}><small>{key} · {value.exact || value.aligned ? 'aligned' : 'verify'}</small>Your stock: {value.inventory || 'missing'}<br/>Source: {value.source || 'missing'}</div>})}</div>
        {selected.explanation.pharma_match && <p className="tiny muted">PharmaMatch v{selected.explanation.pharma_match.version} advisory product similarity: {Math.round(selected.explanation.pharma_match.product_similarity*100)}%. The batch and manufacturer checks above determine review status.</p>}
        <div className="notice">{selected.status === 'potential_match' ? 'Product, batch and manufacturer align under conservative normalization. Confirm against the source and physical stock.' : 'An identifier is missing or conflicts. Verify before deciding whether this record applies.'}</div>
        <label className="field">Pharmacist note<textarea value={note} onChange={event => setNote(event.target.value)} placeholder="Record what you checked"/></label>
        <div className="verification-checklist"><label><input type="checkbox" checked={recordReviewed} onChange={event => setRecordReviewed(event.target.checked)}/> Official record reviewed</label><label><input type="checkbox" checked={physicalVerified} onChange={event => setPhysicalVerified(event.target.checked)}/> Physical package and batch verified</label></div>
        <div style={{display: 'flex', gap: 8, flexWrap: 'wrap'}}>
          <button className="secondary" disabled={busy} onClick={() => act('under_investigation')}>Start investigation</button>
          <button className="secondary" disabled={busy} onClick={() => act('physical_verification_pending')}>Physical check pending</button>
          <button className="primary" disabled={busy} onClick={() => act('reviewed')}>Mark reviewed</button>
          <button className="secondary" disabled={busy || Boolean(investigation?.simulated_hold)} onClick={() => act('simulated_hold')}>{investigation?.simulated_hold ? 'Simulated hold recorded' : 'Simulate hold'}</button>
          <button className="secondary" disabled={busy} onClick={() => act('closed')}>Close</button>
          <button className="secondary" disabled={busy} onClick={() => act('open')}>Reopen</button>
        </div><p className="tiny muted">Simulation only — no real inventory restriction.</p>
      </> : <p className="muted">No inventory-specific candidate for this record in your pharmacy. This does not establish safety.</p>}
    </div></div>}
    {versions.length > 1 && <div className="card mt"><h2>Observed source revisions</h2><p className="muted tiny">A changed extraction was observed on these checks. Verify differences on CDSCO before acting.</p>{versions.map(version => <div className="row" key={version.id}><span>{new Date(version.observed_at).toLocaleString()}</span><span>{version.quality_issue || 'See source'}</span></div>)}</div>}
    {investigation && <div className="card mt"><h2>Investigation activity</h2><p>Review: <span className="badge">{investigation.status.replaceAll('_', ' ')}</span> · Physical verification: <span className="badge">{investigation.physical_status.replaceAll('_', ' ')}</span> · Hold: <span className="badge">{investigation.simulated_hold ? 'simulated' : 'none'}</span></p><div className="timeline">{events.map(event => <p key={event.id}><b>{event.action.replaceAll('_', ' ')}</b> · {new Date(event.created_at).toLocaleString()}<br/>{event.detail.note}</p>)}</div></div>}
    {investigation && <EvidenceAttachments recordId={investigation.id}/>}
    <Link className="secondary mt" href={'/contextos?alert=' + id}>Explain This Alert with ContextOS</Link>
  </AppShell>;
}
