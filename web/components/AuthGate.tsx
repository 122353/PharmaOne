'use client';
import {useEffect,useState} from 'react';
import {useRouter} from 'next/navigation';
import {supabase,configured} from '@/lib/supabase';

export default function AuthGate({children}:{children:React.ReactNode}) {
  const [ready,setReady]=useState(false); const router=useRouter();
  useEffect(()=>{
    if(!configured) return;
    let active=true;
    const {data:{subscription}}=supabase!.auth.onAuthStateChange((event,session)=>{
      if(!active) return;
      if(event==='SIGNED_OUT'||(event==='INITIAL_SESSION'&&!session)){
        setReady(false);
        router.replace('/login');
      }else if(session){setReady(true)}
    });
    supabase!.auth.getSession().then(({data})=>{
      if(!active) return;
      if(data.session) setReady(true);
      else {setReady(false);router.replace('/login')}
    }).catch(()=>{if(active){setReady(false);router.replace('/login')}});
    return ()=>{active=false;subscription.unsubscribe()};
  },[router]);
  if(!configured) return <div className="state">Supabase is not configured. Add your project URL and anon key to <code>web/.env.local</code>.</div>;
  return ready ? <>{children}</> : <div className="state">Checking your session…</div>;
}
