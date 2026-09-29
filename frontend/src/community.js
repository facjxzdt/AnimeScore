import { createIcons, LogIn, LogOut, UserRound, ListChecks, X, Send, RefreshCw } from 'lucide';

const $ = selector => document.querySelector(selector);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
export const communityIcons = { LogIn, LogOut, UserRound, ListChecks, X, Send, RefreshCw };
const icons = () => createIcons({ icons: communityIcons, attrs: { 'aria-hidden': 'true' } });
const names = { bgm: 'Bangumi', mal: 'MyAnimeList', anilist: 'AniList', filmarks: 'Filmarks', anikore: 'Anikore' };
export const submissionStates = { queued: '等待审核', reviewing: '正在核对', accepted: '审核通过', rejected: '映射不正确', uncertain: '待管理员确认', error: '审核暂不可用', conflict: '映射已变更' };
export const account = { user: null, csrf_token: null, login_enabled: false, review_enabled: false, quota: null };
let activeItem = null, poll = null, activeSubmission = null, signature = '', historyOffset = 0;

export async function accountRequest(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(account.csrf_token ? { 'X-CSRF-Token': account.csrf_token } : {}), ...options.headers } });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `请求失败 (${response.status})`);
  return data;
}

export function contributorCaption(item) {
  const entries = Object.entries(item.mapping_contributors || {}).filter(([, person]) => Number.isSafeInteger(person.bgm_id) && person.bgm_id > 0);
  if (!entries.length) return '';
  return `<small class="contributor-credit">ID 提交：${entries.map(([provider, person]) => `<a href="https://bgm.tv/user/${person.bgm_id}" target="_blank" rel="noopener" title="${escape(names[provider])} ID 提交者">${escape(person.username)}</a>`).join(' · ')}</small>`;
}

export async function refreshAccount() {
  Object.assign(account, await accountRequest('/auth/me'));
  renderAccount();
  window.dispatchEvent(new CustomEvent('account-changed'));
  return account;
}

function renderAccount() {
  const bar = $('#account-bar');
  if (!bar) return;
  bar.innerHTML = account.user ? `<span class="account-name"><i data-lucide="user-round"></i>${escape(account.user.username)}</span><span class="account-quota">今日错误机会 ${account.quota.remaining} / 5</span><button id="my-submissions" class="button secondary"><i data-lucide="list-checks"></i>我的投稿</button>${account.user.role === 'admin' ? '<a class="button secondary" href="/admin">管理后台</a>' : ''}<button id="bgm-logout" class="icon-button" title="退出登录" aria-label="退出 Bangumi 登录"><i data-lucide="log-out"></i></button>` : account.login_enabled ? `<a id="bgm-login" class="button secondary" href="/api/v1/auth/bangumi/login?return_to=${location.pathname === '/admin' ? '/admin' : '/'}"><i data-lucide="log-in"></i>Bangumi 登录</a>` : '<span class="account-unavailable">Bangumi 登录未配置</span>';
  icons();
}

function recordMarkup(record) {
  const scoreLabel = record.status === 'accepted' ? { pending: '评分待采集', collecting: '正在采集评分', ok: '评分已采集', no_score: '站点暂无评分', unavailable: '评分暂不可用，将自动重试', stale: '保留缓存评分', mapping_changed: '映射已由管理员更改' }[record.score_status] || '' : '';
  return `<div class="submission-record"><div><strong>${escape(names[record.provider])}</strong> <a href="${escape(record.url)}" target="_blank" rel="noopener">${escape(record.identifier)}</a><span class="submission-state ${record.status}">${submissionStates[record.status]}</span></div><p>${escape(record.reason || '正在等待后台处理')}</p>${scoreLabel ? `<small>${scoreLabel}</small>` : ''}<time>${new Date(record.created_at * 1000).toLocaleString('zh-CN')}</time></div>`;
}

