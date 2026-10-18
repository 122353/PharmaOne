import {test, expect} from '@playwright/test';

test('signup blocks duplicate submissions and explains email throttling', async ({page}) => {
  let requests = 0;
  await page.route(/\/auth\/v1\/signup(?:\?|$)/, async route => {
    requests += 1;
    await new Promise(resolve => setTimeout(resolve, 200));
    await route.fulfill({
      status: 429,
      contentType: 'application/json',
      body: JSON.stringify({code: 'over_email_send_rate_limit', message: 'email rate limit exceeded'}),
    });
  });
  await page.goto('/signup');
  await page.getByLabel('Your name').fill('Synthetic Tester');
  await page.getByLabel('Work email').fill('synthetic@example.test');
  await page.getByLabel('Password', {exact: true}).fill('synthetic-pass-123');
  await page.getByLabel('Confirm password').fill('synthetic-pass-123');
  await page.getByRole('checkbox').check();
  const submit = page.locator('form button[type="submit"]');
  await submit.click();
  await expect(submit).toBeDisabled();
  await expect(page.locator('form [role="alert"]')).toContainText('Email delivery is temporarily rate limited');
  expect(requests).toBe(1);
  await page.getByLabel('Interface language').selectOption('hi');
  await expect(page.getByRole('heading', {name: 'अपना कार्यक्षेत्र बनाएँ'})).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', {name: 'अपना कार्यक्षेत्र बनाएँ'})).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'hi');
});
