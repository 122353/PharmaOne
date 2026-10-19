import {test, expect, type Page} from '@playwright/test';
import {existsSync, readFileSync} from 'node:fs';
import type {Match} from '../lib/api';

const localEnv = Object.fromEntries(
  (existsSync('.env.local') ? readFileSync('.env.local', 'utf8') : '')
    .split(/\r?\n/)
    .filter(line => /^[A-Za-z_][A-Za-z0-9_]*=/.test(line))
    .map(line => {
      const at = line.indexOf('=');
      return [line.slice(0, at), line.slice(at + 1)];
    }),
);
const project = localEnv.NEXT_PUBLIC_SUPABASE_URL
  ? new URL(localEnv.NEXT_PUBLIC_SUPABASE_URL).hostname.split('.')[0]
  : '';
const storageKey = `sb-${project}-auth-token`;

const alert = {
  fingerprint: 'synthetic-alert',
  product_name: 'Synthetic Test Medicine 10mg Tablet',
  manufacturer: 'Example Labs',
  batch_number: 'SYN-001',
  quality_issue: 'Synthetic test finding',
  reporting_period: 'AUG-2026',
  reporting_source: 'Synthetic test source',
  source_url: 'https://cdscoonline.gov.in/CDSCO/viewPublicNSQDrug',
  retrieved_at: '2026-10-17T20:27:27Z',
  classification: 'nsq',
};

async function seedSignedInUser(page: Page) {
  test.skip(!project || !localEnv.NEXT_PUBLIC_SUPABASE_ANON_KEY, 'Requires web/.env.local with Supabase browser credentials.');
  const user = {
    id: 'synthetic-notification-user', aud: 'authenticated', role: 'authenticated',
    email: 'synthetic@example.test', app_metadata: {}, user_metadata: {},
    created_at: new Date().toISOString(),
  };
  const session = {
    access_token: 'synthetic-browser-token', refresh_token: 'synthetic-browser-refresh',
    token_type: 'bearer', expires_in: 3600,
    expires_at: Math.floor(Date.now() / 1000) + 3600, user,
  };
  await page.addInitScript(({key, value}) => {
    localStorage.setItem(key, JSON.stringify(value));
  }, {key: storageKey, value: session});
}

test('notification count, acknowledgement persistence, and alert fingerprint link', async ({page}) => {
  await seedSignedInUser(page);
  let isRead = false;
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    expect(request.headers().authorization).toBe('Bearer synthetic-browser-token');
    let result: unknown;

    if (path === '/api/dashboard') result = {
      pharmacy: 'Synthetic Pharmacy', inventory_count: 1, potential_count: 1,
      verification_count: 0, open_investigations: 0,
      review_queue: [], recent_alerts: [alert], clarifications: [],
      unread_notifications: isRead ? 0 : 1,
      source: {
        state: 'historical_snapshot', last_checked: null, record_count: 5,
        source_url: alert.source_url, error: '', historical_snapshot_imported: true,
        snapshot_imported_at: alert.retrieved_at, snapshot_reporting_period: 'AUG-2026',
        retrieval_metadata: {imported_as_historical: true},
      },
    };
    else if (path === '/api/notifications') result = [{
      id: 'notice-1', event_id: 'synthetic-event', inventory_id: 'stock-1',
      alert_id: alert.fingerprint, status: 'potential_match',
      title: 'Potential regulatory match', message: 'Synthetic test notice',
      is_read: isRead, is_active: true, medicine_name: alert.product_name,
      batch_number: alert.batch_number, quality_issue: alert.quality_issue,
      reporting_period: alert.reporting_period, source_url: alert.source_url,
      created_at: '2026-10-17T20:27:27Z',
    }];
    else if (path === '/api/notifications/notice-1/read' && request.method() === 'PATCH') {
      isRead = true;
      result = {id: 'notice-1', is_read: true};
    }
    else if (path === '/api/alerts/synthetic-alert') result = alert;
    else if (path === '/api/alerts/synthetic-alert/versions') result = [];
    else if (path === '/api/matches' || path === '/api/investigations') result = [];
    else throw new Error(`Unexpected API request: ${request.method()} ${path}`);

    await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(result)});
  });

  await page.goto('/dashboard');
  await expect(page.getByText('Historical snapshot imported')).toBeVisible();
  await expect(page.getByText(/No live source check is recorded/)).toBeVisible();
  const bell = page.getByRole('button', {name: 'Regulatory notifications, 1 unread'});
  await expect(bell).toBeVisible();
  await bell.click();
  await expect(page.getByText('Source reporting period: AUG-2026')).toBeVisible();
  await expect(page.getByText('Synthetic test finding')).toBeVisible();
  await page.getByRole('button', {name: 'Mark read'}).click();
  await expect(page.getByRole('button', {name: 'Regulatory notifications, 0 unread'})).toBeVisible();
  await expect(page.getByText('Acknowledged')).toBeVisible();

  await page.reload();
  await page.getByRole('button', {name: 'Regulatory notifications, 0 unread'}).click();
  await expect(page.getByText('Acknowledged')).toBeVisible();
  await page.getByRole('link', {name: 'Review', exact: true}).click();
  await expect(page).toHaveURL(/\/alerts\/synthetic-alert$/, {timeout: 15000});
  await expect(page.getByRole('heading', {name: alert.product_name})).toBeVisible();
  await expect(page.getByText('Synthetic test finding')).toBeVisible();
});

