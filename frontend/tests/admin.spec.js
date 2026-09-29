import { test, expect } from '@playwright/test';

test('site toggles persist independently and old weights migrate', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('animescore.weights', JSON.stringify({ bgm: 4, mal: 3, anilist: 0 })));
  await page.goto('/');
  await expect(page.locator('#weight-bgm')).toHaveValue('4');
  await expect(page.locator('[data-weight-enabled="filmarks"]')).not.toBeChecked();
  await page.locator('[data-weight-enabled="filmarks"]').check();
  await page.locator('#weight-filmarks').fill('3');
  await page.getByRole('button', { name: '应用到榜单与趋势' }).click();
  await expect(page.locator('#list-title')).toHaveText('个人加权排名');
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('animescore.weights')));
  expect(saved).toMatchObject({ bgm: 4, mal: 3, filmarks: 3, anikore: 0 });
  await page.locator('[data-weight-enabled="filmarks"]').uncheck();
  await expect(page.locator('#weight-filmarks')).toBeDisabled();
  await page.locator('[data-weight-enabled="filmarks"]').check();
  await expect(page.locator('#weight-filmarks')).toHaveValue('3');
});

test('mapping editor validation, saved state, audit and conflict feedback', async ({ page }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/admin');
  await expect(page.locator('#workspace')).toBeVisible();
  await page.getByRole('searchbox', { name: '搜索映射动画' }).fill('无职转生');
  await page.locator('#mapping-search').press('Enter');
  await expect(page.locator('.mapping-table tbody tr').first()).toBeVisible();
  await page.locator('.mapping-table tbody tr').filter({ hasText: 'Ⅲ' }).first().getByRole('button').click();
  await expect(page.locator('#mapping-title')).toContainText('Ⅲ');
  // UI writes are isolated; API persistence and concurrency are tested with temporary databases in pytest.
  let detail;
  const cid = await page.locator('.mapping-table tbody tr').filter({ hasText: 'Ⅲ' }).first().locator('[data-edit]').getAttribute('data-edit');
  detail = await (await page.request.get(`/api/v1/admin/mappings/${cid}`)).json();
  await page.route('**/api/v1/admin/validate', async route => {
    const body = route.request().postDataJSON();
    if (body.id === 'bad-id') return route.fulfill({ status: 422, json: { detail: 'Filmarks 需要系列 ID/季度 ID' } });
    await route.fulfill({ json: { id: '1431/6089', title: '無職転生Ⅲ', score: 8.4, votes: 1940, status: 'ok' } });
  });
  await page.locator('[data-mode="filmarks"]').selectOption('manual');
  await page.locator('#id-filmarks').fill('bad-id');
  await page.locator('[data-validate="filmarks"]').click();
  await expect(page.locator('[data-result="filmarks"]')).toContainText('系列 ID/季度 ID');
  await page.locator('#id-filmarks').fill('https://filmarks.com/animes/1431/6089');
  await page.locator('[data-validate="filmarks"]').click();
  await expect(page.locator('[data-result="filmarks"]')).toContainText('8.40');
  await expect(page.locator('#id-filmarks')).toHaveValue('1431/6089');
  await page.locator('[data-note="filmarks"]').fill('已核对第三季');
  await page.route(`**/api/v1/admin/mappings/${cid}`, async route => {
    if (route.request().method() !== 'PUT') return route.continue();
    const body = route.request().postDataJSON();
    const before = structuredClone(detail.overrides);
    detail.revision++;
    detail.overrides.filmarks = { id: body.changes.filmarks.id, note: body.changes.filmarks.note, updated_at: Date.now() / 1000 };
    detail.audit.unshift({ id: 999, timestamp: Date.now() / 1000, before, after: structuredClone(detail.overrides) });
    await route.fulfill({ json: detail });
  });
  await page.getByRole('button', { name: '保存映射', exact: true }).click();
  await expect(page.locator('#editor-notice')).toContainText('映射已保存');
  await page.getByRole('button', { name: '修改记录', exact: true }).click();
  await expect(page.locator('#mapping-audit')).toContainText('已核对第三季');
  await page.getByRole('button', { name: '站点映射', exact: true }).click();
  await page.screenshot({ path: `test-results/admin-editor-${test.info().project.name}.png` });
  await page.unroute(`**/api/v1/admin/mappings/${cid}`);
  await page.route(`**/api/v1/admin/mappings/${cid}`, route => route.fulfill({ status: 409, json: { detail: '映射已被其他窗口修改，请重新加载后保存' } }));
  await page.locator('[data-note="filmarks"]').fill('再次核对第三季');
  await page.getByRole('button', { name: '保存映射', exact: true }).click();
  await expect(page.locator('#editor-notice')).toContainText('其他窗口修改');
  await page.getByRole('button', { name: '关闭映射编辑' }).click();
  await page.screenshot({ path: `test-results/admin-list-${test.info().project.name}.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  expect(errors).toEqual([]);
});
