import { test, expect } from '@playwright/test';

const user = { id: 71, username: 'verified-user', nickname: '投稿测试用户', role: 'user' };
const quota = { limit: 5, errors: 0, remaining: 5, pending: false, day: '2026-09-28', resets_at: '2026-09-29T00:00:00+08:00' };

async function mockAccount(page, overrides = {}) {
  await page.route('**/api/v1/auth/me', route => route.fulfill({ json: { user, quota, csrf_token: 'test-csrf', login_enabled: true, review_enabled: true, ...overrides } }));
}

test('user submits missing ID, sees verified credit and collected score', async ({ page }) => {
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await mockAccount(page);
  let item, accepted = false, checks = 0, record;
  const credit = { bgm_id: 71, username: 'verified-user', profile_url: 'https://bgm.tv/user/71' };
  await page.route('**/api/v1/dashboard/anime/*?**', async route => {
    const response = await route.fetch({ url: route.request().url().replace('refresh=true', 'refresh=false') });
    const data = await response.json();
    data.mapping_sources.filmarks = accepted ? 'community' : 'missing';
    if (accepted) { data.ids.filmarks_id = '1/2'; data.scores.filmarks = 8.4; data.mapping_contributors = { filmarks: credit }; }
    else { delete data.ids.filmarks_id; data.scores.filmarks = null; }
    item = data;
    await route.fulfill({ json: data });
  });
  await page.route('**/api/v1/dashboard/ranking?**', async route => {
    const response = await route.fetch(); const data = await response.json();
    if (accepted) for (const entry of data.items) if (entry.catalog_id === item.catalog_id) entry.mapping_contributors = { filmarks: credit };
    await route.fulfill({ json: data });
  });
  await page.route('**/api/v1/contributions*', async route => {
    const request = route.request();
    if (request.method() === 'POST') {
      expect(request.headers()['x-csrf-token']).toBe('test-csrf');
      expect(request.postDataJSON()).toEqual({ catalog_id: item.catalog_id, provider: 'filmarks', id: '1/2' });
      record = { id: 'submission1', catalog_id: item.catalog_id, anime_name: item.name_cn || item.name, provider: 'filmarks', identifier: '1/2', url: 'https://filmarks.com/animes/1/2', status: 'queued', created_at: Date.now() / 1000 };
      await route.fulfill({ status: 202, json: { submission: record, quota: { ...quota, pending: true } } });
    } else if (new URL(request.url()).pathname.endsWith('/submission1')) {
      accepted = ++checks >= 2;
      record = { ...record, status: accepted ? 'accepted' : 'reviewing', score_status: accepted ? 'ok' : null, reason: accepted ? '作品名称与季度一致' : '' };
      await route.fulfill({ json: { submission: record, quota: { ...quota, pending: !accepted } } });
    } else await route.fulfill({ json: { items: record ? [record] : [], quota } });
  });
  // The status URL includes a slash, so keep a separate route for polling.
  await page.route('**/api/v1/contributions/submission1', async route => {
    accepted = ++checks >= 2;
    record = { ...record, status: accepted ? 'accepted' : 'reviewing', score_status: accepted ? 'ok' : null, reason: accepted ? '作品名称与季度一致' : '' };
    await route.fulfill({ json: { submission: record, quota: { ...quota, pending: !accepted } } });
  });
  await page.goto('/');
  await expect(page.locator('#account-bar')).toContainText('verified-user');
  await page.locator('.anime-title').first().click();
  await page.getByRole('button', { name: '补充缺失 ID', exact: true }).click();
  await page.getByLabel('评分站点', { exact: true }).selectOption('filmarks');
  await page.getByLabel('动画 ID 或作品链接').fill('1/2');
  await expect(page.locator('#contribute-credit')).toHaveText('公开署名：verified-user');
  await page.getByRole('button', { name: '提交审核', exact: true }).click();
  await expect(page.locator('#contribute-result')).toContainText('评分已采集', { timeout: 10000 });
  await expect(page.locator('.detail-copy .contributor-credit')).toContainText('verified-user');
  await expect(page.locator('#contribute-quota')).toContainText('5 / 5');
  await page.screenshot({ path: `test-results/contribution-${test.info().project.name}.png` });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width);
  await page.getByRole('button', { name: '关闭投稿', exact: true }).click();
  await page.getByRole('button', { name: '关闭详情', exact: true }).click();
  await expect(page.locator('.anime-text .contributor-credit').first()).toContainText('verified-user');
  await page.getByRole('button', { name: '我的投稿', exact: true }).click();
  await expect(page.locator('#submission-history')).toContainText('审核通过');
  expect(errors).toEqual([]);
});

