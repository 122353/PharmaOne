'use client';
import {useState} from 'react';
import {api,Alert} from '@/lib/api';

const languages=[
  ['hi','Hindi'],['bn','Bengali'],['ta','Tamil'],['te','Telugu'],['mr','Marathi'],
  ['gu','Gujarati'],['kn','Kannada'],['ml','Malayalam'],['pa','Punjabi'],['od','Odia'],
  ['as','Assamese'],['ur','Urdu'],['ne','Nepali'],['sa','Sanskrit'],['kok','Konkani'],
  ['ks','Kashmiri'],['mai','Maithili'],['mni','Manipuri'],['brx','Bodo'],['doi','Dogri'],
  ['sat','Santali'],['sd','Sindhi']
] as const;

export default function TranslatedFinding({alert}:{alert:Alert}){
  const [target,setTarget]=useState('hi'),[translation,setTranslation]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  if(!alert.quality_issue)return null;
  async function run(){
    setBusy(true);setError('');setTranslation('');
    try{
      const result=await api<{translated:string}>('/api/alerts/'+alert.fingerprint+'/translate',{
        method:'POST',body:JSON.stringify({language:target})
      });
      setTranslation(result.translated);
    }catch(e){setError(String(e))}finally{setBusy(false)}
  }
  return <div className="notice">
    <div className="toolbar">
      <label className="field" style={{margin:0,minWidth:180}}>Translate finding
        <select value={target} onChange={e=>setTarget(e.target.value)}>
          {languages.map(([code,name])=><option key={code} value={code}>{name}</option>)}
        </select>
      </label>
      <button className="secondary" onClick={run} disabled={busy}>{busy?'Translating…':'Translate with Sarvam AI'}</button>
    </div>
    {translation&&<p><b>Translated finding:</b> {translation}<br/><small>Original: {alert.quality_issue} · batch {alert.batch_number} is preserved.</small></p>}
    {error&&<p role="alert">{error}</p>}
  </div>;
}
