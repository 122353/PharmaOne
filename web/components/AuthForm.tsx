'use client';

import {FormEvent, useRef, useState} from 'react';
import Link from 'next/link';
import {useRouter} from 'next/navigation';
import {supabase, configured} from '@/lib/supabase';
import {Button} from '@/components/ui/button';
import {useLanguage, Language} from '@/lib/language';

type Mode = 'login' | 'signup' | 'forgot';

export function authErrorMessage(error: unknown, language: Language = 'en'): string {
  const value = error instanceof Error ? error.message : String(error || 'Authentication failed');
  const status = typeof error === 'object' && error !== null && 'status' in error ? Number(error.status) : 0;
  if (status === 429 || /(?:email|mail).*rate.limit|too many (?:emails|requests)|over_email_send_rate_limit/i.test(value)) {
    return language === 'hi'
      ? 'ईमेल भेजने की सीमा अस्थायी रूप से पूरी हो गई है। कुछ समय बाद फिर कोशिश करें। यदि आपने पहले पंजीकरण किया है, तो पुष्टि ईमेल देखें या साइन इन करें; बार-बार भेजने से ईमेल जल्दी नहीं आएगा।'
      : 'Email delivery is temporarily rate limited. Wait before trying again. If you already signed up, use the confirmation email you received or sign in; repeated submissions will not speed up delivery.';
  }
  return value;
}

