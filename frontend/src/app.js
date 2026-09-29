import { createIcons, Layers3, ChartNoAxesColumnIncreasing, ChartPie, Bookmark, Search, ArrowRight, RefreshCw, ChevronLeft, ChevronRight, SlidersHorizontal, RotateCcw, Check, ArrowUpRight, Clock3, Info, X, Download, Star, SearchX, LoaderCircle, Library, AlertCircle } from 'lucide';
import * as echarts from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, GraphicComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { initCommunity, openSubmission, contributorCaption, communityIcons } from './community.js';

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, GraphicComponent, CanvasRenderer]);
const iconSet = { ...communityIcons, Layers3, ChartNoAxesColumnIncreasing, ChartPie, Bookmark, Search, ArrowRight, RefreshCw, ChevronLeft, ChevronRight, SlidersHorizontal, RotateCcw, Check, ArrowUpRight, Clock3, Info, X, Download, Star, SearchX, LoaderCircle, Library, AlertCircle };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escape = (value) => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const icons = () => createIcons({ icons: iconSet, attrs: { 'aria-hidden': 'true' } });
const providers = ['bgm', 'mal', 'anilist', 'filmarks', 'anikore'];
const names = { bgm: 'Bangumi', mal: 'MyAnimeList', anilist: 'AniList', filmarks: 'Filmarks', anikore: 'Anikore', total: '综合评分' };
const colors = { bgm: '#dc7394', mal: '#417eb3', anilist: '#db9b41', filmarks: '#9a79ba', anikore: '#428d92', total: '#267453' };
const seasons = { winter: '冬季', spring: '春季', summer: '夏季', fall: '秋季' };
const DEFAULT = { bgm: 5, mal: 2, anilist: 0, filmarks: 0, anikore: 0 };
const stateNames = { ok: '已更新', no_score: '暂无评分', stale: '缓存过期', unavailable: '暂不可用', unmapped: '无站点映射', not_fetched: '待采集' };
const storage = {
  read(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } },
  write(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Browser storage may be unavailable. */ } },
};
function validWeights(value) { return value && providers.every(p => Number.isFinite(value[p]) && value[p] >= 0 && value[p] <= 100) && providers.some(p => value[p] > 0); }
const savedWeights = { ...DEFAULT, ...storage.read('animescore.weights', DEFAULT) };
const rememberedWeights = { ...storage.read('animescore.weight-values', {}) };
const storedFavorites = storage.read('animescore.favorites', []);
const state = { view: 'ranking', weights: validWeights(savedWeights) ? savedWeights : { ...DEFAULT }, draft: {}, favorites: new Set(Array.isArray(storedFavorites) ? storedFavorites.filter(id => typeof id === 'string') : []), year: null, season: null, type: '', query: '', offset: 0, limit: 12, minPlatforms: 0, minVotes: 0, data: null, status: null, selected: null, period: '7d', metric: 'scores', history: null };
let requestId = 0, detailId = 0, rankingController, toastTimer;
const charts = new Map();
const observer = new ResizeObserver(entries => entries.forEach(entry => charts.get(entry.target.id)?.resize()));

function safeUrl(url) { try { const parsed = new URL(url); return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : ''; } catch { return ''; } }
function count(value) { if (value === null || value === undefined) return '—'; return Number(value).toLocaleString('zh-CN'); }
function compact(value) { if (value === null || value === undefined) return '—'; return value >= 10000 ? `${(value / 10000).toFixed(1)}万` : count(value); }
function score(value) { return value == null ? '—' : Number(value).toFixed(2); }
function date(value, full = false) { if (!value) return '—'; return new Intl.DateTimeFormat('zh-CN', full ? { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false } : { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value)); }
function params(extra = {}) { return new URLSearchParams({ ...state.weights, ...extra }).toString(); }
async function api(path, options = {}) { const response = await fetch(`/api/v1/dashboard${path}`, options); if (!response.ok) { let message = `请求失败 (${response.status})`; try { const data = await response.json(); if (typeof data.detail === 'string') message = data.detail; } catch {} throw new Error(message); } return response.json(); }
function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 2800); }
function notice(message, error = false) { $('#notice').textContent = message; $('#notice').classList.toggle('error', error); $('#notice').hidden = !message; }
function isDefault(weights) { return providers.every(p => weights[p] === DEFAULT[p]); }
function isEqual(weights) { return weights.bgm > 0 && providers.every(p => weights[p] === weights.bgm); }

