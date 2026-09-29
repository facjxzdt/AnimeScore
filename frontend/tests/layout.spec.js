import { test, expect } from '@playwright/test';

test('mapping dialog controls remain inside the viewport', async ({ page }) => {
  await page.goto('/admin');
  await expect(page.locator('#workspace')).toBeVisible();
  await page.locator('#mapping-query').fill('无职转生');
  await page.locator('#mapping-search').press('Enter');
  await expect(page.locator('.mapping-table')).toBeVisible();
  await page.locator('.mapping-table tbody tr').filter({ hasText: 'Ⅲ' }).first().getByRole('button').click();
  await page.locator('[data-mode="filmarks"]').selectOption('manual');
  await page.locator('#id-filmarks').fill('bad-id');
  const geometry = await page.evaluate(() => {
    const button = document.querySelector('[data-validate="filmarks"]');
    const r = button.getBoundingClientRect();
    const d = document.querySelector('dialog[open]').getBoundingClientRect();
    return { viewport: innerWidth, root: document.documentElement.scrollWidth, scrollX, visual: { scale: visualViewport.scale, x: visualViewport.offsetLeft, y: visualViewport.offsetTop, width: visualViewport.width }, dialog: { x: d.x, width: d.width }, button: { x: r.x, y: r.y, width: r.width }, hit: document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)?.outerHTML.slice(0, 150) };
  });
  expect(geometry.root).toBeLessThanOrEqual(page.viewportSize().width);
  expect(geometry.dialog.x).toBeGreaterThanOrEqual(0);
  expect(geometry.visual.scale).toBe(1);
});
