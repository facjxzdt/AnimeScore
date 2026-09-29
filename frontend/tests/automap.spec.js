import { test, expect } from '@playwright/test';

test('automatic mapping job controls and candidate selection', async ({ page }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  let state = { status: 'idle', current_year: 2026, current_season: 'summer', completed: 0, total: 0, counts: {}, recent: [] };
  await page.route('**/api/v1/admin/filmarks/job', async route => {
    if (route.request().method() === 'POST') {
      expect(route.request().postDataJSON()).toMatchObject({ scope: 'season', year: 2026, season: 'summer', apply: false, limit: 25 });
      state = { ...state, status: 'running', total: 25, completed: 2, counts: { review: 2 } };
    }
    await route.fulfill({ json: state });
  });
  await page.route('**/api/v1/admin/filmarks/job/cancel', async route => {
    state = { ...state, status: 'cancelled' }; await route.fulfill({ json: state });
  });
  await page.route('**/api/v1/admin/filmarks/discover/*', route => route.fulfill({ json: {
    status: 'review', checked_at: Date.now() / 1000, errors: [], candidates: [{ id: '1431/6089', title: '無職転生Ⅲ', date: '2026-07-05', method: '季度目录', url: 'https://filmarks.com/animes/1431/6089', reasons: ['名称一致', '开播日期相差 9 天'], verified: true }],
  } }));
  await page.goto('/admin');
  await expect(page.locator('#job-state')).toHaveText('待启动');
  await page.locator('#batch-limit').fill('25');
  await page.locator('#batch-apply').uncheck();
  await page.getByRole('button', { name: '开始匹配', exact: true }).click();
  await expect(page.locator('#job-counts')).toContainText('2 / 25');
  await expect(page.locator('#start-mapping')).toBeDisabled();
  await page.getByRole('button', { name: '停止自动映射', exact: true }).click();
  await expect(page.locator('#job-state')).toHaveText('已停止');
  await page.locator('#filmarks-filter').selectOption('review');
  await expect(page.locator('#filmarks-filter')).toHaveValue('review');
  await page.locator('#filmarks-filter').selectOption('');
  await page.locator('#mapping-query').fill('无职转生');
  await page.locator('#mapping-search').press('Enter');
  await page.locator('.mapping-table tbody tr').filter({ hasText: 'Ⅲ' }).first().getByRole('button').click();
  await page.getByRole('button', { name: '查找候选', exact: true }).click();
  await expect(page.locator('#filmarks-candidates')).toContainText('开播日期相差 9 天');
  await page.getByRole('button', { name: '采用候选 無職転生Ⅲ', exact: true }).click();
  await expect(page.locator('#id-filmarks')).toHaveValue('1431/6089');
  await expect(page.locator('#editor-notice')).toContainText('尚未保存');
  await page.locator('#filmarks-candidates').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `test-results/filmarks-candidates-${test.info().project.name}.png` });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width);
  expect(errors).toEqual([]);
});
