'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import AppShell from '@/components/AppShell';
import {api, Dashboard} from '@/lib/api';
import {useLanguage} from '@/lib/language';

export default function Page() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState('');
  const {language} = useLanguage();
  const t = (en: string, hi: string) => language === 'hi' ? hi : en;
  useEffect(() => { api<Dashboard>('/api/dashboard').then(setData).catch(error => setError(String(error))); }, []);

  return <AppShell>
    <div className="page-head"><div>
      <span className="page-kicker">{t('Pharmacy / Overview', 'फार्मेसी / अवलोकन')}</span>
      <h1>{data?.pharmacy || t('Your pharmacy', 'आपकी फार्मेसी')}</h1>
      <p>{t('Your batch-level review workspace. Evidence is only as current as the last successful source check.', 'बैच स्तर पर समीक्षा का आपका कार्यक्षेत्र। प्रमाण केवल आखिरी सफल स्रोत जाँच तक अद्यतन हैं।')}</p>
    </div><Link className="secondary" href="/onboarding/inventory">{t('Import inventory', 'इन्वेंटरी आयात करें')}</Link></div>
    {error && <div className="notice error" role="alert">{language === 'hi' && /Failed to fetch/i.test(error) ? 'सर्वर से संपर्क नहीं हो पाया।' : error} <Link href="/onboarding/pharmacy">{t('Set up pharmacy →', 'फार्मेसी सेट करें →')}</Link></div>}
    {!data && !error && <div className="state">{t('Loading your workspace…', 'आपका कार्यक्षेत्र लोड हो रहा है…')}</div>}
    {data && <>
      <div className="grid-4">
        <div className="card stat"><small>{t('Inventory batches', 'इन्वेंटरी बैच')}</small><strong>{data.inventory_count}</strong><span>{t('Imported rows', 'आयातित पंक्तियाँ')}</span></div>
        <div className="card stat"><small>{t('Potential matches', 'संभावित मेल')}</small><strong>{data.potential_count}</strong><span>{t('Require human review', 'मानवीय समीक्षा आवश्यक')}</span></div>
        <div className="card stat"><small>{t('Needs verification', 'सत्यापन आवश्यक')}</small><strong>{data.verification_count}</strong><span>{t('Missing or conflicting fields', 'अधूरी या विरोधी जानकारी')}</span></div>
        <div className="card stat"><small>{t('Open investigations', 'खुली जाँच')}</small><strong>{data.open_investigations}</strong><span>{t('Recorded decisions', 'दर्ज निर्णय')}</span></div>
      </div>
      <div className="dashboard-grid">
        <div className="card action-card"><h2>{t('Requires your review', 'आपकी समीक्षा आवश्यक')}</h2>
          {data.review_queue.length === 0 ? <div className="empty">{data.inventory_count === 0
            ? t('Import inventory to begin matching.', 'मिलान शुरू करने के लिए इन्वेंटरी आयात करें।')
            : data.source.state === 'never_synced'
              ? t('No central source check yet. Previously verified records remain visible when available.', 'केंद्रीय स्रोत की जाँच अभी नहीं हुई है। पहले सत्यापित रिकॉर्ड उपलब्ध होने पर दिखेंगे।')
              : t('No open matches from available records. This does not establish that stock is safe.', 'उपलब्ध रिकॉर्ड में कोई खुला मेल नहीं है। इससे स्टॉक सुरक्षित सिद्ध नहीं होता।')}</div>
          : data.review_queue.map(match => <div className="row" key={match.id}><div>
              <span className="badge">{match.status === 'potential_match' ? t('Potential match', 'संभावित मेल') : t('Needs verification', 'सत्यापन आवश्यक')}</span>
              <h3 className="mt">{match.inventory.medicine_name}</h3>
              <p>{t('Batch', 'बैच')} {match.inventory.batch_number || t('missing', 'उपलब्ध नहीं')} · {match.alert.reporting_period} · {match.alert.classification.toUpperCase()}</p>
            </div><Link href={'/alerts/' + match.alert.fingerprint + '?match=' + match.id} className="secondary">{t('Review alert →', 'अलर्ट देखें →')}</Link></div>)}
        </div>
        <div className="card"><h2>{t('Source health', 'स्रोत की स्थिति')}</h2>
          <span className={'badge ' + (data.source.state === 'succeeded' ? 'green' : '')}>{data.source.state === 'succeeded' ? t('Last sync succeeded', 'पिछला सिंक सफल') : data.source.state === 'never_synced' ? t('Not synced', 'सिंक नहीं हुआ') : t('Source unavailable', 'स्रोत उपलब्ध नहीं')}</span>
          <p className="muted">{data.source.last_checked ? t('Last checked ', 'आखिरी जाँच ') + new Date(data.source.last_checked).toLocaleString(language === 'hi' ? 'hi-IN' : undefined) : t('No central source check recorded yet.', 'केंद्रीय स्रोत की जाँच अभी दर्ज नहीं है।')}</p>
          <a className="text-link" href={data.source.source_url} target="_blank" rel="noreferrer">{t('Open CDSCO database ↗', 'CDSCO डेटाबेस खोलें ↗')}</a>
        </div>
        <div className="card"><h2>{t('ContextOS Lite · What to clarify', 'ContextOS Lite · क्या स्पष्ट करें')}</h2>
          {data.clarifications.length ? data.clarifications.map(value => <p key={value} className="notice">{value}</p>) : <p className="muted">{t('No missing identifiers detected in your current import.', 'वर्तमान आयात में कोई पहचान संबंधी जानकारी अधूरी नहीं मिली।')}</p>}
          <Link className="text-link" href="/inventory">{t('Review inventory →', 'इन्वेंटरी देखें →')}</Link>
        </div>
        <div className="card"><h2>{t('Recent official records', 'हाल के आधिकारिक रिकॉर्ड')}</h2>
          {data.recent_alerts.length === 0 ? <p className="muted">{t('No retrieved records yet. We do not display invented alerts.', 'अभी कोई प्राप्त रिकॉर्ड नहीं है। हम काल्पनिक अलर्ट नहीं दिखाते।')}</p> : data.recent_alerts.map(alert => <div className="row" key={alert.fingerprint}><div><h3>{alert.product_name}</h3><p>{alert.reporting_period} · CDSCO NSQ</p></div><Link href={'/alerts/' + alert.fingerprint}>{t('View →', 'देखें →')}</Link></div>)}
        </div>
      </div>
      <div className="notice mt">{t('NSQ is not automatically a recall. A potential match needs pharmacist validation. Simulated holds do not affect dispensing.', 'NSQ अपने आप रिकॉल नहीं है। संभावित मेल के लिए फार्मासिस्ट का सत्यापन आवश्यक है। सिम्युलेटेड होल्ड से दवा वितरण प्रभावित नहीं होता।')}</div>
    </>}
  </AppShell>;
}
