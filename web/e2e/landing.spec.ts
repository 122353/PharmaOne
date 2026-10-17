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
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  expect(overflow).toBe(false);
  await page.screenshot({path:'test-results/landing-mobile.png',fullPage:true});
});