function renderWeightControls() {
  state.draft = { ...state.weights };
  $('#weight-controls').innerHTML = providers.map(p => `<div class="weight-control"><label class="weight-switch"><input type="checkbox" data-weight-enabled="${p}" aria-label="${names[p]}参与综合分"><span>计入综合分</span></label><label class="weight-label" for="weight-${p}"><span><span class="provider-dot ${p}"></span>${names[p]}</span><input id="weight-${p}" data-weight-number="${p}" aria-label="${names[p]}权重" type="number" min="0" max="100" step="0.5" value="${state.weights[p]}"></label><input data-weight-range="${p}" aria-label="${names[p]}权重滑块" type="range" min="0" max="100" step="0.5" value="${state.weights[p]}"><span class="weight-percent" id="percent-${p}"></span></div>`).join('');
  updateWeightDraft();
}
function updateWeightDraft() {
  const sum = providers.reduce((total, p) => total + state.draft[p], 0);
  providers.forEach(p => $(`#percent-${p}`).textContent = sum ? `${(state.draft[p] / sum * 100).toFixed(1)}%` : '0%');
  providers.forEach(p => {
    const enabled = state.draft[p] > 0;
    $(`[data-weight-enabled="${p}"]`).checked = enabled;
    $(`[data-weight-number="${p}"]`).disabled = !enabled;
    $(`[data-weight-range="${p}"]`).disabled = !enabled;
    $(`[data-weight-enabled="${p}"]`).closest('.weight-control').classList.toggle('weight-off', !enabled);
    if (enabled) rememberedWeights[p] = state.draft[p];
  });
  $('#weight-formula').textContent = providers.map(p => state.draft[p]).join(' : ');
  $('#weight-error').hidden = sum > 0;
  $('#apply-weights').disabled = !sum;
  $$('.weight-presets button').forEach(button => button.classList.toggle('selected', button.dataset.preset === 'default' ? isDefault(state.draft) : isEqual(state.draft)));
  $('#custom-label').hidden = isDefault(state.draft) || isEqual(state.draft);
}
function changeDraft(provider, value) {
  state.draft[provider] = Math.max(0, Math.min(100, Number(value) || 0));
  $(`[data-weight-number="${provider}"]`).value = state.draft[provider];
  $(`[data-weight-range="${provider}"]`).value = state.draft[provider];
  updateWeightDraft();
}
async function applyWeights() {
  if (!validWeights(state.draft)) return;
  state.weights = { ...state.draft };
  storage.write('animescore.weights', state.weights);
  storage.write('animescore.weight-values', rememberedWeights);
  state.offset = 0;
  await loadRanking();
  if (state.selected) {
    state.selected.scores.total = weighted(state.selected.scores);
    $('#detail-total').textContent = score(state.selected.scores.total);
    await loadHistory();
  }
  toast('权重已保存，综合分与排名已更新');
}
function weighted(scores) { const values = providers.filter(p => state.weights[p] > 0 && scores[p] != null); const divisor = values.reduce((sum, p) => sum + state.weights[p], 0); return divisor ? Math.round(values.reduce((sum, p) => sum + scores[p] * state.weights[p], 0) / divisor * 1000) / 1000 : null; }
function poster(item, className = 'poster') {
  const url = safeUrl(item.poster);
  return url ? `<img class="${className}" src="${escape(url)}" alt="${escape(item.name_cn || item.name)}海报" loading="lazy" referrerpolicy="no-referrer">` : `<span class="${className} poster-placeholder" aria-label="暂无海报"><i data-lucide="library"></i></span>`;
}
function empty(title, message, icon = 'search-x') { return `<div class="empty-state"><i data-lucide="${icon}"></i><h3>${escape(title)}</h3><p>${escape(message)}</p></div>`; }
function renderFavoritesCount() { $('#favorite-count').textContent = state.favorites.size; }
function toggleFavorite(id) {
  if (state.favorites.has(id)) state.favorites.delete(id); else state.favorites.add(id);
  storage.write('animescore.favorites', [...state.favorites]);
  renderFavoritesCount();
  $$(`[data-favorite="${id}"]`).forEach(button => { button.classList.toggle('saved', state.favorites.has(id)); button.setAttribute('aria-pressed', String(state.favorites.has(id))); button.title = state.favorites.has(id) ? '取消收藏' : '收藏动画'; });
  if (state.view === 'favorites') loadRanking();
}
function table(items) {
  if (!items.length) return empty(state.view === 'favorites' ? '还没有收藏的动画' : '没有找到符合条件的动画', state.view === 'favorites' ? '收藏的作品会显示在这里。' : '试试原名、其他译名，或调整筛选条件。');
  return `<table class="score-table"><thead><tr><th scope="col">排名</th><th scope="col">动画</th><th scope="col">综合评分</th>${providers.map(p => `<th scope="col"><span class="provider-dot ${p}"></span>${p === 'mal' ? 'MAL' : names[p]}</th>`).join('')}<th scope="col"><span class="sr-only">收藏</span></th></tr></thead><tbody>${items.map(item => `<tr data-anime="${escape(item.catalog_id)}"><td><span class="rank ${item.rank && item.rank <= 3 ? 'top' : ''}">${item.rank ? String(item.rank).padStart(2, '0') : '—'}</span></td><td><div class="anime-cell">${poster(item)}<div class="anime-text"><button class="anime-title" data-detail="${escape(item.catalog_id)}" title="${escape(item.name_cn || item.name)}">${escape(item.name_cn || item.name)}</button><div class="anime-original">${escape(item.name)}</div><div class="anime-meta"><span class="type-tag">${escape((item.type || '').toUpperCase())}</span><span>${item.time ? `${item.time.year}.${String(item.time.month).padStart(2, '0')}` : '日期待定'}</span>${item.episodes ? `<span>· ${item.episodes} 话</span>` : ''}</div></div></div></td><td><span class="composite">${score(item.scores.total)}</span><span class="score-caption">${item.coverage ?? providers.filter(p => item.scores[p] != null).length} / ${providers.length} 平台</span></td>${providers.map(p => `<td title="${escape(stateNames[item.score_status?.[p]?.status] || '待采集')}"><span class="platform-score">${score(item.scores[p])}</span><span class="platform-votes">${compact(item.votes?.[p])} 人次</span></td>`).join('')}<td><button class="icon-button favorite ${state.favorites.has(item.catalog_id) ? 'saved' : ''}" data-favorite="${escape(item.catalog_id)}" aria-label="收藏 ${escape(item.name_cn || item.name)}" aria-pressed="${state.favorites.has(item.catalog_id)}" title="${state.favorites.has(item.catalog_id) ? '取消收藏' : '收藏动画'}"><i data-lucide="bookmark"></i></button></td></tr>`).join('')}</tbody></table>`;
}
function renderData(data) {
  state.data = data;
  $('#metric-total').textContent = count(data.summary.total);
  $('#metric-rated').textContent = count(data.summary.rated);
  $('#metric-average').textContent = score(data.summary.average);
  $('#metric-votes').textContent = compact(data.summary.votes);
  $('#metric-coverage').textContent = data.summary.total ? `覆盖 ${(data.summary.rated / data.summary.total * 100).toFixed(0)}%` : '暂无评分';
  $('#ranking-table').innerHTML = table(data.items);
  for (const item of data.items) $(`[data-anime="${item.catalog_id}"] .anime-text`)?.insertAdjacentHTML('beforeend', contributorCaption(item));
  $('#result-count').textContent = `${count(data.total)} 部动画`;
  $('#page-info').textContent = data.total ? `显示 ${state.offset + 1}–${Math.min(state.offset + state.limit, data.total)}，共 ${data.total} 部` : '暂无结果';
  $('#page-number').textContent = `${Math.floor(state.offset / state.limit) + 1} / ${Math.max(1, Math.ceil(data.total / state.limit))}`;
  $('#prev').disabled = state.offset === 0;
  $('#next').disabled = state.offset + state.limit >= data.total;
  $('#list-title').textContent = state.query ? `“${state.query}” 的搜索结果` : state.view === 'favorites' ? '我的收藏' : isDefault(state.weights) ? '综合排名' : '个人加权排名';
  const seasonTitle = state.year === state.status?.current_year && state.season === state.status?.current_season ? '当季新番' : `${state.year} ${seasons[state.season]}`;
  $('#page-title').textContent = state.view === 'insights' ? '季度数据 · 评分观察' : state.view === 'favorites' ? '我的动画收藏' : state.query ? '搜索动画' : `${seasonTitle} · 全球评分榜`;
  $('#page-subtitle').textContent = state.query ? '全部年份 · 多语言番剧目录' : `${state.year} ${seasons[state.season]} / ${providers.map(p => names[p]).join(' · ')}`;
  updateCollection(data.collection);
  icons();
  drawDistribution();
  if (state.view === 'insights') drawInsights();
}
async function loadFavorites() {
  const result = [];
  const ids = [...state.favorites];
  for (let index = 0; index < ids.length; index += 8) {
    const batch = await Promise.allSettled(ids.slice(index, index + 8).map(id => api(`/anime/${id}?${params({ refresh: false })}`)));
    batch.forEach(item => { if (item.status === 'fulfilled') result.push(item.value); });
  }
  result.sort((a, b) => (b.scores.total ?? -1) - (a.scores.total ?? -1));
  result.forEach((item, index) => item.rank = item.scores.total == null ? null : index + 1);
  const filtered = result.filter(item => (!state.type || item.type === state.type) && (!state.query || [item.name, item.name_cn, item.name_en].join(' ').toLowerCase().includes(state.query.toLowerCase())));
  const rated = filtered.filter(item => item.scores.total != null);
  const summary = { total: filtered.length, rated: rated.length, average: rated.length ? rated.reduce((sum, i) => sum + i.scores.total, 0) / rated.length : null, votes: filtered.reduce((sum, i) => sum + providers.reduce((s, p) => s + (i.votes?.[p] || 0), 0), 0), coverage: Object.fromEntries(providers.map(p => [p, filtered.filter(i => i.scores[p] != null).length])), distribution: Array.from({ length: 10 }, (_, i) => ({ range: `${i}-${i + 1}`, count: rated.filter(item => Math.min(Math.floor(item.scores.total), 9) === i).length })) };
  return { items: filtered.slice(state.offset, state.offset + state.limit), total: filtered.length, summary, collection: state.status?.collection };
}
async function loadRanking(silent = false) {
  const id = ++requestId;
  rankingController?.abort();
  rankingController = new AbortController();
  if (!silent && state.view !== 'insights') $('#ranking-table').innerHTML = Array.from({ length: 5 }, () => '<div class="loading-row"><div class="skeleton image"></div><div class="skeleton line"></div></div>').join('');
  $('#refresh svg')?.classList.add('spinning');
  try {
    const query = { year: state.year, season: state.season, q: state.query, limit: state.limit, offset: state.offset, min_platforms: state.minPlatforms, min_votes: state.minVotes };
    if (state.type) query.anime_type = state.type;
    const data = state.view === 'favorites' ? await loadFavorites() : await api(`/ranking?${params(query)}`, { signal: rankingController.signal });
    if (id !== requestId) return;
    renderData(data);
  } catch (error) {
    if (error.name === 'AbortError' || id !== requestId) return;
    notice(`数据读取失败：${error.message}`, true);
    if (!silent) { $('#ranking-table').innerHTML = empty('暂时无法读取数据', '请确认后端服务运行正常，然后重试。', 'alert-circle'); icons(); }
  } finally { if (id === requestId) $('#refresh svg')?.classList.remove('spinning'); }
}
function updateCollection(collection) {
  if (!collection) return;
  $('#update-label').textContent = collection.running ? `采集中 ${collection.completed} / ${collection.total}` : collection.last_finished ? `更新于 ${date(collection.last_finished)}` : '等待首次采集';
  $('#next-update').textContent = state.status?.enabled === false ? '后台采集已停用' : collection.running ? `正在采集 ${collection.completed} / ${collection.total}` : collection.next_run ? `下次采集 ${date(collection.next_run)}` : '每小时自动采集';
  if (collection.running) notice(`正在更新评分：${collection.completed} / ${collection.total} 部动画，已采集的数据会逐步显示。`);
  else if (collection.error || collection.failures) notice(collection.error ? `上次采集未完成：${collection.error}` : `${collection.failures} 个平台请求暂时不可用，已保留可用评分。`);
  else notice('');
}
function chart(id) {
  if (!charts.has(id)) { charts.set(id, echarts.init(document.getElementById(id), null, { renderer: 'canvas' })); observer.observe(document.getElementById(id)); }
  return charts.get(id);
}
const baseChart = { animation: false, textStyle: { fontFamily: 'DM Sans, Microsoft YaHei, sans-serif', fontSize: 10 }, tooltip: { trigger: 'axis', renderMode: 'richText', backgroundColor: '#fff', borderColor: '#dce4de', textStyle: { color: '#344338', fontSize: 11 } } };
function distributionOption(small = false) {
  const distribution = state.data?.summary.distribution || [];
  return { ...baseChart, grid: { top: 12, right: 10, bottom: small ? 23 : 30, left: small ? 8 : 40, containLabel: !small }, xAxis: { type: 'category', data: distribution.map(i => i.range), axisTick: { show: false }, axisLine: { lineStyle: { color: '#e4eae3' } }, axisLabel: { color: '#96a390', fontSize: small ? 8 : 10, interval: small ? 1 : 0 } }, yAxis: { type: 'value', minInterval: 1, show: !small, splitLine: { lineStyle: { color: '#edf1ec', type: 'dashed' } } }, series: [{ name: '动画数', type: 'bar', data: distribution.map(i => i.count), barWidth: small ? '52%' : '45%', itemStyle: { color: '#76a18c', borderRadius: [2, 2, 0, 0] } }] };
}
function drawDistribution() { chart('distribution-small').setOption(distributionOption(true), true); }
function drawInsights() {
  chart('distribution-main').setOption(distributionOption(), true);
  chart('coverage-chart').setOption({ ...baseChart, grid: { left: 95, right: 25, top: 20, bottom: 35 }, xAxis: { type: 'value', max: Math.max(1, state.data?.summary.total || 0), minInterval: 1, splitLine: { lineStyle: { color: '#edf1ec' } } }, yAxis: { type: 'category', inverse: true, data: providers.map(p => names[p]), axisLine: { show: false }, axisTick: { show: false } }, series: [{ type: 'bar', barWidth: 22, label: { show: true, position: 'right', color: '#6b7b65' }, data: providers.map(p => ({ value: state.data?.summary.coverage[p] || 0, itemStyle: { color: colors[p], borderRadius: [0, 3, 3, 0] } })) }] }, true);
  const collection = state.data.collection || {};
  $('#source-health').innerHTML = [['采集范围', `${state.status?.current_year} ${seasons[state.status?.current_season]} + 已查看的作品`], ['更新频率', state.status?.enabled === false ? '已停用' : '每小时'], ['历史记录', `${count(collection.observations)} 条`], ['开始记录', date(collection.collected_since, true)], ['上次完成', date(collection.last_finished, true)], ['平台请求异常', count(collection.failures)]].map(([key, value]) => `<div class="source-row"><span>${key}</span><strong>${escape(value)}</strong></div>`).join('');
}
function showView(view) {
  state.view = view; state.offset = 0;
  $$('.nav-link').forEach(button => { button.classList.toggle('active', button.dataset.view === view); button.setAttribute('aria-current', button.dataset.view === view ? 'page' : 'false'); });
  $('#ranking-view').hidden = view === 'insights'; $('#insights-view').hidden = view !== 'insights';
  $('.season-filters').hidden = view === 'favorites' || !!state.query;
  $('#min-platforms').hidden = view === 'favorites';
  $('#min-votes').hidden = view === 'favorites';
  loadRanking();
}
function renderDetail(item) {
  const liveSources = providers.map(p => item.score_status?.[p]?.updated_at).filter(Boolean).sort();
  $('#detail-content').innerHTML = `<div class="detail-body"><div class="detail-intro">${poster(item, 'detail-poster')}<div class="detail-copy"><div class="detail-tags"><span class="type-tag">${escape((item.type || '').toUpperCase())}</span><span>${item.begin ? new Date(item.begin).toLocaleDateString('zh-CN') : '开播日期待定'}</span>${item.episodes ? `<span>${item.episodes} 话</span>` : ''}${item.studio ? `<span>${escape(item.studio)}</span>` : ''}</div><h2 id="detail-title">${escape(item.name_cn || item.name)}</h2><div class="detail-original">${escape(item.name)}</div><p class="detail-summary">${escape(item.summary || '暂无剧情简介。')}</p>${item.summary?.length > 140 ? '<button class="summary-toggle" id="summary-toggle">展开简介</button>' : ''}</div><div class="detail-actions"><button class="icon-button favorite ${state.favorites.has(item.catalog_id) ? 'saved' : ''}" data-favorite="${item.catalog_id}" title="收藏动画" aria-label="收藏动画" aria-pressed="${state.favorites.has(item.catalog_id)}"><i data-lucide="bookmark"></i></button></div></div><div class="rating-strip"><div class="rating-block"><span>综合评分</span><strong id="detail-total">${score(item.scores.total)}</strong><small>当前个人权重</small></div>${providers.map(p => { const link = item.sites?.find(site => site.site === ({ bgm: 'bangumi', mal: 'mal', anilist: 'aniList', filmarks: 'filmarks', anikore: 'anikore' }[p])); return `<div class="rating-block"><span><a href="${escape(safeUrl(link?.url) || '#')}" target="_blank" rel="noopener"><span class="provider-dot ${p}"></span>${names[p]}<i data-lucide="arrow-up-right"></i></a></span><strong style="color:${colors[p]}">${score(item.scores[p])}</strong><small>${compact(item.votes?.[p])} 人次 · ${escape(stateNames[item.score_status?.[p]?.status] || '待采集')}</small></div>`; }).join('')}</div><div class="chart-heading"><h3>评分趋势</h3><div class="chart-controls"><div class="segmented" id="metric-tabs"><button data-metric="scores" class="${state.metric === 'scores' ? 'selected' : ''}">评分</button><button data-metric="votes" class="${state.metric === 'votes' ? 'selected' : ''}">评分人数</button></div><div class="segmented" id="period-tabs">${['7d', '30d', '90d', '1y'].map(p => `<button data-period="${p}" class="${state.period === p ? 'selected' : ''}">${p}</button>`).join('')}</div></div></div><div id="trend-chart" class="trend-chart" role="img" aria-label="各平台和综合评分历史折线图"></div><div class="chart-foot"><span id="history-note">正在读取历史记录</span><span id="history-count"></span></div><div class="detail-bottom"><span>最后采集 ${date(liveSources.at(-1), true)} · 十分制 · 每小时记录</span><a id="download-history" class="download-link"><i data-lucide="download"></i>导出历史 CSV</a></div></div>`;
  $('.detail-original').insertAdjacentHTML('afterend', contributorCaption(item));
  if (Object.values(item.mapping_sources || {}).includes('missing')) $('.rating-strip').insertAdjacentHTML('afterend', '<div class="contribution-actions"><button id="open-contribution" class="button secondary"><i data-lucide="arrow-up-right"></i>补充缺失 ID</button></div>');
  icons();
}
function disposeTrend() { const node = $('#trend-chart'); if (node) observer.unobserve(node); charts.get('trend-chart')?.dispose(); charts.delete('trend-chart'); }
async function openDetail(id) {
  const current = ++detailId;
  disposeTrend(); state.selected = null;
  $('#detail-content').innerHTML = empty('正在读取评分', '正在同步各平台最新可用数据。', 'loader-circle'); icons();
  if (!$('#detail-dialog').open) $('#detail-dialog').showModal();
  try {
    const cached = await api(`/anime/${id}?${params({ refresh: false })}`);
    if (current !== detailId) return;
    state.selected = cached; renderDetail(cached); await loadHistory();
    const fresh = await api(`/anime/${id}?${params({ refresh: true })}`);
    if (current !== detailId) return;
    fresh.scores.total = weighted(fresh.scores);
    state.selected = fresh; disposeTrend(); renderDetail(fresh); await loadHistory();
    loadRanking(true);
  } catch (error) {
    if (current !== detailId) return;
    if (state.selected) toast(`更新失败，显示缓存：${error.message}`);
    else { $('#detail-content').innerHTML = empty('暂时无法读取详情', error.message, 'alert-circle'); icons(); }
  }
}
let historyRequestId = 0;
async function loadHistory() {
  if (!state.selected) return;
  const id = ++historyRequestId;
  state.history = null;
  $('#history-count').textContent = '';
  $('#download-history').removeAttribute('href');
  chart('trend-chart').showLoading({ text: '读取历史记录', color: colors.total, maskColor: '#fdfefdcc' });
  const url = `/anime/${state.selected.catalog_id}/history?${params({ period: state.period })}`;
  try {
    const data = await api(url);
    if (id !== historyRequestId || !state.selected) return;
    state.history = data;
    drawHistory();
    $('#history-count').textContent = `${data.points.length} 个真实采集点 · ${data.resolution === 'hour' ? '每小时' : '每日末次'}`;
    $('#history-note').textContent = data.points.length <= 1 ? '历史记录正在积累，暂无足够数据绘制趋势。' : `开始记录 ${date(data.collected_since, true)}，不补齐缺失时段。`;
    $('#download-history').href = `/api/v1/dashboard/anime/${state.selected.catalog_id}/history.csv?${params({ period: state.period })}`;
  } catch (error) {
    if (id === historyRequestId && $('#history-note')) {
      $('#history-note').textContent = `历史读取失败：${error.message}`;
      charts.get('trend-chart')?.clear();
    }
  } finally { if (id === historyRequestId) charts.get('trend-chart')?.hideLoading(); }
}
function drawHistory() {
  if (!state.history || !$('#trend-chart')) return;
  const data = state.history;
  const keys = state.metric === 'scores' ? ['total', ...providers] : providers;
  const gap = data.resolution === 'hour' ? 2 * 3600000 : 2 * 86400000;
  const series = keys.map(p => {
    const points = [];
    data.points.forEach((point, i) => { const timestamp = Date.parse(point.timestamp); if (i && timestamp - Date.parse(data.points[i - 1].timestamp) > gap) points.push([timestamp - 1, null]); points.push([timestamp, point[state.metric]?.[p] ?? null]); });
    return { name: names[p], type: 'line', data: points, connectNulls: false, symbol: 'circle', symbolSize: 5, showSymbol: data.points.length < 25, smooth: false, lineStyle: { width: p === 'total' ? 2.5 : 1.7 }, itemStyle: { color: colors[p] }, emphasis: { focus: 'series' } };
  });
  chart('trend-chart').setOption({ ...baseChart, color: keys.map(p => colors[p]), legend: { top: 20, left: 'center', icon: 'roundRect', itemHeight: 3, itemWidth: 14, textStyle: { fontSize: 10, color: '#87967e' } }, grid: { left: 45, right: 20, top: 94, bottom: 38 }, xAxis: { type: 'time', min: Date.parse(data.from), max: Date.parse(data.to), splitNumber: 5, axisLine: { lineStyle: { color: '#e1e8dc' } }, axisTick: { show: false }, axisLabel: { fontSize: 9, color: '#93a189', hideOverlap: true, formatter: value => `${new Date(value).getMonth() + 1}/${new Date(value).getDate()}` } }, yAxis: { type: 'value', min: 0, max: state.metric === 'scores' ? 10 : null, axisLabel: { fontSize: 9, color: '#93a189', formatter: value => state.metric === 'votes' ? compact(value) : value }, splitLine: { lineStyle: { color: '#eaf0e5', type: 'dashed' } } }, series, graphic: data.points.length === 0 ? [{ type: 'text', left: 'center', top: 'middle', style: { text: '尚无历史记录', fill: '#99a98e', fontSize: 12 } }] : [] }, true);
}