test('notification load errors show a retry state', async ({page}) => {
  await seedSignedInUser(page);
  let fail = true;
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/dashboard') {
      await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({
        pharmacy: 'Synthetic Pharmacy', inventory_count: 0, potential_count: 0,
        verification_count: 0, open_investigations: 0, review_queue: [],
        recent_alerts: [], clarifications: [], unread_notifications: 0,
        source: {
          state: 'never_synced', last_checked: null, record_count: 0,
          source_url: alert.source_url, error: '', historical_snapshot_imported: false,
          snapshot_imported_at: null, snapshot_reporting_period: null, retrieval_metadata: {},
        },
      })});
      return;
    }
    if (path === '/api/notifications' && fail) {
      await route.fulfill({status: 503, contentType: 'application/json', body: JSON.stringify({detail: 'Source unavailable'})});
      return;
    }
    if (path === '/api/notifications') {
      await route.fulfill({status: 200, contentType: 'application/json', body: '[]'});
      return;
    }
    throw new Error(`Unexpected API request: ${route.request().method()} ${path}`);
  });

  await page.goto('/dashboard');
  await page.getByRole('button', {name: 'Regulatory notifications, 0 unread'}).click();
  await expect(page.locator('.notification-card [role="alert"]')).toContainText('Could not load notifications');
  fail = false;
  await page.getByRole('button', {name: 'Retry'}).click();
  await expect(page.getByText('No notifications yet.')).toBeVisible();
});

test('alert detail clearly requires review for a strength conflict', async ({page}) => {
  await seedSignedInUser(page);
  const mismatched: Match = {
    id: 'synthetic-match',
    status: 'needs_verification',
    inventory: {
      id: 'synthetic-stock', medicine_name: 'Linezolid Tablets IP 300mg',
      manufacturer: 'Symbiosis Pharmaceuticals Pvt Ltd', batch_number: 'TG261185',
      strength: '300mg', expiry_date: '2028-04-01', quantity: 4, quality_state: 'normal',
    },
    alert: {...alert, product_name: 'Linezolid Tablets IP 600mg'},
    explanation: {
      product: {
        inventory: 'Linezolid Tablets IP 300mg', source: 'Linezolid Tablets IP 600mg',
        aligned: true, inventory_ingredients: ['linezolid'], source_ingredients: ['linezolid'],
        inventory_form: ['tablet'], source_form: ['tablet'], form_aligned: true,
        inventory_release: [], source_release: [], release_aligned: true,
      },
      batch: {inventory: 'TG261185', source: 'TG261185', exact: true},
      manufacturer: {
        inventory: 'Symbiosis Pharmaceuticals Pvt Ltd',
        source: 'Symbiosis Pharmaceuticals Pvt Ltd', aligned: true,
      },
      strength: {
        inventory: [{value_mg: '300', basis: 'dose'}],
        inventory_name: [{value_mg: '300', basis: 'dose'}],
        inventory_field: [{value_mg: '300', basis: 'dose'}],
        source: [{value_mg: '600', basis: 'dose'}],
        aligned: false, inventory_conflict: false, duplicate_sources: true,
      },
    },
  };

  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const result = path === '/api/alerts/synthetic-alert' ? mismatched.alert
      : path === '/api/alerts/synthetic-alert/versions' ? []
      : path === '/api/matches' ? [mismatched]
      : path === '/api/investigations' ? []
      : undefined;
    if (result === undefined) throw new Error(`Unexpected API request: ${path}`);
    await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(result)});
  });

  await page.goto('/alerts/synthetic-alert');
  await expect(page.getByRole('heading', {name: 'Linezolid Tablets IP 600mg'})).toBeVisible();
  await expect(page.getByText('Inventory and regulatory strengths differ. This requires pharmacist verification.')).toBeVisible();
  await expect(page.getByText(/One or more identifiers are missing or conflict/)).toBeVisible();
  await expect(page.getByText('NSQ · Not automatically a recall')).toBeVisible();
});

