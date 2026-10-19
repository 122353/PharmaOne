'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api, type MonitoringNotification } from '@/lib/api';
import { useLanguage } from '@/lib/language';

type NotificationBellProps = { initialUnreadCount?: number };

export default function NotificationBell({ initialUnreadCount }: NotificationBellProps) {
  const [items, setItems] = useState<MonitoringNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(initialUnreadCount ?? 0);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState<string | null>(null);
  const { language } = useLanguage();
  const t = (en: string, hi: string) => language === 'hi' ? hi : en;

  const loadNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api<MonitoringNotification[]>('/api/notifications');
      setItems(result);
      if (initialUnreadCount === undefined) {
        setUnreadCount(result.filter(item => !item.is_read && item.is_active).length);
      }
      setError('');
    } catch {
      setError(t('Could not load notifications.', 'सूचनाएँ लोड नहीं हो सकीं।'));
    } finally {
      setLoading(false);
    }
  }, [initialUnreadCount, language]);

  useEffect(() => {
    if (initialUnreadCount !== undefined) setUnreadCount(initialUnreadCount);
  }, [initialUnreadCount]);

  async function markRead(id: string) {
    const item = items.find(value => value.id === id);
    if (!item || item.is_read || savingId) return;

    setSavingId(id);
    setError('');
    setItems(previous => previous.map(value => value.id === id ? { ...value, is_read: true } : value));
    setUnreadCount(count => Math.max(0, count - 1));
    try {
      await api(`/api/notifications/${encodeURIComponent(id)}/read`, { method: 'PATCH' });
    } catch {
      setItems(previous => previous.map(value => value.id === id ? { ...value, is_read: false } : value));
      setUnreadCount(count => count + 1);
      setError(t('Could not update notification. Please retry.', 'सूचना अपडेट नहीं हुई। कृपया फिर कोशिश करें।'));
    } finally {
      setSavingId(null);
    }
  }

  return (
    <section className="card notification-card" aria-label={t('Regulatory notifications', 'नियामक सूचनाएँ')}>
      <button
        type="button"
        className="secondary"
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next) void loadNotifications();
        }}
        aria-expanded={open}
        aria-controls="notification-panel"
        aria-label={t(`Regulatory notifications, ${unreadCount} unread`, `नियामक सूचनाएँ, ${unreadCount} अपठित`)}
      >
        <span aria-hidden="true">🔔</span> {t('Notifications', 'सूचनाएँ')} <span className="notification-count" aria-live="polite">{unreadCount}</span>
      </button>

      {open && (
        <div id="notification-panel" className="notification-panel">
          <h2>{t('Regulatory notifications', 'नियामक सूचनाएँ')}</h2>
          {loading && <p className="muted" role="status">{t('Loading notifications…', 'सूचनाएँ लोड हो रही हैं…')}</p>}
          {error && <div className="notice error" role="alert">{error} <button type="button" className="text-link" onClick={() => void loadNotifications()}>{t('Retry', 'फिर कोशिश करें')}</button></div>}
          {!loading && !error && items.length === 0 && (
            <p className="empty">{t('No notifications yet.', 'अभी कोई सूचना नहीं है।')}</p>
          )}

          {items.map(item => (
            <article className="row notification-item" key={item.id}>
              <div className="notification-copy">
                <div className="notification-heading">
                  <strong>{item.status === 'potential_match'
                    ? t('Potential regulatory match', 'संभावित नियामक मेल')
                    : t('Regulatory verification required', 'नियामक सत्यापन आवश्यक')}</strong>
                  {!item.is_read && <span className="badge">{t('New', 'नई')}</span>}
                  {item.is_read && <span className="badge gray">{t('Acknowledged', 'देखी गई')}</span>}
                </div>
                <p>{item.medicine_name || item.message} {item.batch_number && <>· {t('Batch', 'बैच')} {item.batch_number}</>}</p>
                {item.quality_issue && <p>{t('Reported finding', 'रिपोर्ट किया गया निष्कर्ष')}: {item.quality_issue}</p>}
                {item.reporting_period && <small>{t('Source reporting period', 'स्रोत रिपोर्टिंग अवधि')}: {item.reporting_period}</small>}
                <small className="notification-time">{new Date(item.created_at).toLocaleString(language === 'hi' ? 'hi-IN' : 'en-IN')}</small>
              </div>
              <div className="notification-actions">
                <Link href={`/alerts/${encodeURIComponent(item.alert_id)}`} className="secondary">
                  {t('Review', 'समीक्षा')}
                </Link>
                {!item.is_read && (
                  <button
                    type="button"
                    className="secondary"
                    disabled={savingId === item.id}
                    onClick={() => void markRead(item.id)}
                  >
                    {savingId === item.id ? t('Saving…', 'सहेज रहे हैं…') : t('Mark read', 'पढ़ा हुआ')}
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      <p className="muted notification-disclaimer">
        {t(
          'Notifications reflect available regulatory evidence, not confirmed recalls. Pharmacist verification is required.',
          'सूचनाएँ उपलब्ध नियामक प्रमाण पर आधारित हैं, पुष्टि किए गए रिकॉल नहीं। फार्मासिस्ट का सत्यापन आवश्यक है।'
        )}
      </p>
    </section>
  );
}
