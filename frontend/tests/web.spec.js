import { test, expect } from '@playwright/test';

test('rankings, custom weights, favorites and real history controls', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('.score-table tbody tr').first()).toBeVisible();
  await expect(page.locator('#metric-total')).not.toHaveText('—');
  await page.getByRole('button', { name: '等权', exact: true }).click();
  await page.getByRole('button', { name: '应用到榜单与趋势' }).click();
  await expect(page.locator('#list-title')).toHaveText('个人加权排名');
  await page.reload();
  await expect(page.locator('#weight-bgm')).toHaveValue('1');
  await expect(page.locator('#weight-anilist')).toHaveValue('1');
  await page.getByRole('button', { name: '恢复默认权重' }).click();
  await expect(page.locator('#weight-bgm')).toHaveValue('5');
  await page.getByRole('searchbox', { name: '搜索动画' }).fill('无职转生');
  await page.locator('#search-form').press('Enter');
  await expect(page.locator('#list-title')).toContainText('无职转生');
  const title = page.locator('.anime-title').filter({ hasText: 'Ⅲ' }).first();
  await expect(title).toBeVisible();
  await title.click();
  await expect(page.locator('#detail-title')).toContainText('Ⅲ');
  await expect(page.locator('#history-count')).toContainText('采集点');
  for (const period of ['30d', '90d', '1y', '7d']) {
    await page.locator(`[data-period="${period}"]`).click();
    await expect(page.locator('#download-history')).toHaveAttribute('href', new RegExp(`period=${period}`));
  }
  const historyRoute = '**/api/v1/dashboard/anime/*/history?**';
  await page.route(historyRoute, route => route.fulfill({ status: 503, body: 'History unavailable' }));
  await page.locator('[data-period="30d"]').click();
  await expect(page.locator('#history-note')).toContainText('历史读取失败');
  await expect(page.locator('#download-history')).not.toHaveAttribute('href');
  await page.unroute(historyRoute);
  await page.locator('[data-period="7d"]').click();
  await expect(page.locator('#history-count')).toContainText('采集点');
  await page.getByRole('button', { name: '评分人数', exact: true }).click();
  await expect(page.locator('#trend-chart canvas')).toBeVisible();
  const chartPixels = await page.locator('#trend-chart canvas').evaluate(canvas => {
    const pixels = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    let drawn = 0;
    for (let i = 3; i < pixels.length; i += 4) if (pixels[i] > 0) drawn++;
    return drawn;
  });
  expect(chartPixels).toBeGreaterThan(500);
  await page.screenshot({ path: `test-results/detail-${test.info().project.name}.png`, fullPage: false });
  await page.locator('#detail-dialog [data-favorite]').click();
  await page.getByRole('button', { name: '关闭详情' }).click();
  await page.locator('[data-view="favorites"]').click();
  await expect(page.locator('.anime-title').filter({ hasText: 'Ⅲ' }).first()).toBeVisible();
  await page.locator('[data-view="insights"]').click();
  await expect(page.locator('#coverage-chart canvas')).toBeVisible();
  await page.locator('[data-view="ranking"]').click();
  await expect(page.locator('.score-table tbody tr').first()).toBeVisible();
  await page.locator('#toast').waitFor({ state: 'hidden' });
  await page.locator('.score-table img').evaluateAll(async images => {
    images.forEach(image => image.loading = 'eager');
    await Promise.race([Promise.allSettled(images.map(image => image.decode())), new Promise(resolve => setTimeout(resolve, 15000))]);
  });
  await expect(page.locator('.score-table img').first()).toHaveJSProperty('complete', true);
  expect(await page.locator('.score-table img').first().evaluate(image => image.naturalWidth)).toBeGreaterThan(0);
  await page.screenshot({ path: `test-results/ranking-${test.info().project.name}.png`, fullPage: true });
  await page.screenshot({ path: `test-results/viewport-${test.info().project.name}.png` });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
  expect(errors).toEqual([]);
});

test('empty results, zero weights and safe error states', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.score-table')).toBeVisible();
  for (const p of ['bgm', 'mal', 'anilist', 'filmarks', 'anikore']) await page.locator(`[data-weight-enabled="${p}"]`).uncheck();
  await expect(page.locator('#weight-error')).toBeVisible();
  await expect(page.locator('#apply-weights')).toBeDisabled();
  await page.getByRole('button', { name: '恢复默认权重' }).click();
  await page.getByRole('searchbox', { name: '搜索动画' }).fill('zzzz-no-anime-found-123');
  await page.locator('#search-form').press('Enter');
  await expect(page.getByRole('heading', { name: '没有找到符合条件的动画' })).toBeVisible();
  await page.getByRole('button', { name: '评分口径与数据说明' }).click();
  await expect(page.locator('#method-dialog')).toBeVisible();
  await page.getByRole('button', { name: '关闭说明' }).click();
  await page.route('**/api/v1/dashboard/ranking?**', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"Test service unavailable"}' }));
  await page.getByRole('button', { name: '刷新数据' }).click();
  await expect(page.locator('#notice')).toContainText('数据读取失败');
});