$('#weight-controls').addEventListener('input', event => {
  const toggle = event.target.dataset.weightEnabled;
  if (toggle) { changeDraft(toggle, event.target.checked ? rememberedWeights[toggle] || 1 : 0); return; }
  const provider = event.target.dataset.weightNumber || event.target.dataset.weightRange;
  if (provider) changeDraft(provider, event.target.value);
});
$$('[data-preset]').forEach(button => button.addEventListener('click', () => { state.draft = button.dataset.preset === 'equal' ? Object.fromEntries(providers.map(p => [p, 1])) : { ...DEFAULT }; providers.forEach(p => changeDraft(p, state.draft[p])); }));
$('#reset-weights').addEventListener('click', () => { state.draft = { ...DEFAULT }; providers.forEach(p => changeDraft(p, state.draft[p])); applyWeights(); });
$('#apply-weights').addEventListener('click', applyWeights);
$$('[data-view]').forEach(button => button.addEventListener('click', () => { if (button.dataset.view !== 'favorites') { state.query = ''; $('#search').value = ''; } showView(button.dataset.view); }));
$('#search-form').addEventListener('submit', event => { event.preventDefault(); state.query = $('#search').value.trim(); state.offset = 0; showView(state.view === 'favorites' ? 'favorites' : 'ranking'); });
$('#search').addEventListener('search', () => { if (!$('#search').value) { state.query = ''; state.offset = 0; showView('ranking'); } });
$('#year').addEventListener('change', event => { state.year = Number(event.target.value); state.offset = 0; loadRanking(); });
$('#season').addEventListener('change', event => { state.season = event.target.value; state.offset = 0; loadRanking(); });
$('#min-platforms').addEventListener('change', event => { state.minPlatforms = Number(event.target.value); state.offset = 0; loadRanking(); });
$('#min-votes').addEventListener('change', event => { state.minVotes = Number(event.target.value); state.offset = 0; loadRanking(); });
$('#type-tabs').addEventListener('click', event => { const button = event.target.closest('button'); if (!button) return; state.type = button.dataset.type; state.offset = 0; $$('#type-tabs button').forEach(b => b.classList.toggle('selected', b === button)); loadRanking(); });
$('#prev').addEventListener('click', () => { state.offset = Math.max(0, state.offset - state.limit); loadRanking(); });
$('#next').addEventListener('click', () => { state.offset += state.limit; loadRanking(); });
$('#refresh').addEventListener('click', () => state.status ? loadRanking() : initialize());
document.addEventListener('click', event => {
  if (event.target.closest('#open-contribution') && state.selected) openSubmission(state.selected);
  const detail = event.target.closest('[data-detail]'); if (detail) openDetail(detail.dataset.detail);
  const favorite = event.target.closest('[data-favorite]'); if (favorite) toggleFavorite(favorite.dataset.favorite);
  const period = event.target.closest('[data-period]'); if (period) { state.period = period.dataset.period; $$('[data-period]').forEach(b => b.classList.toggle('selected', b === period)); loadHistory(); }
  const metric = event.target.closest('[data-metric]'); if (metric) { state.metric = metric.dataset.metric; $$('[data-metric]').forEach(b => b.classList.toggle('selected', b === metric)); drawHistory(); }
  if (event.target.id === 'summary-toggle') { $('.detail-summary').classList.toggle('expanded'); event.target.textContent = $('.detail-summary').classList.contains('expanded') ? '收起简介' : '展开简介'; }
});
document.addEventListener('error', event => { if (event.target.tagName === 'IMG') { event.target.style.visibility = 'hidden'; event.target.alt = '海报暂不可用'; } }, true);
$('#close-detail').addEventListener('click', () => $('#detail-dialog').close());
$('#detail-dialog').addEventListener('close', () => { ++detailId; ++historyRequestId; state.selected = null; disposeTrend(); });
$('#methodology').addEventListener('click', () => { $('#method-dialog').showModal(); icons(); });
$('#close-method').addEventListener('click', () => $('#method-dialog').close());
[$('#detail-dialog'), $('#method-dialog')].forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } }));

