import { chromium } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const snapshotBytes = readFileSync(resolve(root, 'evidence/cdsco-aug-2026-tinyfish.json'));
const evidence = JSON.parse(snapshotBytes.toString('utf8'));
const browser = await chromium.launch({ headless: true });

try {
  const page = await browser.newPage();
  await page.goto(evidence.source_url, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.locator('#repYear').selectOption('2026');
  await page.locator('#repMonth option').filter({ hasText: /Aug/i }).first().waitFor({ state: 'attached', timeout: 10000 });
  const august = await page.locator('#repMonth option').evaluateAll(options =>
    options.find(option => /aug/i.test(option.textContent || ''))?.value,
  );
  if (!august) throw new Error('August 2026 is unavailable on the official site');
  await page.locator('#repMonth').selectOption(august);
  await page.getByRole('button', { name: 'Apply Filter' }).click();
  await page.waitForFunction(() =>
    [...document.querySelectorAll('#NSQDrug tbody tr')].some(row => row.textContent?.includes('AUG-2026')),
    null, { timeout: 20000 },
  );
  const official = await page.locator('#NSQDrug tbody tr').evaluateAll(rows => rows.slice(0, 5).map(row => {
    const cells = [...row.querySelectorAll('td')].map(cell => cell.textContent?.trim() || '');
    return {
      product_name: cells[1], batch_number: cells[2], manufacturer: cells[5],
      quality_issue: cells[6], reporting_source: cells[7], reporting_period: cells[9],
    };
  }));
  const fields = ['product_name', 'manufacturer', 'batch_number', 'quality_issue', 'reporting_source', 'reporting_period'];
  const mismatches = evidence.records.flatMap((record, index) =>
    fields.filter(field => record[field] !== official[index]?.[field]).map(field => ({ row: index + 1, field })),
  );
  const report = {
    status: mismatches.length ? 'failed' : 'verified',
    verified_at: new Date().toISOString(),
    source_url: evidence.source_url,
    provider_run_id: evidence.provider_run_id,
    snapshot_sha256: createHash('sha256').update(snapshotBytes.toString('utf8').replaceAll('\r\n', '\n')).digest('hex'),
    records_checked: evidence.records.length,
    fields_checked: evidence.records.length * fields.length,
    mismatches,
  };
  writeFileSync(resolve(root, 'evidence/cdsco-verification-report.json'), JSON.stringify(report, null, 2) + '\n');
  process.stdout.write(`${report.status}: ${report.records_checked} rows, ${report.fields_checked} fields; ${mismatches.length} mismatches\n`);
  if (mismatches.length) process.exitCode = 1;
} finally {
  await browser.close();
}