async function loadHistory() {
  const data = await accountRequest(`/contributions?offset=${historyOffset}`);
  $('#submission-history').innerHTML = data.items.length ? data.items.map(record => `<div class="history-submission"><button class="text-button" data-open-submitted-anime="${escape(record.catalog_id)}">${escape(record.anime_name || record.catalog_id)}</button>${recordMarkup(record)}</div>`).join('') : '<p class="community-empty">暂无投稿</p>';
  $('#submission-previous').disabled = historyOffset === 0;
  $('#submission-next').disabled = data.items.length < 50;
}

function setFormState() {
  if (!$('#contribute-submit')) return;
  $('#contribute-submit').disabled = !account.user || !account.review_enabled || account.quota?.remaining === 0 || account.quota?.pending || !!activeSubmission;
  $('#contribute-quota').textContent = account.quota ? `今日剩余错误机会 ${account.quota.remaining} / 5 · 北京时间 00:00 重置` : '';
}

function stopPoll() { clearInterval(poll); poll = null; activeSubmission = null; }
async function pollSubmission() {
  if (!activeSubmission) return;
  const id = activeSubmission;
  try {
    const data = await accountRequest(`/contributions/${id}`);
    if (activeSubmission !== id) return;
    const record = data.submission;
    $('#contribute-result').innerHTML = recordMarkup(record);
    account.quota = data.quota; renderAccount();
    const nextSignature = `${record.status}:${record.score_status}`;
    if (record.status === 'accepted' && signature !== nextSignature) {
      window.dispatchEvent(new CustomEvent('mapping-submitted', { detail: record.catalog_id }));
      $(`#contribute-provider option[value="${record.provider}"]`)?.remove();
      $('#contribute-id').value = '';
      if (!$('#contribute-provider').options.length) $('#contribute-form').hidden = true;
    }
    signature = nextSignature;
    if (!['queued', 'reviewing'].includes(record.status) && !['pending', 'collecting'].includes(record.score_status)) {
      stopPoll(); await refreshAccount();
    }
    setFormState();
  } catch (error) {
    if (activeSubmission !== id) return;
    stopPoll(); $('#contribute-notice').textContent = `${error.message}；可在“我的投稿”查看结果。`; setFormState();
  }
}

export async function openSubmission(item) {
  stopPoll(); activeItem = item; signature = '';
  $('#contribute-title').textContent = `补充 ID · ${item.name_cn || item.name}`;
  $('#contribute-result').innerHTML = ''; $('#contribute-notice').textContent = ''; $('#contribute-id').value = '';
  if (!$('#contribute-dialog').open) $('#contribute-dialog').showModal();
  try {
    await refreshAccount();
    if (activeItem !== item) return;
    const missing = Object.keys(names).filter(p => item.mapping_sources?.[p] === 'missing');
    $('#contribute-provider').innerHTML = missing.map(p => `<option value="${p}">${names[p]}</option>`).join('');
    $('#contribute-form').hidden = !account.user || !missing.length;
    $('#contribute-login').hidden = !!account.user || !account.login_enabled;
    $('#contribute-notice').textContent = !account.user ? (account.login_enabled ? '请先登录 Bangumi' : 'Bangumi 登录尚未配置') : !missing.length ? '暂无可补充的站点' : !account.review_enabled ? '映射审核服务尚未配置' : '';
    $('#contribute-credit').textContent = account.user ? `公开署名：${account.user.username}` : '';
    if (account.user) {
      const data = await accountRequest(`/contributions?catalog_id=${item.catalog_id}`);
      if (activeItem !== item) return;
      $('#contribute-result').innerHTML = data.items.slice(0, 3).map(recordMarkup).join('');
      const pending = data.items.find(value => ['queued', 'reviewing'].includes(value.status) || ['pending', 'collecting'].includes(value.score_status));
      if (pending) { activeSubmission = pending.id; poll = setInterval(pollSubmission, 2000); }
    }
    setFormState(); icons();
  } catch (error) { if (activeItem === item) $('#contribute-notice').textContent = error.message; }
}