async function initialize() {
  icons(); renderWeightControls(); renderFavoritesCount();
  try {
    state.status = await api('/status');
    state.year = state.status.current_year; state.season = state.status.current_season;
    $('#year').innerHTML = state.status.years.map(year => `<option value="${year}">${year}</option>`).join('');
    $('#year').value = state.year; $('#season').value = state.season;
    await loadRanking();
  } catch (error) { notice(`服务暂不可用：${error.message}`, true); $('#ranking-table').innerHTML = empty('正在等待数据', '确认目录已导入并且后端服务正在运行。', 'alert-circle'); icons(); }
}
setInterval(async () => {
  if (document.hidden || !state.status) return;
  try { const latest = await api('/status'); const changed = latest.collection.running || latest.collection.last_finished !== state.status.collection.last_finished || latest.mapping_updated_at !== state.status.mapping_updated_at; state.status = latest; updateCollection(latest.collection); if (changed) await loadRanking(true); } catch { $('#update-label').textContent = '连接暂时中断'; }
}, 15000);
initialize();
initCommunity();
window.addEventListener('open-submitted-anime', event => openDetail(event.detail));
window.addEventListener('mapping-submitted', async event => {
  const version = detailId;
  try {
    if (state.selected?.catalog_id === event.detail) {
      const item = await api(`/anime/${event.detail}?${params({ refresh: false })}`);
      if (version === detailId && state.selected?.catalog_id === event.detail) { state.selected = item; disposeTrend(); renderDetail(item); await loadHistory(); }
    }
    await loadRanking(true);
  } catch (error) { toast(error.message); }
});
