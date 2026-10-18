'use client';
import Link from 'next/link';
import {usePathname,useRouter} from 'next/navigation';
import {LayoutDashboard,Package,ShieldAlert,ClipboardCheck,Settings,LogOut,Menu,ScanLine,Network,MessageCircle} from 'lucide-react';
import {useState} from 'react';
import AuthGate from './AuthGate';
import {supabase} from '@/lib/supabase';
import {navText,useLanguage} from '@/lib/language';

const links=[['/dashboard',LayoutDashboard],['/inventory',Package],['/scan',ScanLine],['/alerts',ShieldAlert],['/investigations',ClipboardCheck],['/suppliers',Network],['/contextos',MessageCircle],['/settings',Settings]] as const;
function Workspace({children}:{children:React.ReactNode}){
  const path=usePathname(),router=useRouter(),[open,setOpen]=useState(false),{language,setLanguage}=useLanguage();
  const t=navText[language];
  return <AuthGate><div className="app-layout"><aside className={'sidebar '+(open?'shown':'')}><Link className="brand" href="/dashboard"><span className="brand-icon">✦</span> PharmaOne <small>AI</small></Link><div className="sidebar-caption">WORKSPACE</div><nav aria-label="Product navigation">{links.map(([href,Icon],index)=><Link onClick={()=>setOpen(false)} className={path.startsWith(href)?'active':''} href={href} key={href}><Icon size={18}/>{t[index]}</Link>)}</nav><div className="sidebar-bottom"><p>From Government Alerts<br/>to Pharmacy Action.</p><button onClick={async()=>{await supabase?.auth.signOut();router.push('/');}}><LogOut size={17}/>{t[9]}</button></div></aside><div className="app-main"><header className="app-header"><button className="mobile-menu" aria-label="Open menu" onClick={()=>setOpen(!open)}><Menu/></button><span>{t[8]}</span><div className="header-actions"><label htmlFor="workspace-language" className="sr-only">Interface language</label><select id="workspace-language" aria-label="Interface language" value={language} onChange={event=>setLanguage(event.target.value as 'en'|'hi')}><option value="en">English</option><option value="hi">हिन्दी</option></select><span className="app-header-right">Official-source evidence · Human review</span></div></header><main className="app-content">{children}</main><Link className="contextos-fab" href="/contextos"><MessageCircle size={18}/>{language==='hi'?'ContextOS से पूछें':'Ask ContextOS'}</Link></div></div></AuthGate>;
}
export default function AppShell({children}:{children:React.ReactNode}){return <Workspace>{children}</Workspace>}