test('mobile Hindi notification acknowledgement rolls back after rate limiting', async ({page}) => {
  await page.setViewportSize({width: 390, height: 844});
  await seedSignedInUser(page);
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/read')) {
      await route.fulfill({status: 429, contentType: 'application/json', headers: {'Retry-After': '30'}, body: '{"detail":"Too many requests"}'});
      return;
    }
    const data = path === '/api/dashboard' ? {
      pharmacy: 'Synthetic Pharmacy', inventory_count: 1, potential_count: 1, verification_count: 0,
      open_investigations: 0, review_queue: [], recent_alerts: [], clarifications: [], unread_notifications: 1,
      source: {state: 'historical_snapshot', last_checked: null, record_count: 5, source_url: alert.source_url,
        error: '', historical_snapshot_imported: true, snapshot_imported_at: alert.retrieved_at,
        snapshot_reporting_period: 'AUG-2026', retrieval_metadata: {}},
    } : [{id: 'mobile-notice', event_id: 'mobile-event', inventory_id: 'stock', alert_id: alert.fingerprint,
      status: 'needs_verification', title: 'Verification', message: '', is_read: false, is_active: true,
      medicine_name: alert.product_name, batch_number: alert.batch_number, quality_issue: alert.quality_issue,
      reporting_period: alert.reporting_period, source_url: alert.source_url, created_at: alert.retrieved_at}];
    await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(data)});
  });
  await page.goto('/dashboard');
  await page.getByLabel('Interface language').selectOption('hi');
  await page.getByRole('button', {name: 'नियामक सूचनाएँ, 1 अपठित'}).click();
  await page.getByRole('button', {name: 'पढ़ा हुआ', exact: true}).click();
  await expect(page.locator('.notification-card [role="alert"]')).toContainText('सूचना अपडेट नहीं हुई');
  await expect(page.getByRole('button', {name: 'नियामक सूचनाएँ, 1 अपठित'})).toBeVisible();
  await expect(page.getByRole('button', {name: 'पढ़ा हुआ', exact: true})).toBeEnabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('missing manufacturer remains a visible pharmacist verification case', async ({page}) => {
  await seedSignedInUser(page);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const match = {id: 'missing-maker', status: 'needs_verification', inventory: {id: 'stock',
    medicine_name: alert.product_name, manufacturer: '', batch_number: alert.batch_number,
    strength: '10mg', expiry_date: '', quantity: 1, quality_state: 'needs_verification'}, alert,
    explanation: {product: {inventory: alert.product_name, source: alert.product_name, aligned: true},
      batch: {inventory: alert.batch_number, source: alert.batch_number, exact: true},
      manufacturer: {inventory: '', source: alert.manufacturer, aligned: false}}};
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    const data = path === '/api/alerts/synthetic-alert' ? alert : path === '/api/matches' ? [match] : [];
    await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(data)});
  });
  await page.goto('/alerts/synthetic-alert');
  await expect(page.getByText('Manufacturer identity is missing or differs. Confirm the manufacturer from the physical package.')).toBeVisible();
  await expect(page.getByText(/One or more identifiers are missing or conflict/)).toBeVisible();
  expect(errors).toEqual([]);
});

for (const state of ['historical_snapshot', 'unavailable', 'succeeded']) {
  test(`regulatory list accurately labels ${state} evidence`, async ({page}) => {
    await seedSignedInUser(page);
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname;
      const data = path === '/api/alerts' ? [alert] : {
        state, last_checked: state === 'succeeded' ? '2026-10-19T01:00:00Z' : null,
        record_count: 5, source_url: alert.source_url, error: '', historical_snapshot_imported: true,
        snapshot_reporting_period: 'AUG-2026', snapshot_imported_at: alert.retrieved_at, retrieval_metadata: {},
      };
      await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(data)});
    });
    await page.goto('/alerts');
    const message = state === 'historical_snapshot' ? /Historical snapshot.*AUG-2026.*No live source check/
      : state === 'unavailable' ? /Source unavailable.*may be stale/
      : /Last successful source check/;
    await expect(page.locator('.notice').first()).toContainText(message);
    await expect(page.getByRole('link', {name: alert.product_name})).toBeVisible();
    expect(errors).toEqual([]);
  });
}