test('daily exhausted quota disables submission', async ({ page }) => {
  await mockAccount(page, { quota: { ...quota, errors: 5, remaining: 0 } });
  await page.route('**/api/v1/contributions?**', route => route.fulfill({ json: { items: [], quota: { ...quota, remaining: 0 } } }));
  await page.route('**/api/v1/dashboard/anime/*?**', async route => {
    const response = await route.fetch({ url: route.request().url().replace('refresh=true', 'refresh=false') }); const data = await response.json();
    data.mapping_sources.filmarks = 'missing'; delete data.ids.filmarks_id;
    await route.fulfill({ json: data });
  });
  await page.goto('/');
  await page.locator('.anime-title').first().click();
  await page.getByRole('button', { name: '补充缺失 ID', exact: true }).click();
  await expect(page.locator('#contribute-quota')).toContainText('0 / 5');
  await expect(page.getByRole('button', { name: '提交审核', exact: true })).toBeDisabled();
});

test('administrator manages roles and adopts uncertain submission', async ({ page }) => {
  await mockAccount(page, { user: { ...user, role: 'admin' } });
  const members = [{ ...user, role: 'admin' }, { id: 72, username: 'contributor-two', nickname: '第二位用户', role: 'user' }];
  let approved = false;
  await page.route('**/api/v1/admin/users?**', route => route.fulfill({ json: { items: members } }));
  await page.route('**/api/v1/admin/users/72/role', async route => {
    expect(route.request().headers()['x-csrf-token']).toBe('test-csrf');
    members[1].role = route.request().postDataJSON().role;
    await route.fulfill({ json: { ok: true } });
  });
  await page.route('**/api/v1/admin/contributions?**', route => route.fulfill({ json: { items: [{ id: 'review1', catalog_id: '00000000000000000001', anime_name: '待确认动画 第二季', user_id: 72, username: 'contributor-two', provider: 'filmarks', identifier: '1/2', url: 'https://filmarks.com/animes/1/2', status: approved ? 'accepted' : 'uncertain', reason: '名称相近，季度信息需要人工核对', evidence: { titles: ['待确认动画 第二季'], date: '2026-07-05', format: 'TV', episodes: 12 } }] } }));
  await page.route('**/api/v1/admin/contributions/review1/approve', async route => { approved = true; expect(route.request().headers()['x-csrf-token']).toBe('test-csrf'); await route.fulfill({ json: { status: 'accepted' } }); });
  await page.goto('/admin');
  await page.getByText('用户与投稿管理', { exact: true }).click();
  await page.getByLabel('contributor-two的权限').selectOption('admin');
  await expect(page.locator('#community-admin-notice')).toContainText('用户权限已更新');
  await page.getByRole('button', { name: '投稿审核', exact: true }).click();
  await page.getByText('核对依据', { exact: true }).click();
  await expect(page.locator('.review-evidence')).toContainText('2026-07-05');
  await page.screenshot({ path: `test-results/community-admin-${test.info().project.name}.png` });
  await page.getByRole('button', { name: '确认匹配并采纳', exact: true }).click();
  await expect(page.locator('#review-list')).toContainText('审核通过');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize().width);
});
