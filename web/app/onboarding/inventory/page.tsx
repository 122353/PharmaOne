'use client';
import {useState} from 'react';
import Link from 'next/link';
import Papa from 'papaparse';
import AppShell from '@/components/AppShell';
import {api} from '@/lib/api';

const columns=['medicine_name','manufacturer','batch_number','strength','expiry_date','quantity'] as const;
type Column=typeof columns[number];
type ImportResult={imported:number;duplicates:number;rejected:number;incomplete:number;errors:{row:number;message:string}[]};

export default function Page(){
  const [file,setFile]=useState<File|null>(null);
  const [headers,setHeaders]=useState<string[]>([]);
  const [rows,setRows]=useState<Record<string,string>[]>([]);
  const [mapping,setMapping]=useState<Record<Column,string>>({medicine_name:'medicine_name',manufacturer:'manufacturer',batch_number:'batch_number',strength:'strength',expiry_date:'expiry_date',quantity:'quantity'});
  const [result,setResult]=useState<ImportResult|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  async function chosen(selected:File|null){
    setFile(selected);setResult(null);setRows([]);setHeaders([]);setError('');
    if(!selected)return;
    if(selected.size>2*1024*1024||!selected.name.toLowerCase().endsWith('.csv')){setError('Choose a CSV up to 2 MB.');return;}
    const text=await selected.text();
    const parsed=Papa.parse<Record<string,string>>(text,{header:true,skipEmptyLines:true});
    if(parsed.errors.length){setError('CSV parsing failed at row '+(Number(parsed.errors[0].row??0)+1)+': '+parsed.errors[0].message);return;}
    if(!parsed.meta.fields?.length){setError('The CSV has no header row.');return;}
    setHeaders(parsed.meta.fields);setRows(parsed.data);
    setMapping(Object.fromEntries(columns.map(c=>[c,parsed.meta.fields!.find(h=>h.toLowerCase().trim()===c)||''])) as Record<Column,string>);
  }
  async function upload(){
    if(!file)return;
    if(!mapping.medicine_name||!mapping.quantity){setError('Map medicine name and quantity before importing.');return;}
    const used=Object.values(mapping).filter(Boolean);
    if(new Set(used).size!==used.length){setError('Each source column can map to only one field.');return;}
    setBusy(true);setError('');
    try{
      const normalized=rows.map(row=>Object.fromEntries(columns.map(c=>[c,mapping[c]?row[mapping[c]]||'':''])));
      const data=Papa.unparse({fields:[...columns],data:normalized.map(row=>columns.map(c=>row[c]))},{escapeFormulae:true});
      const form=new FormData();form.append('file',new Blob([data],{type:'text/csv'}),'mapped-inventory.csv');
      setResult(await api('/api/inventory/import',{method:'POST',body:form}));
    }catch(err){setError(String(err));}finally{setBusy(false);}
  }
  const template='data:text/csv;charset=utf-8,'+encodeURIComponent(columns.join(',')+'\n');
  const errorsCsv=result?Papa.unparse({fields:['row','message'],data:result.errors.map(e=>[e.row,e.message])},{escapeFormulae:true}):'';
  return <AppShell><div className="page-head"><div><span className="page-kicker">Inventory setup</span><h1>Bring your batch records in</h1><p>Import a UTF-8 CSV. Missing identifiers remain in the review queue.</p></div><Link className="secondary" href="/dashboard">View dashboard</Link></div><div className="split"><div className="card"><h2>1 · Select a file</h2><p className="muted">Up to 2 MB and 5,000 rows. Map your columns to the PharmaOne fields.</p><label className="field">CSV file<input type="file" accept=".csv,text/csv" onChange={e=>chosen(e.target.files?.[0]||null)}/></label><a className="text-link" download="pharmaone-inventory-template.csv" href={template}>Download CSV template ↓</a>{rows.length>0&&<><h2 className="mt">2 · Map columns</h2><div className="grid-4">{columns.map(c=><label className="field" key={c}>{c.replaceAll('_',' ')}<select value={mapping[c]} onChange={e=>setMapping({...mapping,[c]:e.target.value})}><option value="">Not in file</option>{headers.map(h=><option key={h} value={h}>{h}</option>)}</select></label>)}</div><h2 className="mt">Preview first 10 rows</h2><div className="table-wrap"><table><thead><tr>{columns.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{rows.slice(0,10).map((row,i)=><tr key={i}>{columns.map(c=><td key={c}>{mapping[c]?row[mapping[c]]||'—':'—'}</td>)}</tr>)}</tbody></table></div><button onClick={upload} disabled={busy} className="primary mt">{busy?'Importing…':'3 · Confirm import'}</button></>}</div><div className="card"><h2>Before you import</h2><p className="muted">We check file size, column names, dates, quantities and spreadsheet formulas. Duplicate rows are skipped. Batch and manufacturer gaps are retained as “Needs verification”.</p><div className="notice">For a demo, use synthetic pharmacy inventory and label it accordingly. Never upload patient records.</div>{error&&<div className="notice error">{error}</div>}{result&&<div className="notice success">Imported {result.imported} rows · {result.duplicates} duplicates · {result.rejected} rejected · {result.incomplete} incomplete.<br/>{result.errors.map(e=><span key={e.row}>Row {e.row}: {e.message}<br/></span>)}{result.errors.length>0&&<a className="text-link" href={'data:text/csv;charset=utf-8,'+encodeURIComponent(errorsCsv)} download="pharmaone-import-errors.csv">Download error CSV ↓</a>}<Link className="text-link" href="/dashboard">Continue to dashboard →</Link></div>}</div></div></AppShell>;
}
