'use client';
import {useEffect,useState} from 'react';
import {useRouter} from 'next/navigation';
import {supabase,configured} from '@/lib/supabase';

export default function AuthGate({children}:{children:React.ReactNode}) {
  const [ready,setReady]=useState(false); const router=useRouter();
  useEffect(()=>{ if(!configured){setReady(true);return;} supabase!.auth.getSession().then(({data})=>{ if(!data.session) router.replace('/login'); else setReady(true); }); },[router]);
  if(!configured) return <div className="state">Supabase is not configured. Add your project URL and anon key to <code>web/.env.local</code>.</div>;
  return ready ? <>{children}</> : <div className="state">Checking your session…</div>;
}
