'use client';
import Link from 'next/link';
import {usePathname,useRouter} from 'next/navigation';
import {LayoutDashboard,Package,ShieldAlert,ClipboardCheck,Upload,Settings,LogOut,Menu} from 'lucide-react';
import {useState} from 'react';
import AuthGate from './AuthGate';
import {supabase} from '@/lib/supabase';

const links=[['/dashboard','Overview',LayoutDashboard],['/inventory','Inventory',Package],['/alerts','Regulatory alerts',ShieldAlert],['/investigations','Investigations',ClipboardCheck],['/onboarding/inventory','Import / sync',Upload],['/settings','Settings',Settings]] as const;
export default function AppShell({children}:{children:React.ReactNode}) {
  const path=usePathname(); const router=useRouter(); const [open,setOpen]=useState(false);
  return <AuthGate><div className="app-layout"><aside className={'sidebar '+(open?'shown':'')}><Link className="brand" href="/dashboard"><span className="brand-icon">✦</span> PharmaOne <small>AI</small></Link><div className="sidebar-caption">WORKSPACE</div><nav aria-label="Product navigation">{links.map(([href,label,Icon])=><Link onClick={()=>setOpen(false)} className={path.startsWith(href)?'active':''} href={href} key={href}><Icon size={18}/>{label}</Link>)}</nav><div className="sidebar-bottom"><p>From Government Alerts<br/>to Pharmacy Action.</p><button onClick={async()=>{await supabase?.auth.signOut();router.push('/');}}><LogOut size={17}/> Sign out</button></div></aside><div className="app-main"><header className="app-header"><button className="mobile-menu" aria-label="Open menu" onClick={()=>setOpen(!open)}><Menu/></button><span>Pharmacy workspace</span><span className="app-header-right">Official-source evidence · Human review</span></header><main className="app-content">{children}</main></div></div></AuthGate>;
}
