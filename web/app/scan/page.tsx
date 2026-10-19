'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import AppShell from '@/components/AppShell';
import {api} from '@/lib/api';
import {useLanguage} from '@/lib/language';
import {decodeLabel,type ScanFields} from '@/lib/scan';
import {recognizePackaging} from '@/lib/browser-ocr';

type Fields=ScanFields;
type ScanResult={matches:{status:string;explanation:{pharma_match?:{product_similarity:number;version:string}};alert:{fingerprint:string;product_name:string;manufacturer:string;batch_number:string;quality_issue:string;source_url:string;pharma_classify?:{category:string;version:string}}}[];note:string};
type SarvamOCR={fields:Fields&{original_text?:string};status:string;requires_confirmation:boolean};
const blank:Fields={medicine_name:'',manufacturer:'',batch_number:'',strength:'',manufacturing_date:'',expiry_date:''};
function Scanner(){
  const {language}=useLanguage(),video=useRef<HTMLVideoElement>(null),controls=useRef<{stop:()=>void}|null>(null),scanRequest=useRef(0);
  const t=(en:string,hi:string)=>language==='hi'?hi:en;
  const [scanning,setScanning]=useState(false),[decoded,setDecoded]=useState(''),[fields,setFields]=useState<Fields>(blank),[original,setOriginal]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[result,setResult]=useState<ScanResult|null>(null);
  const [ocrProgress,setOcrProgress]=useState('');
  useEffect(()=>()=>{scanRequest.current++;controls.current?.stop()},[]);
  async function start(){
    const request=++scanRequest.current;
    setError('');setScanning(true);
    try{
      const {BrowserMultiFormatReader}=await import('@zxing/browser');
      const reader=new BrowserMultiFormatReader();
      if(!video.current){setScanning(false);return}
      const next=await reader.decodeFromVideoDevice(undefined,video.current,(code)=>{
        if(code&&request===scanRequest.current){
          const value=code.getText();setDecoded(value);setFields(current=>({...current,...decodeLabel(value)}));stop();
        }
      });
      if(request===scanRequest.current)controls.current=next;
      else next.stop();
    }catch{if(request===scanRequest.current){setScanning(false);setError(t('Camera unavailable. Upload a packaging image or enter the identifiers manually.','कैमरा उपलब्ध नहीं है। पैकेजिंग की तस्वीर अपलोड करें या विवरण स्वयं दर्ज करें।'))}}
  }
  function stop(){scanRequest.current++;controls.current?.stop();controls.current=null;setScanning(false)}
  async function extract(file:File){
    if(busy)return;
    setBusy(true);setError('');setResult(null);setOriginal('');setFields(blank);
    setOcrProgress(t('Reading package with Sarvam AI…','Sarvam AI से पैकेज पढ़ा जा रहा है…'));
    try{
      const body=new FormData();body.append('file',file);
      const response=await api<SarvamOCR>('/api/scan/ocr',{method:'POST',body});
      const extracted=response.fields||blank;
      setFields({...blank,...extracted});
      setOriginal(extracted.original_text||'');
      if(!extracted.medicine_name&&!extracted.batch_number)throw new Error('Sarvam OCR returned no usable identifiers');
    }catch{
      setOcrProgress(t('Sarvam unavailable. Falling back to on-device OCR…','Sarvam उपलब्ध नहीं है। डिवाइस OCR का उपयोग हो रहा है…'));
      try{
        const response=await recognizePackaging(file,setOcrProgress);
        setFields({...blank,...response.fields});setOriginal(response.text);
        if(!response.text)setError(t('No text was detected. Enter the identifiers manually.','कोई पाठ नहीं मिला। विवरण स्वयं दर्ज करें।'));
      }catch(e){setError(e instanceof Error?e.message:t('OCR failed. Enter the identifiers manually.','OCR विफल हुआ। विवरण स्वयं दर्ज करें।'))}
    }finally{setBusy(false);setOcrProgress('')}
  }
  async function capture(){if(!video.current){setError(t('Start the camera first','पहले कैमरा शुरू करें'));return}const canvas=document.createElement('canvas');canvas.width=video.current.videoWidth;canvas.height=video.current.videoHeight;canvas.getContext('2d')?.drawImage(video.current,0,0);canvas.toBlob(blob=>{if(blob)void extract(new File([blob],'capture.png',{type:'image/png'}))},'image/png')}
  async function verify(event:React.FormEvent){event.preventDefault();setBusy(true);setError('');try{setResult(await api<ScanResult>('/api/scan/match',{method:'POST',body:JSON.stringify({...fields,confirmed:true})}))}catch(e){setError(String(e))}finally{setBusy(false)}}
  const labels:Record<keyof Fields,[string,string]>={medicine_name:['Medicine name','दवा का नाम'],manufacturer:['Manufacturer','निर्माता'],batch_number:['Batch number','बैच नंबर'],strength:['Strength','मात्रा'],manufacturing_date:['Manufacturing date','निर्माण तिथि'],expiry_date:['Expiry date','समाप्ति तिथि']};
  return <><div className="page-head"><div><span className="page-kicker">{t('Pharmacist confirmation required','फार्मासिस्ट की पुष्टि आवश्यक')}</span><h1>{t('Scan Medicine','दवा स्कैन करें')}</h1><p>{t('Read a QR, barcode or package image, then confirm every identifier before matching.','QR, बारकोड या पैकेजिंग की तस्वीर से विवरण लें। मिलान से पहले उन्हें जाँचें।')}</p></div></div><div className="split"><section className="card"><h2>{t('Camera and image','कैमरा और तस्वीर')}</h2><p className="tiny muted">{t('Package images are first processed by Sarvam AI document OCR for multilingual extraction. If Sarvam is unavailable, PharmaOne falls back to on-device OCR. Review every extracted value before matching.','पैकेज की तस्वीर पहले बहुभाषी जानकारी निकालने के लिए Sarvam AI OCR को भेजी जाती है। Sarvam उपलब्ध न हो तो PharmaOne डिवाइस OCR का उपयोग करता है। मिलान से पहले हर विवरण जाँचें।')}</p><video ref={video} className="scan-video" muted playsInline aria-label={t('Live camera preview','कैमरा दृश्य')}/><div className="toolbar"><button className="secondary" onClick={scanning?stop:start}>{scanning?t('Stop camera','कैमरा बंद करें'):t('Scan QR / barcode','QR / बारकोड स्कैन करें')}</button><button className="secondary" onClick={capture} disabled={!scanning||busy}>{t('Capture image for OCR','OCR के लिए तस्वीर लें')}</button></div><label className="field">{t('Packaging image (PNG or JPEG, up to 5 MB)','पैकेजिंग की तस्वीर (PNG या JPEG, अधिकतम 5 MB)')}<input type="file" accept="image/png,image/jpeg" disabled={busy} onChange={event=>{const file=event.target.files?.[0];if(file)void extract(file)}}/></label>{ocrProgress&&<p className="tiny" role="status">{ocrProgress}</p>}{decoded&&<div className="notice"><b>{t('Decoded symbol (original)','पढ़ा गया कोड (मूल)')}</b><p className="break-all">{decoded}</p><small>{t('A barcode may contain only a product identifier. Missing batch data stays blank.','बारकोड में केवल उत्पाद की पहचान हो सकती है। बैच की जानकारी न हो तो खाली रहेगी।')}</small></div>}{original&&<div className="notice"><b>{t('Original extracted text','मूल निकाला गया पाठ')}</b><p style={{whiteSpace:'pre-wrap'}}>{original}</p></div>}</section><section className="card"><h2>{t('Confirm identifiers','पहचान विवरण की पुष्टि करें')}</h2><form onSubmit={verify}>{(Object.keys(blank) as (keyof Fields)[]).map(key=><label className="field" key={key}>{labels[key][language==='hi'?1:0]}<input value={fields[key]} maxLength={255} required={key==='medicine_name'} onChange={event=>setFields({...fields,[key]:event.target.value})}/></label>)}<button className="primary" disabled={busy}>{busy?t('Processing…','प्रक्रिया चल रही है…'):t('Confirm and match CDSCO records','CDSCO रिकॉर्ड से मिलान करें')}</button></form></section></div>{error&&<div className="notice error" role="alert">{error}</div>}{result&&<section className="card mt"><h2>{t('Potential quality alerts','संभावित गुणवत्ता अलर्ट')}</h2>{result.matches.length?result.matches.map(match=><div className="row" key={match.alert.fingerprint}><div><h3>{match.alert.product_name} · {match.alert.batch_number}</h3><p>{language==='hi'?(match.status==='potential_match'?'संभावित मेल':'सत्यापन आवश्यक'):match.status.replaceAll('_',' ')} · {match.alert.quality_issue}</p><p className="tiny muted">PharmaMatch advisory similarity: {Math.round((match.explanation.pharma_match?.product_similarity||0)*100)}% · PharmaClassify advisory category: {match.alert.pharma_classify?.category.replaceAll('_',' ')||'unclassified'}</p><a href={match.alert.source_url} target="_blank" rel="noreferrer">{t('Official CDSCO source ↗','आधिकारिक CDSCO स्रोत ↗')}</a></div><Link className="secondary" href={'/alerts/'+match.alert.fingerprint}>{t('Review alert','अलर्ट देखें')}</Link></div>):<p>{t('No identified match in the currently stored CDSCO records. This is not proof of product safety.','वर्तमान CDSCO रिकॉर्ड में कोई पहचाना गया मेल नहीं है। इससे उत्पाद सुरक्षित सिद्ध नहीं होता।')}</p>}<p className="tiny muted">{language==='hi'?'संभावित मेल के लिए भौतिक फार्मासिस्ट सत्यापन आवश्यक है। इन्वेंटरी या होल्ड में कोई बदलाव नहीं किया गया है।':result.note}</p></section>}</>;
}
export default function Page(){return <AppShell><Scanner/></AppShell>}