export default function AuthForm({mode}: {mode: Mode}) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [confirm, setConfirm] = useState('');
  const [terms, setTerms] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const router = useRouter();
  const {language, setLanguage} = useLanguage();
  const t = (en: string, hi: string) => language === 'hi' ? hi : en;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending.current) return;
    setMessage('');
    setError(false);
    if (!supabase) { setMessage(t('Configure Supabase in web/.env.local first.', 'पहले web/.env.local में Supabase कॉन्फ़िगर करें।')); setError(true); return; }
    if (mode === 'signup' && password !== confirm) { setMessage(t('Passwords do not match.', 'पासवर्ड मेल नहीं खाते।')); setError(true); return; }
    if (mode === 'signup' && !terms) { setMessage(t('Please accept the terms and privacy notice.', 'कृपया नियम और गोपनीयता सूचना स्वीकार करें।')); setError(true); return; }
    pending.current = true;
    setBusy(true);
    try {
      if (mode === 'forgot') {
        const {error: failure} = await supabase.auth.resetPasswordForEmail(email.trim(), {
          redirectTo: new URL('/reset-password', window.location.origin).toString(),
        });
        if (failure) throw failure;
        setMessage(t('If an account exists for this email, a password reset link will arrive. Check your inbox and spam folder before requesting another.', 'यदि इस ईमेल का खाता है, तो पासवर्ड रीसेट लिंक आएगा। दोबारा अनुरोध करने से पहले इनबॉक्स और स्पैम जाँचें।'));
      } else if (mode === 'signup') {
        const {data, error: failure} = await supabase.auth.signUp({
          email: email.trim(), password,
          options: {data: {name: name.trim()}, emailRedirectTo: new URL('/onboarding/pharmacy', window.location.origin).toString()},
        });
        if (failure) throw failure;
        if (data.session) router.replace('/onboarding/pharmacy');
        else setMessage(t('Check your email to confirm your account, then sign in. Do not submit the signup form again while waiting.', 'खाता पुष्टि के लिए ईमेल देखें, फिर साइन इन करें। प्रतीक्षा करते समय पंजीकरण फ़ॉर्म दोबारा न भेजें।'));
      } else {
        const {error: failure} = await supabase.auth.signInWithPassword({email: email.trim(), password});
        if (failure) throw failure;
        router.replace('/dashboard');
      }
    } catch (failure) {
      setError(true);
      setMessage(authErrorMessage(failure, language));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  return <div className="auth-page">
    <div className="auth-art"><Link className="brand" href="/"><span className="brand-icon">✦</span> PharmaOne <small>AI</small></Link><div><span className="overline" style={{color: '#caebdd'}}>{t('A CALMER WAY TO STAY INFORMED', 'जानकारी के साथ बेहतर निर्णय')}</span><h2>{t('Official evidence, connected to the stock you hold.', 'आधिकारिक प्रमाण, आपकी उपलब्ध दवाओं से जुड़े हुए।')}</h2></div><small>{t('Medicine-quality intelligence for pharmacy teams.', 'फार्मेसी टीमों के लिए दवा गुणवत्ता की जानकारी।')}</small></div>
    <div className="auth-form"><form onSubmit={submit} aria-busy={busy}>
      <Link className="brand" href="/"><span className="brand-icon">✦</span> PharmaOne <small>AI</small></Link>
      <label className="field">{t('Interface language', 'इंटरफ़ेस भाषा')}<select aria-label="Interface language" value={language} onChange={event => setLanguage(event.target.value as Language)}><option value="en">English</option><option value="hi">हिन्दी</option></select></label>
      <h1>{mode === 'signup' ? t('Create your workspace', 'अपना कार्यक्षेत्र बनाएँ') : mode === 'login' ? t('Welcome back', 'वापसी पर स्वागत है') : t('Reset your password', 'पासवर्ड रीसेट करें')}</h1>
      <p>{mode === 'signup' ? t('Start with your account, then tell us about your pharmacy.', 'पहले खाता बनाएँ, फिर अपनी फार्मेसी की जानकारी दें।') : mode === 'login' ? t('Sign in to review your pharmacy’s evidence and inventory.', 'अपनी फार्मेसी के प्रमाण और इन्वेंटरी देखने के लिए साइन इन करें।') : t('We’ll email you a reset link.', 'हम आपको ईमेल से रीसेट लिंक भेजेंगे।')}</p>
      {mode === 'signup' && <label className="field">{t('Your name', 'आपका नाम')}<input required value={name} onChange={event => setName(event.target.value)} autoComplete="name"/></label>}
      <label className="field">{t('Work email', 'कार्य ईमेल')}<input required type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email"/></label>
      {mode !== 'forgot' && <label className="field">{t('Password', 'पासवर्ड')}<input required minLength={8} type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'}/></label>}
      {mode === 'signup' && <><label className="field">{t('Confirm password', 'पासवर्ड की पुष्टि करें')}<input required minLength={8} type="password" value={confirm} onChange={event => setConfirm(event.target.value)} autoComplete="new-password"/></label><label className="tiny"><input type="checkbox" checked={terms} onChange={event => setTerms(event.target.checked)}/> {t('I agree to the', 'मैं')} <Link href="/terms">{t('terms', 'नियमों')}</Link> {t('and', 'और')} <Link href="/privacy">{t('privacy notice', 'गोपनीयता सूचना')}</Link> {t('and understand this is decision support.', 'से सहमत हूँ और समझता हूँ कि यह निर्णय में सहायता के लिए है।')}</label></>}
      {message && <div className={'notice' + (error ? ' error' : '')} role={error ? 'alert' : 'status'}>{message}</div>}
      <Button disabled={busy || !configured} className="w-full mt-3" type="submit">{busy ? t('Please wait…', 'कृपया प्रतीक्षा करें…') : mode === 'signup' ? t('Create account', 'खाता बनाएँ') : mode === 'login' ? t('Sign in', 'साइन इन करें') : t('Send reset link', 'रीसेट लिंक भेजें')}</Button>
      {mode === 'login' ? <><Link className="text-link" href="/forgot-password">{t('Forgot password?', 'पासवर्ड भूल गए?')}</Link><p>{t('New here?', 'नए हैं?')} <Link className="text-link" href="/signup">{t('Create an account', 'खाता बनाएँ')}</Link></p></> : <p><Link className="text-link" href="/login">{t('Back to sign in', 'साइन इन पर लौटें')}</Link></p>}
    </form></div>
  </div>;
}
