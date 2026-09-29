import { createIcons, Layers3, ArrowLeft, ArrowRight, ArrowUpRight, Download, LogOut, Search, RefreshCw, ChevronLeft, ChevronRight, Pencil, X, Save, KeyRound, Check, Sparkles, Square } from 'lucide';
import { initCommunity, account, refreshAccount, communityIcons, submissionStates } from './community.js';
const iconSet = { ...communityIcons, Layers3, ArrowLeft, ArrowRight, ArrowUpRight, Download, LogOut, Search, RefreshCw, ChevronLeft, ChevronRight, Pencil, X, Save, KeyRound, Check, Sparkles, Square };
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const escape = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
const icons = () => createIcons({ icons: iconSet, attrs: { 'aria-hidden': 'true' } });
const origins = { catalog: '目录映射', manual: '人工指定', auto: '自动匹配', community: '用户贡献', disabled: '已禁用', missing: '缺失' };
const matchNames = { unchecked: '尚未匹配', applied: '已自动保存', matched: '确定匹配', review: '待确认', not_found: '未找到', error: '检索失败', conflict: 'ID 冲突', skipped: '已跳过' };
const jobNames = { idle: '待启动', queued: '排队中', running: '匹配中', completed: '已完成', cancelled: '已停止', failed: '任务中断' };
let jobState = null, jobConfigured = false;
let adminMode = null, membersOffset = 0, reviewsOffset = 0;
let token = ''; try { token = sessionStorage.getItem('animescore.admin-token') || ''; } catch {}
let providers = [], active = null, offset = 0, total = 0, listRequest = 0, editorRequest = 0;
const limit = 20;
function notice(text, target = '#admin-notice', error = false) { const node = $(target); node.textContent = text; node.hidden = !text; node.classList.toggle('error', error); }
async function api(path, options = {}) {
  const response = await fetch(`/api/v1/admin${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...(account.csrf_token ? { 'X-CSRF-Token': account.csrf_token } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}), ...options.headers } });
  const data = await response.json();
  if (!response.ok) { const error = new Error(typeof data.detail === 'string' ? data.detail : `请求失败 (${response.status})`); error.status = response.status; throw error; }
  return data;
}
async function connect() {
  try {
    await refreshAccount().catch(() => {});
    const data = await api('/status'); providers = data.providers;
    adminMode = data.mode;
    $('#auth-mode').textContent = data.mode === 'local' ? '本机管理' : '管理员已连接';
    $('#logout').hidden = data.mode !== 'token'; $('#login-form').hidden = true; $('#workspace').hidden = false;
    $('#missing').innerHTML = '<option value="">全部映射</option>' + providers.map(p => `<option value="${p.key}">缺失 ${escape(p.name)} ID</option>`).join('');
    notice(''); await load(); await loadJob();
  } catch (error) { $('#login-form').hidden = false; $('#workspace').hidden = true; notice(error.message, '#admin-notice', true); }
}
async function load() {
  const request = ++listRequest;
  $('#mapping-table').setAttribute('aria-busy', 'true');
  try {
    const params = new URLSearchParams({ q: $('#mapping-query').value.trim(), missing: $('#missing').value, edited: $('#edited').checked, filmarks_status: $('#filmarks-filter').value, limit, offset });
    const data = await api(`/mappings?${params}`);
    if (request !== listRequest) return;
    total = data.total;
    $('#mapping-count').textContent = `${total.toLocaleString()} 部动画`;
    $('#mapping-page-info').textContent = total ? `${offset + 1}–${Math.min(offset + limit, total)} / ${total}` : '暂无结果';
    $('#mapping-page').textContent = `${Math.floor(offset / limit) + 1} / ${Math.max(1, Math.ceil(total / limit))}`;
    $('#previous').disabled = offset === 0; $('#next').disabled = offset + limit >= total;
    $('#mapping-table').innerHTML = data.items.length ? `<table class="mapping-table"><thead><tr><th>动画</th>${providers.map(p => `<th>${escape(p.name)}</th>`).join('')}<th><span class="sr-only">操作</span></th></tr></thead><tbody>${data.items.map(item => `<tr><td><div class="mapping-name">${escape(item.name_cn || item.name)}</div><div class="mapping-meta">${escape(item.name)} · ${item.time?.year || '日期待定'} · ${escape(item.type.toUpperCase())}</div></td>${providers.map(p => `<td><span class="mapping-id">${escape(item.ids[p.field] || '—')}</span><span class="mapping-origin ${item.mapping_sources[p.key]}">${origins[item.mapping_sources[p.key]]}</span></td>`).join('')}<td><button class="icon-button" data-edit="${item.catalog_id}" title="编辑映射" aria-label="编辑 ${escape(item.name_cn || item.name)}"><i data-lucide="pencil"></i></button></td></tr>`).join('')}</tbody></table>` : '<div class="empty-mappings">没有符合条件的动画</div>';
    icons(); notice('');
  } catch (error) { if (request === listRequest) notice(error.message, '#admin-notice', true); }
  finally { if (request === listRequest) $('#mapping-table').removeAttribute('aria-busy'); }
}
function searchUrl(p, title) {
  const q = encodeURIComponent(title);
  return { bgm: `https://bgm.tv/subject_search/${q}?cat=2`, mal: `https://myanimelist.net/anime.php?q=${q}`, anilist: `https://anilist.co/search/anime?search=${q}`, filmarks: `https://filmarks.com/search/animes?q=${q}`, anikore: `https://www.anikore.jp/anime_title/${q}/` }[p];
}
function displayAudit() {
  $('#mapping-audit').innerHTML = active.audit.length ? active.audit.map(event => {
    const changes = providers.filter(p => JSON.stringify(event.before[p.key]) !== JSON.stringify(event.after[p.key]));
    return `<div class="audit-entry"><time>${escape(new Date(event.timestamp * 1000).toLocaleString('zh-CN'))}</time>${changes.map(p => {
      const before = event.before[p.key], after = event.after[p.key];
      const label = value => value ? value.id || '禁用映射' : '跟随目录';
      return `<p><strong>${escape(p.name)}</strong> · ${escape(label(before))} → ${escape(label(after))}${after?.note ? `<br>${escape(after.note)}` : ''}</p>`;
    }).join('')}</div>`;
  }).join('') : '<div class="empty-mappings">暂无修改记录</div>';
}
function renderEditor() {
  const { item, overrides, revision } = active;
  $('#mapping-title').textContent = item.name_cn || item.name;
  $('#mapping-original').textContent = `${item.name} · ${item.time?.year || '日期待定'} · ${item.type.toUpperCase()}`;
  $('#revision').textContent = `版本 ${revision}`;
  $('#mapping-fields').innerHTML = providers.map(p => {
    const override = overrides[p.key], mode = override ? override.id ? 'manual' : 'disabled' : 'catalog';
    return `<section class="mapping-field" data-provider="${p.key}"><div class="mapping-field-head"><label for="id-${p.key}"><span class="provider-dot" style="background:${p.color}"></span>${escape(p.name)}</label><a href="${escape(searchUrl(p.key, item.name))}" target="_blank" rel="noopener">站内检索<i data-lucide="arrow-up-right"></i></a></div><div class="mapping-inputs"><select data-mode="${p.key}" aria-label="${escape(p.name)}映射方式"><option value="catalog" ${mode === 'catalog' ? 'selected' : ''}>跟随目录</option><option value="manual" ${mode === 'manual' ? 'selected' : ''}>人工指定</option><option value="disabled" ${mode === 'disabled' ? 'selected' : ''}>禁用映射</option></select><input id="id-${p.key}" data-id="${p.key}" aria-label="${escape(p.name)} ID" value="${escape(override?.id || item.base_ids[p.field] || '')}" placeholder="${escape(p.example)} 或作品链接" maxlength="300" ${mode !== 'manual' ? 'disabled' : ''}><button type="button" class="button secondary" data-validate="${p.key}" ${mode !== 'manual' ? 'disabled' : ''}><i data-lucide="check"></i>校验</button></div><div class="mapping-base">目录 ID：${escape(item.base_ids[p.field] || '缺失')}</div><input class="mapping-note" data-note="${p.key}" aria-label="${escape(p.name)}修改备注" placeholder="修改备注（可选）" maxlength="500" value="${escape(override?.note || '')}"><div class="validation-result" data-result="${p.key}" role="status"></div></section>`;
  }).join('');
  const field = $('[data-provider="filmarks"]');
  field.insertAdjacentHTML('beforeend', '<div class="candidate-heading"><strong>自动检索候选</strong><button id="discover-filmarks" type="button" class="button secondary"><i data-lucide="search"></i>查找候选</button></div><div id="filmarks-candidates" aria-live="polite"></div>');
  if (overrides.filmarks?.source === 'auto') field.querySelector('.mapping-base').append(' · 当前为自动匹配');
  renderCandidates(active.filmarks_match);
  notice('', '#editor-notice'); displayAudit(); icons();
}
async function openEditor(id) {
  const request = ++editorRequest;
  try {
    const data = await api(`/mappings/${id}`);
    if (request !== editorRequest) return;
    active = data; renderEditor(); setTab('fields'); $('#save-mapping').disabled = false; $('#collect').disabled = false; $('#mapping-dialog').showModal();
  } catch (error) { if (request === editorRequest) notice(error.message, '#admin-notice', true); }
}
function setTab(tab) { $('#mapping-form').hidden = tab !== 'fields'; $('#mapping-audit').hidden = tab !== 'audit'; $$('[data-tab]').forEach(b => b.classList.toggle('selected', b.dataset.tab === tab)); }
async function validate(provider) {
  const input = $(`[data-id="${provider}"]`), value = input.value, result = $(`[data-result="${provider}"]`), button = $(`[data-validate="${provider}"]`);
  button.disabled = true; result.textContent = '正在核对作品…'; result.classList.remove('error');
  try {
    const data = await api('/validate', { method: 'POST', body: JSON.stringify({ provider, id: value }) });
    if (!input.isConnected || input.value !== value) return;
    const available = ['ok', 'no_score'].includes(data.status);
    result.classList.toggle('error', !available);
    result.textContent = available ? `${data.title || '站点未返回作品名'} · ${data.score == null ? '暂无评分' : `${data.score.toFixed(2)} / 10`} · ${data.votes == null ? '评价人数未知' : `${data.votes.toLocaleString()} 人次`}` : `校验未完成：${data.error || data.status}，请通过站内链接确认作品。`;
    if (available) input.value = data.id;
  } catch (error) { if (input.isConnected && input.value === value) { result.textContent = error.message; result.classList.add('error'); } }
  finally { if (button.isConnected) button.disabled = $(`[data-mode="${provider}"]`).value !== 'manual'; }
}
$('#mapping-form').addEventListener('submit', async event => {
  event.preventDefault(); if (!active) return;
  const request = editorRequest;
  const button = $('#save-mapping'); button.disabled = true;
  try {
    const changes = Object.fromEntries(providers.map(p => [p.key, { mode: $(`[data-mode="${p.key}"]`).value, id: $(`[data-id="${p.key}"]`).value.trim(), note: $(`[data-note="${p.key}"]`).value.trim() }]).filter(([key, change]) => {
      const before = active.overrides[key], mode = before ? before.id ? 'manual' : 'disabled' : 'catalog';
      return change.mode !== mode || (change.mode === 'manual' && change.id !== before?.id) || (change.mode !== 'catalog' && change.note !== (before?.note || ''));
    }));
    if (!Object.keys(changes).length) { notice('映射没有变化', '#editor-notice'); return; }
    const data = await api(`/mappings/${active.item.catalog_id}`, { method: 'PUT', body: JSON.stringify({ revision: active.revision, changes }) });
    if (request === editorRequest) { active = data; renderEditor(); notice('映射已保存，评分采集将使用当前 ID。', '#editor-notice'); }
    await load();
  } catch (error) { if (request === editorRequest) notice(error.message, '#editor-notice', true); }
  finally { if (request === editorRequest) button.disabled = false; }
});
$('#collect').addEventListener('click', async () => {
  if (!active) return;
  const request = editorRequest;
  const id = active.item.catalog_id; $('#collect').disabled = true; notice('正在采集已保存映射的评分…', '#editor-notice');
  try {
    const data = await api(`/mappings/${id}/collect`, { method: 'POST' });
    if (request !== editorRequest) return;
    notice(providers.map(p => `${p.name}：${data.scores[p.key] == null ? ({ unmapped: '缺少映射', unavailable: '暂不可用', no_score: '暂无评分' }[data.score_status[p.key]?.status] || '未采集') : data.scores[p.key].toFixed(2)}`).join('；'), '#editor-notice');
  } catch (error) { if (request === editorRequest) notice(error.message, '#editor-notice', true); }
  finally { if (request === editorRequest) $('#collect').disabled = false; }
});
document.addEventListener('click', event => {
  const edit = event.target.closest('[data-edit]'); if (edit) openEditor(edit.dataset.edit);
  const validation = event.target.closest('[data-validate]'); if (validation) validate(validation.dataset.validate);
  const tab = event.target.closest('[data-tab]'); if (tab) setTab(tab.dataset.tab);
  if (event.target.closest('#discover-filmarks')) discoverCandidates();
  const candidate = event.target.closest('[data-use-candidate]'); if (candidate) {
    const data = active?.filmarks_match?.candidates.find(value => value.id === candidate.dataset.useCandidate);
    if (data) {
      const mode = $('[data-mode="filmarks"]'); mode.value = 'manual'; mode.dispatchEvent(new Event('change', { bubbles: true }));
      $('#id-filmarks').value = data.id; $('[data-note="filmarks"]').value = `人工确认候选：${data.title}；${data.reasons.join('；')}`.slice(0, 500);
      notice('候选 ID 已填入，尚未保存', '#editor-notice');
    }
  }
});
$('#mapping-fields').addEventListener('change', event => { const p = event.target.dataset.mode; if (p) { $(`[data-id="${p}"]`).disabled = event.target.value !== 'manual'; $(`[data-validate="${p}"]`).disabled = event.target.value !== 'manual'; $(`[data-result="${p}"]`).textContent = ''; } });
$('#mapping-fields').addEventListener('input', event => { const p = event.target.dataset.id; if (p) $(`[data-result="${p}"]`).textContent = ''; });
$('#close-mapping').addEventListener('click', () => $('#mapping-dialog').close());
$('#mapping-dialog').addEventListener('close', () => { editorRequest++; active = null; });
$('#mapping-search').addEventListener('submit', event => { event.preventDefault(); offset = 0; load(); });
['missing', 'edited', 'filmarks-filter'].forEach(id => $(`#${id}`).addEventListener('change', () => { offset = 0; load(); }));
$('#reload').addEventListener('click', load);
$('#previous').addEventListener('click', () => { offset = Math.max(0, offset - limit); load(); });
$('#next').addEventListener('click', () => { offset += limit; load(); });
$('#login-form').addEventListener('submit', event => { event.preventDefault(); token = $('#admin-token').value.trim(); try { sessionStorage.setItem('animescore.admin-token', token); } catch {} connect(); });
$('#logout').addEventListener('click', () => { token = ''; try { sessionStorage.removeItem('animescore.admin-token'); } catch {} $('#admin-token').value = ''; connect(); });
$('#export').addEventListener('click', async () => {
  try { const data = await api('/mappings/export'); const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); const a = document.createElement('a'); a.href = url; a.download = `animescore-mappings-${new Date().toISOString().slice(0, 10)}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
  catch (error) { notice(error.message, '#admin-notice', true); }
});
function renderCandidates(result) {
  const candidates = result?.candidates || [];
  $('#filmarks-candidates').innerHTML = `<div class="candidate-state">${escape(matchNames[result?.status] || '尚未匹配')}${result?.checked_at ? ` · ${new Date(result.checked_at * 1000).toLocaleString('zh-CN')}` : ''}</div>${candidates.map(candidate => `<div class="mapping-candidate"><div><a href="${escape(candidate.url)}" target="_blank" rel="noopener">${escape(candidate.title)}<i data-lucide="arrow-up-right"></i></a><div class="candidate-meta">${escape(candidate.id)} · ${escape(candidate.date || '日期未知')} · ${escape(candidate.method || '')}</div><p>${escape(candidate.reasons.join('；'))}</p></div><button type="button" class="icon-button" data-use-candidate="${escape(candidate.id)}" aria-label="采用候选 ${escape(candidate.title)}" title="填入候选 ID"><i data-lucide="check"></i></button></div>`).join('')}${result?.errors?.length ? `<div class="candidate-errors">${result.errors.map(escape).join('<br>')}</div>` : ''}`;
}
async function discoverCandidates() {
  if (!active) return;
  const request = editorRequest, button = $('#discover-filmarks'); button.disabled = true;
  $('#filmarks-candidates').textContent = '正在检索并核对作品…';
  try {
    const result = await api(`/filmarks/discover/${active.item.catalog_id}`, { method: 'POST' });
    if (request !== editorRequest) return;
    active.filmarks_match = result; renderCandidates(result); icons();
  } catch (error) { if (request === editorRequest) $('#filmarks-candidates').textContent = error.message; }
  finally { if (button.isConnected) button.disabled = false; }
}
async function loadJob() {
  if ($('#workspace').hidden) return;
  try {
    const data = await api('/filmarks/job');
    const running = ['queued', 'running'].includes(data.status);
    if (!jobConfigured) { $('#batch-year').value = data.current_year; $('#batch-season').value = data.current_season; jobConfigured = true; }
    $('#job-state').textContent = jobNames[data.status] || data.status;
    $('#start-mapping').disabled = running; $('#stop-mapping').disabled = !running || data.cancel_requested;
    $('#job-progress').max = data.total || 1; $('#job-progress').value = data.completed || 0;
    $('#job-counts').textContent = `${data.completed || 0} / ${data.total || 0}` + Object.entries(data.counts || {}).map(([key, value]) => ` · ${matchNames[key] || key} ${value}`).join('');
    $('#job-current').textContent = data.cancel_requested && running ? '正在停止当前任务…' : data.current || '';
    notice(data.error || '', '#job-notice', !!data.error);
    $('#job-recent').innerHTML = (data.recent || []).slice(0, 4).map(item => `<div><button type="button" data-edit="${escape(item.catalog_id)}">${escape(item.name)}</button><span>${escape(matchNames[item.status] || item.status)}</span></div>`).join('');
    if (jobState && jobState !== data.status && !running) await load();
    jobState = data.status;
  } catch (error) { notice(error.message, '#job-notice', true); }
}
$('#batch-scope').addEventListener('change', () => { const all = $('#batch-scope').value === 'missing'; $('#batch-year').disabled = all; $('#batch-season').disabled = all; });
$('#mapping-batch').addEventListener('submit', async event => {
  event.preventDefault(); $('#start-mapping').disabled = true;
  try {
    await api('/filmarks/job', { method: 'POST', body: JSON.stringify({ scope: $('#batch-scope').value, year: Number($('#batch-year').value), season: $('#batch-season').value, limit: Number($('#batch-limit').value), apply: $('#batch-apply').checked }) });
    await loadJob();
  } catch (error) { notice(error.message, '#job-notice', true); $('#start-mapping').disabled = false; }
});
$('#stop-mapping').addEventListener('click', async () => { try { await api('/filmarks/job/cancel', { method: 'POST' }); await loadJob(); } catch (error) { notice(error.message, '#job-notice', true); } });
setInterval(loadJob, 3000);
async function loadMembers() {
  try {
    const data = await api(`/users?${new URLSearchParams({ q: $('#member-query').value.trim(), offset: membersOffset })}`);
    $('#member-list').innerHTML = data.items.length ? `<table class="member-table"><thead><tr><th>UID</th><th>Bangumi 用户</th><th>权限</th></tr></thead><tbody>${data.items.map(user => `<tr><td>${user.id}</td><td><a href="https://bgm.tv/user/${user.id}" target="_blank" rel="noopener">${escape(user.username)}</a><span class="mapping-origin">${escape(user.nickname)}</span></td><td><select data-user-role="${user.id}" aria-label="${escape(user.username)}的权限"><option value="user" ${user.role === 'user' ? 'selected' : ''}>普通用户</option><option value="admin" ${user.role === 'admin' ? 'selected' : ''}>管理员</option></select></td></tr>`).join('')}</tbody></table>` : '<p class="community-empty">暂无已登录用户</p>';
    $('#members-prev').disabled = membersOffset === 0; $('#members-next').disabled = data.items.length < 50;
  } catch (error) { notice(error.message, '#community-admin-notice', true); }
}
function reviewEvidence(record) {
  const evidence = record.evidence || {};
  const date = typeof evidence.date === 'object' && evidence.date ? [evidence.date.year, evidence.date.month, evidence.date.day].map(value => value || '?').join('-') : evidence.date;
  return [['站点作品名', (evidence.titles || []).join(' / ')], ['开播日期', date], ['作品类型', evidence.format], ['集数', evidence.episodes]].map(([label, value]) => `<div>${label}：${escape(value || '未知')}</div>`).join('');
}
async function loadReviews() {
  try {
    const data = await api(`/contributions?offset=${reviewsOffset}`);
    $('#review-list').innerHTML = data.items.length ? data.items.map(record => `<article class="review-row"><header><button class="review-name" data-edit="${record.catalog_id}">${escape(record.anime_name)}</button><span class="submission-state ${record.status}">${submissionStates[record.status]}</span></header><p><a href="https://bgm.tv/user/${record.user_id}" target="_blank" rel="noopener">${escape(record.username)}</a> · ${escape(providers.find(p => p.key === record.provider)?.name)} · <a href="${escape(record.url)}" target="_blank" rel="noopener">${escape(record.identifier)} <i data-lucide="arrow-up-right"></i></a></p><p>${escape(record.reason || '正在等待审核')}</p><details><summary>核对依据</summary><div class="review-evidence">${reviewEvidence(record)}</div></details>${['uncertain', 'error', 'rejected'].includes(record.status) ? `<div class="review-actions"><button class="button secondary" data-approve-submission="${record.id}"><i data-lucide="check"></i>确认匹配并采纳</button></div>` : ''}</article>`).join('') : '<p class="community-empty">暂无投稿记录</p>';
    $('#reviews-prev').disabled = reviewsOffset === 0; $('#reviews-next').disabled = data.items.length < 50; icons();
  } catch (error) { notice(error.message, '#community-admin-notice', true); }
}
$('#community-management').addEventListener('toggle', () => { if ($('#community-management').open) { loadMembers(); loadReviews(); } });
$('#member-search').addEventListener('submit', event => { event.preventDefault(); membersOffset = 0; loadMembers(); });
$('#member-list').addEventListener('change', async event => {
  const id = event.target.dataset.userRole; if (!id) return;
  event.target.disabled = true;
  try { await api(`/users/${id}/role`, { method: 'PUT', body: JSON.stringify({ role: event.target.value }) }); notice('用户权限已更新', '#community-admin-notice'); await refreshAccount(); if (adminMode === 'bangumi' && account.user?.role !== 'admin') await connect(); }
  catch (error) { notice(error.message, '#community-admin-notice', true); }
  await loadMembers();
});
$('#review-list').addEventListener('click', async event => {
  const button = event.target.closest('[data-approve-submission]'); if (!button) return;
  button.disabled = true;
  try { await api(`/contributions/${button.dataset.approveSubmission}/approve`, { method: 'POST' }); notice('投稿已采纳，已保留署名并安排评分采集', '#community-admin-notice'); await loadReviews(); await load(); }
  catch (error) { notice(error.message, '#community-admin-notice', true); button.disabled = false; }
});
for (const tab of $$('[data-community-tab]')) tab.addEventListener('click', () => { const members = tab.dataset.communityTab === 'members'; $('#members-panel').hidden = !members; $('#reviews-panel').hidden = members; $$('[data-community-tab]').forEach(t => t.classList.toggle('selected', t === tab)); });
for (const [id, delta] of [['members-prev', -50], ['members-next', 50]]) $(`#${id}`).addEventListener('click', () => { membersOffset = Math.max(0, membersOffset + delta); loadMembers(); });
for (const [id, delta] of [['reviews-prev', -50], ['reviews-next', 50], ['reload-reviews', 0]]) $(`#${id}`).addEventListener('click', () => { reviewsOffset = Math.max(0, reviewsOffset + delta); loadReviews(); });
window.addEventListener('account-changed', () => { if (adminMode === 'bangumi' && !account.user) { $('#workspace').hidden = true; $('#login-form').hidden = false; } });
window.addEventListener('open-submitted-anime', event => openEditor(event.detail));
icons(); initCommunity(); connect();
