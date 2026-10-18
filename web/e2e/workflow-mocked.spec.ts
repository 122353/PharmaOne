import {test, expect} from '@playwright/test';
import {existsSync, readFileSync} from 'node:fs';

// This exercises the browser workflow with synthetic API responses. It does not
// assert live Supabase Auth or TinyFish behavior.
const localEnv = Object.fromEntries(
  (existsSync('.env.local') ? readFileSync('.env.local', 'utf8') : '').split(/\r?\n/).filter(line => /^[A-Za-z_][A-Za-z0-9_]*=/.test(line))
    .map(line => { const at = line.indexOf('='); return [line.slice(0, at), line.slice(at + 1)]; }),
);
const project = localEnv.NEXT_PUBLIC_SUPABASE_URL ? new URL(localEnv.NEXT_PUBLIC_SUPABASE_URL).hostname.split('.')[0] : '';
const storageKey = `sb-${project}-auth-token`;

test('synthetic signed-in pharmacy journey persists review and simulated hold on refresh', async ({page}) => {
  test.setTimeout(120000);
  test.skip(!project, 'Requires a configured web/.env.local');
  const user = {id: 'synthetic-browser-user', aud: 'authenticated', role: 'authenticated', email: 'synthetic@example.test', app_metadata: {}, user_metadata: {}, created_at: new Date().toISOString()};
  const session = {access_token: 'synthetic-browser-token', refresh_token: 'synthetic-browser-refresh', token_type: 'bearer', expires_in: 3600, expires_at: Math.floor(Date.now() / 1000) + 3600, user};
  await page.addInitScript(({key, value}) => {
    if (!sessionStorage.getItem('pharmaone-e2e-seeded')) {
      localStorage.setItem(key, JSON.stringify(value));
      sessionStorage.setItem('pharmaone-e2e-seeded', 'yes');
    }
  }, {key: storageKey, value: session});

  const alert = {fingerprint: 'synthetic-alert', product_name: 'Synthetic Test Medicine', manufacturer: 'Example Labs', batch_number: 'SYN123', quality_issue: 'Synthetic test finding', reporting_period: 'AUG-2026', reporting_source: 'Test source', source_url: 'https://cdscoonline.gov.in/CDSCO/viewPublicNSQDrug', retrieved_at: new Date().toISOString(), classification: 'nsq'};
  let pharmacy: Record<string, unknown> | null = null;
  let stock: Record<string, unknown>[] = [];
  let investigation: Record<string, unknown> | null = null;
  let events: Record<string, unknown>[] = [];
  let attachments: Record<string, unknown>[] = [];
  await page.route('http://localhost:8000/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    expect(request.headers().authorization).toBe('Bearer synthetic-browser-token');
    const body = request.headers()['content-type']?.includes('application/json')
      ? request.postDataJSON() as Record<string, unknown> : undefined;
    let result: unknown = null;
    if (path === '/api/me') result = {user_id: user.id, pharmacy};
    else if (path === '/api/pharmacies/current' && request.method() === 'PUT') result = pharmacy = body || null;
    else if (path === '/api/pharmacies/current') result = pharmacy;
    else if (path === '/api/inventory/import') {
      stock = [{id: 'synthetic-stock', medicine_name: alert.product_name, manufacturer: alert.manufacturer, batch_number: alert.batch_number, strength: '10mg', expiry_date: '2027-01-01', quantity: 3, quality_state: 'ready'}];
      result = {imported: 1, duplicates: 0, rejected: 0, incomplete: 0, errors: []};
    }
    else if (path === '/api/inventory') result = stock;
    else if (path === '/api/matches') result = stock.length ? [{id: 'synthetic-match', status: 'potential_match', checked_at: new Date().toISOString(), inventory: stock[0], alert, explanation: {product: {inventory: alert.product_name, source: alert.product_name, aligned: true}, batch: {inventory: alert.batch_number, source: alert.batch_number, exact: true}, manufacturer: {inventory: alert.manufacturer, source: alert.manufacturer, aligned: true}}}] : [];
    else if (path === '/api/dashboard') result = {pharmacy: pharmacy?.name || 'Synthetic Pharmacy', inventory_count: stock.length, potential_count: stock.length ? 1 : 0, verification_count: 0, open_investigations: investigation?.status === 'open' ? 1 : 0, review_queue: stock.length ? [{id: 'synthetic-match', status: 'potential_match', inventory: stock[0], alert}] : [], recent_alerts: [alert], clarifications: [], source: {state: 'succeeded', last_checked: new Date().toISOString(), record_count: 1, source_url: alert.source_url, error: ''}};
    else if (path === '/api/alerts') result = [alert];
    else if (path === '/api/alerts/synthetic-alert') result = alert;
    else if (path === '/api/alerts/synthetic-alert/versions') result = [];
    else if (path === '/api/investigations' && request.method() === 'POST') {
      const action = String(body?.status || 'open');
      investigation = {
        id: 'synthetic-investigation', match_id: body?.match_id,
        status: ['simulated_hold', 'physical_verification_pending'].includes(action) ? (investigation?.status || 'open') : action,
        physical_status: action === 'physical_verification_pending' ? 'pending' : body?.physical_verified ? 'verified' : 'unverified',
        simulated_hold: action === 'simulated_hold' || Boolean(investigation?.simulated_hold),
        note: body?.note, record_reviewed: Boolean(body?.record_reviewed),
        physical_verified: Boolean(body?.physical_verified), updated_at: new Date().toISOString(),
      };
      events.push({id: `event-${events.length}`, action: `investigation_${action}`, created_at: new Date().toISOString(), detail: {note: body?.note}});
      result = investigation;
    }
    else if (path === '/api/investigations') result = investigation ? [investigation] : [];
    else if (path === '/api/investigations/synthetic-investigation/events') result = events;
    else if (path === '/api/investigations/synthetic-investigation/attachments' && request.method() === 'POST') result = (attachments = [{id: 'synthetic-attachment', filename: 'evidence.png', size: 9, created_at: new Date().toISOString()}])[0];
    else if (path === '/api/investigations/synthetic-investigation/attachments') result = attachments;
    else if (path === '/api/ingestion/status') result = {state: 'succeeded', last_checked: new Date().toISOString(), record_count: 1, source_url: alert.source_url, error: ''};
    else if (path === '/api/scan/match') result = {matches: body?.batch_number === alert.batch_number ? [{status: 'potential_match', explanation: {pharma_match: {product_similarity: 0.9, version: 'synthetic-test'}}, alert: {...alert, pharma_classify: {category: 'unclassified', version: 'synthetic-test'}}}] : [], note: 'Potential matches require physical verification.'};
    else if (path === '/api/contextos/ask') result = {mode: 'evidence_only', answer: body?.language === 'hi' ? 'आधिकारिक रिकॉर्ड में बैच SYN123 है।' : 'Official evidence lists batch SYN123.', evidence: [{...alert}], inventory_match: 'potential_match', language: body?.language};
    else throw new Error(`Unexpected API request: ${request.method()} ${path}`);
    await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(result)});
  });

  await page.goto('/onboarding/pharmacy');
  await page.getByLabel('Trading name').fill('Synthetic Pharmacy');
  await page.getByRole('button', {name: 'Continue'}).click();
  await page.getByRole('button', {name: 'Continue'}).click();
  await page.getByRole('button', {name: 'Continue'}).click();
  await page.getByRole('button', {name: /save & continue/i}).click();
  await expect(page).toHaveURL(/onboarding\/inventory/);

  await page.locator('input[type=file]').setInputFiles({name: 'synthetic.csv', mimeType: 'text/csv', buffer: Buffer.from('medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nSynthetic Test Medicine,Example Labs,SYN123,10mg,2027-01-01,3\n')});
  await page.getByRole('button', {name: /confirm import/i}).click();
  await expect(page.getByText('Imported 1 rows')).toBeVisible();
  await page.getByRole('link', {name: /continue to dashboard/i}).click();
  await expect(page.getByText('Potential matches')).toBeVisible();
  await page.getByRole('link', {name: 'Scan Medicine'}).click();
  const imageBase64 = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 1200; canvas.height = 340;
    const context = canvas.getContext('2d')!;
    context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = '#000'; context.font = 'bold 42px Arial';
    context.fillText('Medicine: Synthetic Test Medicine', 35, 75);
    context.fillText('Manufacturer: Example Labs', 35, 145);
    context.fillText('Batch: WRONG', 35, 215);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  await page.locator('input[type=file]').setInputFiles({name: 'synthetic.png', mimeType: 'image/png', buffer: Buffer.from(imageBase64, 'base64')});
  await expect(page.getByText('Original extracted text')).toBeVisible({timeout:90000});
  await expect(page.getByText('Medicine: Synthetic Test Medicine', {exact: false})).toBeVisible();
  await page.getByLabel('Batch number').fill('SYN123');
  await page.getByRole('button', {name: 'Confirm and match CDSCO records'}).click();
  await expect(page.getByText('Potential quality alerts')).toBeVisible();
  await page.getByRole('link', {name: 'Review alert'}).click();
  await expect(page.getByText('Synthetic test finding')).toBeVisible();
  await page.getByRole('link', {name: 'Explain This Alert with ContextOS'}).click();
  await page.getByLabel('Your question').fill('What should I verify?');
  await page.getByRole('button', {name: 'Ask ContextOS'}).last().click();
  await expect(page.getByText('Official evidence lists batch SYN123.')).toBeVisible();
  await page.getByLabel('Interface language').selectOption('hi');
  await page.getByRole('textbox', {name: 'आपका प्रश्न'}).fill('यह बैच क्यों चिह्नित है?');
  await page.getByRole('button', {name: 'ContextOS से पूछें'}).last().click();
  await expect(page.getByText('आधिकारिक रिकॉर्ड में बैच SYN123 है।')).toBeVisible();
  await page.getByLabel('Interface language').selectOption('en');
  await page.goto('/dashboard');
  await page.getByRole('link', {name: /review alert/i}).click();
  await expect(page.getByText('Synthetic test finding')).toBeVisible();
  await page.getByLabel('Pharmacist note').fill('Synthetic stock checked');
  await page.getByRole('button', {name: 'Mark reviewed'}).click();
  await expect(page.getByText('Review:', {exact: false})).toBeVisible();
  await page.getByLabel('Add evidence file').setInputFiles({name: 'evidence.png', mimeType: 'image/png', buffer: Buffer.from([137,80,78,71,13,10,26,10,1])});
  await expect(page.getByText('evidence.png', {exact: false})).toBeVisible();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name: 'Simulate hold'}).click();
  await expect(page.getByText('Simulated hold recorded')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Review:', {exact: false})).toBeVisible();
  await expect(page.getByRole('textbox', {name: 'Pharmacist note'})).toHaveValue('Synthetic stock checked');
  await page.getByRole('link', {name: 'Investigations'}).click();
  await expect(page).toHaveURL(/\/investigations$/);
  await expect(page.getByRole('heading', {name: 'Investigations'})).toBeVisible();
  await expect(page.getByText('Simulated hold', {exact: true})).toBeVisible();
  await page.setViewportSize({width: 390, height: 844});
  await page.reload();
  await expect(page.getByRole('heading', {name: 'Investigations'})).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.getByRole('button', {name: 'Open menu'}).click();
  await expect(page.getByRole('navigation', {name: 'Product navigation'})).toBeVisible();
});
