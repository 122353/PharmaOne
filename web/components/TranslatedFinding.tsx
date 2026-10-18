'use client';
import {useState} from 'react';
import {api,Alert} from '@/lib/api';
import {useLanguage} from '@/lib/language';

export default function TranslatedFinding({alert}:{alert:Alert}){
  const {language}=useLanguage(),[translation,setTranslation]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  if(language!=='hi'||!alert.quality_issue)return null;
  async function run(){setBusy(true);setError('');try{const result=await api<{translated:string}>('/api/alerts/'+alert.fingerprint+'/translate',{method:'POST',body:JSON.stringify({language:'hi'})});setTranslation(result.translated)}catch(e){setError(String(e))}finally{setBusy(false)}}
  return <div className="notice"><button className="secondary" onClick={run} disabled={busy}>{busy?'अनुवाद हो रहा है…':'Sarvam से निष्कर्ष का अनुवाद करें'}</button>{translation&&<p><b>अनुवादित व्याख्या:</b> {translation}<br/><small>मूल पाठ: {alert.quality_issue} · बैच {alert.batch_number} अपरिवर्तित है।</small></p>}{error&&<p role="alert">{error}</p>}</div>;
}
