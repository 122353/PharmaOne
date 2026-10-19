'use client';

import Link from 'next/link';
import {useEffect, useRef, useState} from 'react';
import {useParams, useSearchParams} from 'next/navigation';
import AppShell from '@/components/AppShell';
import TranslatedFinding from '@/components/TranslatedFinding';
import EvidenceAttachments from '@/components/EvidenceAttachments';
import {api, Alert, Match} from '@/lib/api';

function strengthLabel(values: {value_mg: string; basis: string}[]) {
  if (!values.length) return 'Not supplied';
  return values.map(value => {
    const mass = `${value.value_mg} mg`;
    if (value.basis === 'per_ml') return `${mass}/mL`;
    if (value.basis === 'dose') return mass;
    return `${mass}/${value.basis.replace('per_', '')}`;
  }).join(' + ');
}

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
  const requestedMatch = matches.find(match => match.id === search.get('match'));
  const selected = requestedMatch?.alert.fingerprint === id
    ? requestedMatch
    : matches.find(match => match.alert.fingerprint === id);
  const investigation = investigations.find(item => item.match_id === selected?.id);

  useEffect(() => {
    const alertPath = '/api/alerts/' + encodeURIComponent(id);
    api<Alert>(alertPath).then(setAlert).catch(error => setMessage(String(error)));
    api<Version[]>(alertPath + '/versions').then(setVersions).catch(() => {});
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
        <div className="comparison">
          <div><small>Product identity · {selected.explanation.product.aligned ? 'aligned' : 'verify'}</small>Your stock: {selected.explanation.product.inventory || 'missing'}<br/>Source: {selected.explanation.product.source || 'missing'}</div>
          <div><small>Batch · {selected.explanation.batch.exact ? 'exact' : 'verify'}</small>Your stock: {selected.explanation.batch.inventory || 'missing'}<br/>Source: {selected.explanation.batch.source || 'missing'}</div>
          <div><small>Manufacturer · {selected.explanation.manufacturer.aligned ? 'aligned' : 'verify'}</small>Your stock: {selected.explanation.manufacturer.inventory || 'missing'}<br/>Source: {selected.explanation.manufacturer.source || 'missing'}</div>
          {selected.explanation.strength && <div><small>Strength · {selected.explanation.strength.aligned === true ? 'aligned' : 'verify'}</small>
            Your stock: {selected.explanation.strength.inventory_conflict
              ? `Name: ${strengthLabel(selected.explanation.strength.inventory_name)}; field: ${strengthLabel(selected.explanation.strength.inventory_field)}`
              : strengthLabel(selected.explanation.strength.inventory)}<br/>
            Source: {strengthLabel(selected.explanation.strength.source)}
          </div>}
          <div><small>Formulation / release · {selected.explanation.product.form_aligned === false || selected.explanation.product.release_aligned === false ? 'conflict' : selected.explanation.product.form_aligned === null || selected.explanation.product.release_aligned === null ? 'verify' : 'aligned'}</small>
            Your stock: {[...(selected.explanation.product.inventory_form || []), ...(selected.explanation.product.inventory_release || [])].join(', ') || 'not stated'}<br/>
            Source: {[...(selected.explanation.product.source_form || []), ...(selected.explanation.product.source_release || [])].join(', ') || 'not stated'}
          </div>
        </div>
        {selected.explanation.strength?.inventory_conflict && <div className="notice error">The medicine name and separate inventory strength disagree. Verify the package and inventory record with a pharmacist.</div>}
        {selected.explanation.strength?.aligned === false && <div className="notice error">Inventory and regulatory strengths differ. This requires pharmacist verification.</div>}
        {!selected.explanation.manufacturer.aligned && <div className="notice">Manufacturer identity is missing or differs. Confirm the manufacturer from the physical package.</div>}
        {selected.explanation.pharma_match?.product_similarity !== undefined && <p className="tiny muted">PharmaMatch v{selected.explanation.pharma_match.version} advisory product similarity: {Math.round(selected.explanation.pharma_match.product_similarity*100)}%. This score does not determine match status.</p>}
        {selected.explanation.semantic_match?.candidate_retrieved && <p className="tiny muted">MiniLM surfaced this naming candidate for pharmacist verification. Semantic similarity cannot confirm a match.</p>}
        <div className="notice">{selected.status === 'potential_match' ? 'Product, batch, manufacturer and available strength/formulation evidence align under conservative rules. Pharmacist review of the official source and physical stock is still required.' : 'One or more identifiers are missing or conflict. Verify the official evidence and physical package before deciding whether this record applies.'}</div>
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
