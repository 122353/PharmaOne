import {test,expect} from '@playwright/test';
test('landing page explains safety and navigates to signup',async({page})=>{
  await page.goto('http://localhost:3000');
  await expect(page.getByRole('heading',{level:1})).toContainText('medicine-quality alert');
  await page.screenshot({path:'test-results/landing-desktop.png',fullPage:true});
  await page.getByRole('link',{name:/create pharmacy workspace/i}).click();
  await expect(page).toHaveURL(/\/signup$/);
  await expect(page.getByRole('heading',{name:'Create your workspace'})).toBeVisible();
});
test('landing remains usable on a narrow phone',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('http://localhost:3000');
  await expect(page.getByRole('link',{name:/get started/i}).first()).toBeVisible();
  const overflow=await page.evaluate(()=>({width:document.documentElement.scrollWidth,viewport:window.innerWidth,offenders:[...document.querySelectorAll('*')].filter(el=>el.getBoundingClientRect().right>window.innerWidth+1).slice(0,8).map(el=>({tag:el.tagName,className:el.className,right:el.getBoundingClientRect().right}))}));
  expect(overflow.width,JSON.stringify(overflow.offenders)).toBeLessThanOrEqual(overflow.viewport);
  await page.screenshot({path:'test-results/landing-mobile.png',fullPage:true});
});

test('landing motion is eased and respects reduced motion',async({page})=>{
  await page.goto('http://localhost:3000');
  const button=page.getByRole('link',{name:/create pharmacy workspace/i});
  const card=page.locator('.step-card').first();
  const durations=await Promise.all([button,card].map(locator=>locator.evaluate(el=>getComputedStyle(el).transitionDuration)));
  expect(durations.every(duration=>parseFloat(duration)>=0.25)).toBe(true);
  await page.emulateMedia({reducedMotion:'reduce'});
  await expect.poll(()=>button.evaluate(el=>getComputedStyle(el).transitionDuration)).toBe('0s');
  await expect.poll(()=>card.evaluate(el=>getComputedStyle(el).transitionDuration)).toBe('0s');
});