export function initCommunity() {
  document.body.insertAdjacentHTML('beforeend', `<dialog id="contribute-dialog" class="community-dialog" aria-labelledby="contribute-title"><div class="dialog-top"><h2 id="contribute-title">补充站点 ID</h2><button class="icon-button" data-close-community="contribute-dialog" aria-label="关闭投稿" title="关闭"><i data-lucide="x"></i></button></div><div class="community-body"><p id="contribute-notice" role="status"></p><a id="contribute-login" class="button primary" href="/api/v1/auth/bangumi/login"><i data-lucide="log-in"></i>Bangumi 登录</a><form id="contribute-form" hidden><label for="contribute-provider">评分站点</label><select id="contribute-provider"></select><label for="contribute-id">动画 ID 或作品链接</label><input id="contribute-id" maxlength="300" required autocomplete="off"><div class="submission-meta"><span id="contribute-credit"></span><span id="contribute-quota"></span></div><button id="contribute-submit" class="button primary" type="submit"><i data-lucide="send"></i>提交审核</button></form><div id="contribute-result" aria-live="polite"></div></div></dialog><dialog id="my-submissions-dialog" class="community-dialog" aria-labelledby="submission-history-title"><div class="dialog-top"><h2 id="submission-history-title">我的投稿</h2><button class="icon-button" data-close-community="my-submissions-dialog" aria-label="关闭我的投稿" title="关闭"><i data-lucide="x"></i></button></div><div class="community-body"><button id="refresh-submissions" class="button secondary"><i data-lucide="refresh-cw"></i>刷新记录</button><div id="submission-history" aria-live="polite"></div><div class="submission-pagination"><button id="submission-previous" class="button secondary">上一页</button><button id="submission-next" class="button secondary">下一页</button></div></div></dialog>`);
  $('#contribute-dialog').addEventListener('close', () => { stopPoll(); activeItem = null; });
  $('#contribute-form').addEventListener('submit', async event => {
    event.preventDefault(); if (!activeItem || activeSubmission) return;
    const item = activeItem;
    $('#contribute-submit').disabled = true;
    try {
      const data = await accountRequest('/contributions', { method: 'POST', body: JSON.stringify({ catalog_id: item.catalog_id, provider: $('#contribute-provider').value, id: $('#contribute-id').value.trim() }) });
      if (activeItem !== item) return;
      activeSubmission = data.submission.id; account.quota = data.quota; signature = '';
      $('#contribute-notice').textContent = '';
      await pollSubmission();
      if (activeSubmission) poll = setInterval(pollSubmission, 2000);
    } catch (error) { if (activeItem === item) $('#contribute-notice').textContent = error.message; await refreshAccount().catch(() => {}); }
    setFormState();
  });
  document.addEventListener('click', async event => {
    const close = event.target.closest('[data-close-community]'); if (close) $(`#${close.dataset.closeCommunity}`).close();
    if (event.target.closest('#bgm-logout')) {
      try { await accountRequest('/auth/logout', { method: 'POST' }); await refreshAccount(); if (activeItem) await openSubmission(activeItem); }
      catch (error) { $('#account-bar').textContent = error.message; }
    }
    if (event.target.closest('#my-submissions')) { historyOffset = 0; $('#my-submissions-dialog').showModal(); await loadHistory().catch(error => $('#submission-history').textContent = error.message); }
    const open = event.target.closest('[data-open-submitted-anime]');
    if (open) { $('#my-submissions-dialog').close(); window.dispatchEvent(new CustomEvent('open-submitted-anime', { detail: open.dataset.openSubmittedAnime })); }
  });
  for (const [id, delta] of [['submission-previous', -50], ['submission-next', 50], ['refresh-submissions', 0]]) {
    $(`#${id}`).addEventListener('click', async () => { historyOffset = Math.max(0, historyOffset + delta); await loadHistory().catch(error => $('#submission-history').textContent = error.message); });
  }
  const authError = new URLSearchParams(location.search).get('auth_error');
  refreshAccount().then(() => {
    if (authError) { const message = authError === 'cancelled' ? 'Bangumi 授权已取消' : 'Bangumi 登录暂时失败，请重试'; $('#account-bar').insertAdjacentHTML('afterbegin', `<span class="account-error">${message}</span>`); history.replaceState(null, '', location.pathname); }
  }).catch(() => { if ($('#account-bar')) $('#account-bar').textContent = '登录服务暂不可用'; });
}
