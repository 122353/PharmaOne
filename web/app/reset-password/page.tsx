'use client';

import {FormEvent, useEffect, useRef, useState} from 'react';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {authErrorMessage} from '@/components/AuthForm';
import {supabase} from '@/lib/supabase';
import {useLanguage} from '@/lib/language';

export default function ResetPasswordPage() {
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const router = useRouter();
  const {language} = useLanguage();
  const t = (en: string, hi: string) => language === 'hi' ? hi : en;

  useEffect(() => {
    if (!supabase) return;
    let active = true;
    const {data: {subscription}} = supabase.auth.onAuthStateChange((event, session) => {
      if (active && (event === 'PASSWORD_RECOVERY' || session)) setReady(true);
    });
    supabase.auth.getSession().then(({data}) => { if (active) setReady(value => value || Boolean(data.session)); }).catch(() => {});
    return () => { active = false; subscription.unsubscribe(); };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending.current || !supabase) return;
    if (password !== confirmation) { setMessage(t('Passwords do not match.', 'पासवर्ड मेल नहीं खाते।')); return; }
    pending.current = true;
    setBusy(true);
    setMessage('');
    try {
      const {error} = await supabase.auth.updateUser({password});
      if (error) throw error;
      await supabase.auth.signOut();
      router.replace('/login?password_reset=success');
    } catch (error) {
      setMessage(authErrorMessage(error, language));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <div className="auth-page"><div className="auth-art"><Link className="brand" href="/">✦ PharmaOne <small>AI</small></Link><h2>{t('Return to your pharmacy workspace.', 'अपने फार्मेसी कार्यक्षेत्र पर लौटें।')}</h2></div><div className="auth-form"><form onSubmit={submit} aria-busy={busy}>
    <h1>{t('Set a new password', 'नया पासवर्ड सेट करें')}</h1>
    {!ready ? <p>{t('This reset link is missing, expired, or still being verified.', 'यह रीसेट लिंक उपलब्ध नहीं है, समाप्त हो चुका है या इसकी जाँच जारी है।')} <Link href="/forgot-password">{t('Request a new reset link', 'नया रीसेट लिंक माँगें')}</Link>.</p> : <>
      <label className="field">{t('New password', 'नया पासवर्ड')}<input required minLength={8} type="password" autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)}/></label>
      <label className="field">{t('Confirm new password', 'नए पासवर्ड की पुष्टि करें')}<input required minLength={8} type="password" autoComplete="new-password" value={confirmation} onChange={event => setConfirmation(event.target.value)}/></label>
      {message && <div className="notice error" role="alert">{message}</div>}
      <button className="primary" disabled={busy} type="submit">{busy ? t('Updating…', 'अपडेट हो रहा है…') : t('Update password', 'पासवर्ड अपडेट करें')}</button>
    </>}
    <p><Link href="/login">{t('Back to sign in', 'साइन इन पर लौटें')}</Link></p>
  </form></div></div>;
}
