import { api, getSession } from './api.js?v=0.1.1';
import { createAssetDrawer } from './asset-drawer.js?v=0.1.1';
import { createManagement } from './management.js?v=0.1.1';
import { icon } from './icons.js';
import { escapeHtml as e, errorMessage, integer, MODE_LABELS, number, parseWorkspaceLocation, safeUrl, workspaceLocationParameters } from './format.js';
import { notify } from './modal.js';
import { renderAsset, renderCollections, renderEmpty, renderError, renderJobs, renderLoading, renderPagination, renderRoots } from './render.js';

const $ = selector => document.querySelector(selector);
const MAX_SELECTION = 300;
const PAGE_SIZE = 36;
const FILTER_FIELDS = { folder: '#filter-folder', tag: '#filter-tag', date_from: '#filter-date-from', date_to: '#filter-date-to', negative_query: '#filter-negative', min_score: '#filter-score' };
const MODES = {
  filename: { placeholder: '搜索文件名，找到记忆中的那一份素材…', hint: '每一份灵感，都有迹可循。', icon: 'search' },
  semantic: { placeholder: '描述你想找的画面，例如：林间透过树叶的阳光', hint: '用一句话描述画面，可搜索图片与视频画面。', icon: 'sparkle' },
  reference: { placeholder: '可选：补充画面描述，进一步缩小范围', hint: '上传一张参考图片，寻找视觉相近的图片与视频。', icon: 'image' },
  document: { placeholder: '搜索文档中的文字、句子或关键词…', hint: '搜索已索引的文档内容，结果会标出原文与页码。', icon: 'document' },
  dialogue: { placeholder: '输入你记得的台词，例如：我们明天就出发', hint: '搜索已识别的视频台词，直接定位对应片段。', icon: 'dialogue' },
};

function savedPreference(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } }
function savePreference(key, value) { try { localStorage.setItem(key, value); } catch { /* The current session remains usable without storage. */ } }

const state = {
  status: null, roots: [], collections: [], jobs: [], scope: { type: 'all' }, mode: 'filename', kind: '', query: '', sort: 'recent',
  view: savedPreference('original-studio-view', 'grid') === 'list' ? 'list' : 'grid',
  items: [], total: 0, page: 1, pageSize: PAGE_SIZE, selected: new Map(), reference: null,
  loading: false, connected: false, initialized: false, filters: {},
};
let searchController = null;
let searchGeneration = 0;
let referenceController = null;
let referenceGeneration = 0;
let referenceObjectUrl = null;
let polling = false;
let pollTimer = null;
let initialising = false;
let refreshing = false;
let libraryUpdatePending = false;
let refreshingEmptyLibrary = false;
const navigationMarkup = new WeakMap();

function updateNavigationSection(element, markup) {
  if (navigationMarkup.get(element) === markup) return;
  const focused = document.activeElement;
  const trigger = focused?.closest('[data-scope]');
  const restore = trigger && element.contains(focused) ? { scope: trigger.dataset.scope, id: trigger.dataset.id || '' } : null;
  element.innerHTML = markup;
  navigationMarkup.set(element, markup);
  if (!restore) return;
  const replacement = [...element.querySelectorAll('[data-scope]')].find(button => button.dataset.scope === restore.scope && (button.dataset.id || '') === restore.id);
  (replacement || $('#library-nav [data-scope="all"]'))?.focus({ preventScroll: true });
}

function syncLocation(mode = 'push') {
  if (mode === 'none' || !state.initialized) return;
  const parameters = workspaceLocationParameters(state).toString();
  const target = `${location.pathname}${parameters ? `?${parameters}` : ''}${location.hash}`;
  if (target === `${location.pathname}${location.search}${location.hash}`) return;
  history[mode === 'replace' ? 'replaceState' : 'pushState'](null, '', target);
}

async function restoreLocation() {
  const restored = parseWorkspaceLocation(location.search, state.roots, state.collections);
  drawer.close();
  if ($('#modal').open) $('#modal').close();
  state.sort = restored.sort;
  state.query = restored.query;
  state.kind = restored.kind;
  $('#search-query').value = restored.query;
  clearFilters();
  setMode(restored.mode, false);
  state.filters = restored.filters;
  Object.entries(FILTER_FIELDS).forEach(([key, selector]) => { $(selector).value = restored.filters[key] ?? ''; });
  const filterCount = Object.keys(restored.filters).length;
  $('#filter-count').textContent = String(filterCount);
  $('#filter-count').hidden = !filterCount;
  $('#advanced-toggle').setAttribute('aria-expanded', String(Boolean(filterCount)));
  $('#advanced-filters').hidden = !filterCount;
  updateKindButtons();
  await setScope(restored.scope, { page: restored.page, urlMode: 'replace' });
}

function markLibraryUpdated() {
  libraryUpdatePending = true;
  $('#refresh-notice').hidden = false;
}

async function refreshEmptyLibrary() {
  if (!libraryUpdatePending || refreshingEmptyLibrary || !state.initialized || state.loading || document.querySelector('dialog[open]')) return;
  if (state.scope.type === 'tasks' || state.items.length || state.selected.size || state.mode !== 'filename' || state.query || $('#search-query').value.trim() || Object.keys(state.filters).length) return;
  libraryUpdatePending = false;
  refreshingEmptyLibrary = true;
  try { await search({ readForm: false, urlMode: 'none' }); }
  finally { refreshingEmptyLibrary = false; }
}

function fillIcons() {
  document.querySelectorAll('[data-icon]').forEach(element => { element.innerHTML = icon(element.dataset.icon); });
}

function setConnection(connected, message = '') {
  state.connected = connected;
  const indicator = $('#connection-indicator');
  indicator.classList.toggle('is-offline', !connected);
  indicator.innerHTML = `<i></i>${connected ? '本地已连接' : '连接已断开'}`;
  const banner = $('#connection-banner');
  banner.hidden = connected;
  if (!connected) banner.innerHTML = `<span>${e(message || '无法连接本地服务。请确认拾序正在运行，然后重试。')}</span><button data-reconnect>重新连接</button>`;
}

function updateNavigation() {
  updateNavigationSection($('#roots-nav'), renderRoots(state.roots, state.scope));
  updateNavigationSection($('#collections-nav'), renderCollections(state.collections, state.scope));
  document.querySelectorAll('[data-scope]').forEach(button => {
    const active = button.dataset.scope === state.scope.type && (!button.dataset.id || Number(button.dataset.id) === state.scope.id);
    button.classList.toggle('is-active', active);
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  const stats = state.status?.stats;
  $('#total-count').textContent = stats ? number(stats.total) : '—';
  $('#favorite-count').textContent = stats ? number(stats.favorites) : '—';
  const active = state.jobs.filter(job => ['queued', 'running', 'stopping'].includes(job.status)).length;
  $('#active-task-count').textContent = String(active);
  $('#active-task-count').hidden = !active;
  $('#jobs-total').textContent = number(state.jobs.length);
  const visual = state.status?.capabilities?.visual;
  $('#engine-indicator').innerHTML = `<span class="status-dot ${visual?.installed ? '' : 'muted-dot'}"></span><span>${!state.status ? '正在连接本地工作区' : visual?.loaded ? '视觉引擎已就绪' : visual?.installed ? '视觉引擎可用' : '基础素材库已就绪'}</span>`;
  updateHeader();
}

function updateHeader() {
  const scope = state.scope;
  const root = scope.type === 'root' ? state.roots.find(item => item.id === scope.id) : null;
  const collection = scope.type === 'collection' ? state.collections.find(item => item.id === scope.id) : null;
  const title = scope.type === 'favorites' ? '我的收藏' : scope.type === 'tasks' ? '索引任务' : root?.name || collection?.name || '全部素材';
  $('#breadcrumb').textContent = title;
  $('#page-title').textContent = title;
  $('#collection-menu-button').hidden = !collection;
  $('#root-menu-button').hidden = !root;
  $('#page-description').textContent = root ? `${root.available === false ? '目录当前不可用 · ' : ''}${root.path}` : collection ? '灵感在此汇聚，新的故事即将发生。' : scope.type === 'favorites' ? '每一份喜欢，都为下一次创作埋下伏笔。' : '收藏每一次发现，让灵感随时归位。';
  $('#page-description').title = root?.path || '';
  const total = root?.asset_count ?? collection?.item_count ?? (scope.type === 'favorites' ? state.status?.stats?.favorites : state.status?.stats?.total);
  $('#heading-total').textContent = total == null ? '—' : number(total);
  $('#kind-all-count').textContent = state.total ? number(state.total) : '';
  document.title = `${title} · 拾序 Original Studio`;
}

function closeNavigation() {
  $('#sidebar').classList.remove('is-open');
  $('#nav-shade').hidden = true;
  $('#nav-toggle').setAttribute('aria-expanded', 'false');
}

async function setScope(scope, { page = 1, urlMode = 'push' } = {}) {
  state.scope = scope;
  state.page = page;
  clearSelection();
  closeNavigation();
  $('#library-view').hidden = scope.type === 'tasks';
  $('#tasks-view').hidden = scope.type !== 'tasks';
  updateNavigation();
  if (scope.type === 'tasks') {
    syncLocation(urlMode);
    searchGeneration += 1;
    searchController?.abort();
    state.loading = false;
    $('#search-submit').disabled = false;
    $('#results').setAttribute('aria-busy', 'false');
    renderTaskList();
    try { await refreshJobs(); }
    catch (failure) { notify(`任务列表暂时无法更新：${errorMessage(failure)}`, 'error'); }
  }
  else await search({ readForm: false, urlMode });
}

async function refreshMetadata() {
  const results = await Promise.allSettled([api.status(), api.roots(), api.collections()]);
  if (results[0].status === 'fulfilled') { state.status = results[0].value; setConnection(true); }
  if (results[1].status === 'fulfilled') state.roots = results[1].value.items || [];
  if (results[2].status === 'fulfilled') state.collections = results[2].value.items || [];
  updateNavigation();
  updateCapabilityNote();
  const failures = results.filter(result => result.status === 'rejected');
  if (failures.length) throw failures[0].reason;
}

function readFilters() {
  const filters = {};
  const map = { folder: '#filter-folder', tag: '#filter-tag', date_from: '#filter-date-from', date_to: '#filter-date-to' };
  Object.entries(map).forEach(([key, selector]) => { const value = $(selector).value.trim(); if (value) filters[key] = value; });
  if (['semantic', 'reference'].includes(state.mode)) {
    const negative = $('#filter-negative').value.trim();
    const score = $('#filter-score').value;
    if (negative) filters.negative_query = negative;
    if (score !== '') filters.min_score = Number(score);
  }
  if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) throw new Error('开始日期不能晚于结束日期。');
  state.filters = filters;
  const count = Object.keys(filters).length;
  $('#filter-count').textContent = String(count);
  $('#filter-count').hidden = !count;
  return filters;
}

function currentFilters() {
  return {
    ...state.filters, mode: state.mode, query: state.query, kind: state.kind || undefined,
    root_id: state.scope.type === 'root' ? state.scope.id : undefined,
    favorite: state.scope.type === 'favorites' ? true : undefined,
    collection_id: state.scope.type === 'collection' ? state.scope.id : undefined,
    sort: state.sort, page: state.page, page_size: state.pageSize,
    reference_id: state.mode === 'reference' ? state.reference?.id : undefined,
  };
}

function showSearchInstruction() {
  const mode = state.mode;
  state.items = [];
  state.total = 0;
  const title = mode === 'reference' ? '从一张图片，发现更多可能。' : mode === 'semantic' ? '描述一个画面，寻找一次共鸣。' : mode === 'document' ? '从文字中，找回记忆。' : '那一句台词，藏在哪段视频里？';
  const description = mode === 'reference' ? '先选择一张参考图片，再搜索你的素材库。' : mode === 'semantic' ? '试着描述光线、颜色、主体或氛围，开始语义搜索。' : mode === 'document' ? '输入文档中出现的文字，搜索已完成索引的内容。' : '输入你记得的台词，定位已建立台词索引的视频片段。';
  $('#results').innerHTML = `<div class="empty-state"><div class="empty-art"><span class="empty-sheet sheet-back"></span><span class="empty-sheet sheet-front">${icon(MODES[mode].icon, '', 34)}</span></div><h2>${title}</h2><p>${description}</p></div>`;
  $('#results').setAttribute('aria-busy', 'false');
  $('#results-summary').textContent = '等待搜索';
  $('#pagination').hidden = true;
  $('#select-page').disabled = true;
  renderSelection();
}

async function search({ readForm = true, resetPage = false, urlMode = 'push' } = {}) {
  if (state.scope.type === 'tasks') return;
  if (readForm) {
    if (!$('#search-form').reportValidity()) return;
    try { readFilters(); } catch (error) { notify(errorMessage(error), 'error'); return; }
    const query = $('#search-query').value.trim();
    if ([...query].length > 1000) { notify('搜索内容最多 1000 个字符，请缩短后重试。', 'error'); return; }
    state.query = query;
  }
  if (resetPage) { state.page = 1; clearSelection(); }
  syncLocation(urlMode);
  const generation = ++searchGeneration;
  searchController?.abort();
  searchController = new AbortController();
  libraryUpdatePending = false;
  $('#refresh-notice').hidden = true;
  if ((state.mode === 'reference' && !state.reference) || (state.mode !== 'filename' && state.mode !== 'reference' && !state.query)) {
    state.loading = false;
    $('#search-submit').disabled = false;
    showSearchInstruction();
    return;
  }
  state.loading = true;
  $('#results').innerHTML = renderLoading();
  $('#results').setAttribute('aria-busy', 'true');
  $('#results-summary').textContent = '正在查找…';
  $('#search-submit').disabled = true;
  $('#select-page').disabled = true;
  $('#pagination').hidden = true;
  try {
    const filters = currentFilters();
    const result = state.mode === 'filename' && !state.query
      ? await api.assets({ ...filters, mode: undefined, query: undefined, reference_id: undefined }, searchController.signal)
      : await api.search(filters, searchController.signal);
    if (generation !== searchGeneration) return;
    state.items = result.items || [];
    state.total = integer(result.total);
    state.page = integer(result.page) || state.page;
    const lastPage = Math.max(1, Math.ceil(state.total / state.pageSize));
    if (state.page > lastPage) { state.page = lastPage; await search({ readForm: false, urlMode: 'replace' }); return; }
    state.items.forEach(item => { if (state.selected.has(item.id)) state.selected.set(item.id, item); });
    renderResults(result.elapsed_ms);
    if (!state.connected) setConnection(true);
  } catch (error) {
    if (error.name === 'AbortError' || generation !== searchGeneration) return;
    $('#results').innerHTML = renderError(errorMessage(error));
    $('#results-summary').textContent = '未能完成搜索';
    state.items = [];
    state.total = 0;
    $('#select-page').checked = false;
    if (error instanceof TypeError) setConnection(false);
  } finally {
    if (generation === searchGeneration) {
      state.loading = false;
      $('#search-submit').disabled = false;
      $('#results').setAttribute('aria-busy', 'false');
      $('#select-page').disabled = !state.items.length;
      await refreshEmptyLibrary();
    }
  }
}

function renderResults(elapsed) {
  const filtered = Boolean(state.query || state.kind || Object.keys(state.filters).length || state.mode !== 'filename');
  $('#results').innerHTML = state.items.length ? state.items.map(item => renderAsset(item, state.selected.has(item.id))).join('') : renderEmpty({ noRoots: !state.roots.length, filtered, scope: state.scope.type });
  const pagination = renderPagination(state.page, state.total, state.pageSize);
  $('#pagination').innerHTML = pagination;
  $('#pagination').hidden = !pagination;
  const range = state.items.length ? `共 ${number(state.total)} 份素材` : '暂无素材';
  const context = state.query ? ` · ${MODE_LABELS[state.mode]}搜索` : state.mode !== 'filename' ? ` · ${MODE_LABELS[state.mode]}` : '';
  $('#results-summary').textContent = `${range}${context}${elapsed != null ? ` · ${(Number(elapsed) / 1000).toFixed(2)} 秒` : ''}`;
  $('#kind-all-count').textContent = state.total ? number(state.total) : '';
  renderSelection();
}

function renderSelection() {
  const selected = state.selected;
  $('#bulk-bar').hidden = !selected.size || state.scope.type === 'tasks';
  $('#selection-count').textContent = String(selected.size);
  $('#bulk-remove-collection').hidden = state.scope.type !== 'collection';
  const allFavorite = selected.size && [...selected.values()].every(item => item.favorite);
  $('[data-bulk="favorite"]').innerHTML = `${icon('heart')}<span>${allFavorite ? '取消收藏' : '收藏'}</span>`;
  const pageCheckbox = $('#select-page');
  const selectedOnPage = state.items.filter(item => selected.has(item.id)).length;
  pageCheckbox.checked = Boolean(state.items.length && selectedOnPage === state.items.length);
  pageCheckbox.indeterminate = selectedOnPage > 0 && selectedOnPage < state.items.length;
  document.querySelectorAll('[data-select]').forEach(input => {
    const checked = selected.has(Number(input.dataset.select));
    input.checked = checked;
    input.closest('.asset-card').classList.toggle('is-selected', checked);
  });
}

function clearSelection() { state.selected.clear(); renderSelection(); }

function selectAsset(id, selected) {
  if (!selected) state.selected.delete(id);
  else {
    if (state.selected.size >= MAX_SELECTION && !state.selected.has(id)) { notify('一次最多选择 300 份素材。', 'info'); renderSelection(); return; }
    const asset = state.items.find(item => item.id === id);
    if (asset) state.selected.set(id, asset);
  }
  renderSelection();
}

function setView(view) {
  state.view = view;
  savePreference('original-studio-view', view);
  $('#results').className = view === 'list' ? 'results-grid results-list' : 'results-grid';
  $('#grid-button').classList.toggle('is-active', view === 'grid');
  $('#list-button').classList.toggle('is-active', view === 'list');
  $('#grid-button').setAttribute('aria-pressed', String(view === 'grid'));
  $('#list-button').setAttribute('aria-pressed', String(view === 'list'));
}

function updateCapabilityNote() {
  const note = $('#capability-note');
  const capabilities = state.status?.capabilities || {};
  const key = ['semantic', 'reference'].includes(state.mode) ? 'visual' : state.mode === 'dialogue' ? 'transcripts' : null;
  const missing = key && capabilities[key]?.installed === false;
  note.hidden = !missing;
  if (missing) note.innerHTML = `${icon('info')}<span>${e(capabilities[key].message || '此搜索需要安装可选引擎。')}<button data-show-capabilities>查看能力与安装说明</button></span>`;
}

function setMode(mode, runSearch = true) {
  if (!MODES[mode]) return;
  state.mode = mode;
  state.page = 1;
  clearSelection();
  document.querySelectorAll('[data-mode]').forEach(button => { const active = button.dataset.mode === mode; button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1; });
  $('#search-query').placeholder = MODES[mode].placeholder;
  $('#search-query').setAttribute('aria-label', `${MODE_LABELS[mode]}搜索内容`);
  $('#search-hint').textContent = MODES[mode].hint;
  $('.search-input-icon').innerHTML = icon(MODES[mode].icon);
  $('#reference-upload').hidden = mode !== 'reference';
  document.querySelectorAll('.semantic-filter').forEach(element => {
    element.hidden = !['semantic', 'reference'].includes(mode);
    element.querySelector('input').disabled = element.hidden;
  });
  const sort = $('#sort-select');
  sort.disabled = mode !== 'filename';
  sort.innerHTML = mode === 'filename' ? '<option value="recent">最近修改</option><option value="name">名称 A → Z</option><option value="oldest">最早修改</option>' : '<option value="relevance">按相关性排序</option>';
  if (mode === 'filename') sort.value = state.sort;
  sort.title = mode === 'filename' ? '结果排序' : '此搜索按相关性排列';
  updateCapabilityNote();
  if (runSearch) search({ resetPage: true });
}

function clearFilters() {
  ['#filter-folder', '#filter-tag', '#filter-date-from', '#filter-date-to', '#filter-negative', '#filter-score'].forEach(selector => { $(selector).value = ''; });
  state.filters = {};
  $('#filter-count').hidden = true;
}

function resetSearch() {
  $('#search-query').value = '';
  state.query = '';
  state.kind = '';
  clearFilters();
  updateKindButtons();
  setMode('filename', false);
  search({ resetPage: true });
}

function updateKindButtons() {
  document.querySelectorAll('[data-kind]').forEach(button => { button.classList.toggle('is-active', button.dataset.kind === state.kind); button.setAttribute('aria-pressed', String(button.dataset.kind === state.kind)); });
}

function clearReference() {
  referenceController?.abort();
  referenceGeneration += 1;
  if (referenceObjectUrl) URL.revokeObjectURL(referenceObjectUrl);
  referenceObjectUrl = null;
  state.reference = null;
  $('#reference-file').value = '';
  $('#reference-preview').innerHTML = '';
  $('#reference-preview').hidden = true;
  $('#reference-drop').hidden = false;
  if (state.mode === 'reference') search({ readForm: false, resetPage: true });
}

async function uploadReference(file) {
  if (!file) return;
  if (!file.type.startsWith('image/')) { notify('请选择图片文件。', 'error'); return; }
  if (file.size > 16 * 1024 * 1024) { notify('参考图片不能超过 16 MB。', 'error'); return; }
  referenceController?.abort();
  const generation = ++referenceGeneration;
  referenceController = new AbortController();
  if (referenceObjectUrl) URL.revokeObjectURL(referenceObjectUrl);
  referenceObjectUrl = URL.createObjectURL(file);
  state.reference = null;
  if (state.mode === 'reference') search({ readForm: false, resetPage: true });
  const preview = $('#reference-preview');
  preview.hidden = false;
  $('#reference-drop').hidden = true;
  preview.innerHTML = `<img alt="参考图片"><div><strong>${e(file.name)}</strong><small><span class="loader"></span> 正在上传与处理…</small></div><button type="button" class="icon-button" data-clear-reference aria-label="移除参考图片">${icon('close', '', 17)}</button>`;
  preview.querySelector('img').src = referenceObjectUrl;
  try {
    const result = await api.reference(file, referenceController.signal);
    if (generation !== referenceGeneration) return;
    state.reference = result;
    preview.querySelector('small').textContent = '参考图已就绪';
    const processedUrl = safeUrl(result.url);
    if (processedUrl) {
      preview.querySelector('img').src = processedUrl;
      if (referenceObjectUrl) URL.revokeObjectURL(referenceObjectUrl);
      referenceObjectUrl = null;
    }
    if (state.mode === 'reference') await search({ resetPage: true });
  } catch (error) {
    if (error.name === 'AbortError' || generation !== referenceGeneration) return;
    preview.querySelector('small').textContent = '上传失败，请移除后重新选择';
    notify(errorMessage(error), 'error');
  }
}

function renderTaskList() {
  const focused = document.activeElement?.closest('[data-job-action]');
  const restore = focused ? { id: focused.dataset.id, action: focused.dataset.jobAction } : null;
  $('#jobs-list').innerHTML = renderJobs(state.jobs);
  if (restore) $(`#jobs-list [data-id="${restore.id}"][data-job-action="${restore.action}"]`)?.focus({ preventScroll: true });
}

async function refreshJobs() {
  const result = await api.jobs();
  const previous = new Map(state.jobs.map(job => [job.id, job.status]));
  state.jobs = result.items || [];
  const completed = state.jobs.some(job => ['completed', 'failed', 'stopped'].includes(job.status) && (['queued', 'running', 'stopping'].includes(previous.get(job.id)) || (!previous.has(job.id) && state.initialized)));
  if (completed) {
    markLibraryUpdated();
    const metadata = await Promise.allSettled([api.status(), api.roots(), api.collections()]);
    if (metadata[0].status === 'fulfilled') state.status = metadata[0].value;
    if (metadata[1].status === 'fulfilled') state.roots = metadata[1].value.items || [];
    if (metadata[2].status === 'fulfilled') state.collections = metadata[2].value.items || [];
    metadata.filter(item => item.status === 'rejected').forEach(item => { if (item.reason instanceof TypeError) setConnection(false); });
  }
  if (state.scope.type === 'tasks') renderTaskList();
  updateNavigation();
  await refreshEmptyLibrary();
  return completed;
}

async function poll() {
  if (polling || document.hidden || !state.initialized) return;
  polling = true;
  const previousTotal = state.status?.stats?.total;
  try {
    const results = await Promise.allSettled([api.status(), refreshJobs()]);
    if (results[0].status === 'fulfilled') {
      state.status = results[0].value;
      if (previousTotal != null && previousTotal !== state.status.stats?.total && !(results[1].status === 'fulfilled' && results[1].value)) markLibraryUpdated();
      setConnection(true);
      updateNavigation();
      updateCapabilityNote();
    }
    else if (results[0].reason instanceof TypeError) setConnection(false);
    if (results[1].status === 'rejected' && results[1].reason instanceof TypeError) setConnection(false);
    await refreshEmptyLibrary();
  } finally { polling = false; }
}

function schedulePoll() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => { await poll(); schedulePoll(); }, state.connected ? 4000 : 7000);
}

async function assetChanged(updated) {
  const index = state.items.findIndex(item => item.id === updated.id);
  if (index >= 0) state.items[index] = { ...state.items[index], ...updated };
  if (state.selected.has(updated.id)) state.selected.set(updated.id, { ...state.selected.get(updated.id), ...updated });
  if (index >= 0 && ((state.scope.type === 'favorites' && !updated.favorite) || (state.scope.type === 'collection' && !(updated.collection_ids || []).includes(state.scope.id)) || (state.filters.tag && !(updated.tags || []).includes(state.filters.tag)))) {
    state.items = state.items.filter(item => item.id !== updated.id);
    state.total = Math.max(0, state.total - 1);
    state.selected.delete(updated.id);
  }
  if (!state.loading && state.scope.type !== 'tasks') renderResults();
  try { await refreshMetadata(); } catch (failure) { notify(`整理已保存，统计未刷新：${errorMessage(failure)}`, 'info'); }
}

const drawer = createAssetDrawer({ getCollections: () => state.collections, onChange: assetChanged });
const management = createManagement({ state, refreshMetadata, setScope, refreshSearch: () => search({ readForm: false }), refreshJobs, renderSelection });

async function toggleFavorite(id, button) {
  const asset = state.items.find(item => item.id === id);
  if (!asset || button.disabled) return;
  button.disabled = true;
  const returnFocus = document.activeElement === button;
  try {
    await assetChanged(await api.updateAsset(id, { favorite: !asset.favorite }));
    if (returnFocus) $(`[data-action="favorite"][data-id="${id}"]`)?.focus({ preventScroll: true });
  }
  catch (failure) { notify(errorMessage(failure), 'error'); }
  finally { if (button.isConnected) button.disabled = false; }
}

function bindEvents() {
  document.addEventListener('click', event => {
    const scope = event.target.closest('[data-scope]');
    if (scope) { setScope({ type: scope.dataset.scope, ...(scope.dataset.id ? { id: Number(scope.dataset.id) } : {}) }); return; }
    if (event.target.closest('[data-reconnect]')) bootstrap();
    if (event.target.closest('[data-show-capabilities]')) management.capabilities();
    if (event.target.closest('[data-clear-reference]')) clearReference();
    const empty = event.target.closest('[data-empty-action]');
    if (empty) {
      if (empty.dataset.emptyAction === 'add-root') management.addRoot();
      if (empty.dataset.emptyAction === 'index') management.index();
      if (empty.dataset.emptyAction === 'reset') resetSearch();
      if (empty.dataset.emptyAction === 'retry') search();
    }
  });
  $('#search-form').addEventListener('submit', event => { event.preventDefault(); search({ resetPage: true }); });
  $('#search-tabs').addEventListener('click', event => { const button = event.target.closest('[data-mode]'); if (button) setMode(button.dataset.mode); });
  $('#search-tabs').addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const tabs = [...document.querySelectorAll('[data-mode]')];
    const current = tabs.indexOf(document.activeElement);
    const index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
    tabs[index].focus();
    setMode(tabs[index].dataset.mode);
  });
  $('#advanced-toggle').addEventListener('click', () => { const expanded = $('#advanced-toggle').getAttribute('aria-expanded') !== 'true'; $('#advanced-toggle').setAttribute('aria-expanded', String(expanded)); $('#advanced-filters').hidden = !expanded; });
  $('#clear-filters').addEventListener('click', () => { clearFilters(); search({ resetPage: true }); });
  $('#kind-filters').addEventListener('click', event => { const button = event.target.closest('[data-kind]'); if (!button) return; state.kind = button.dataset.kind; updateKindButtons(); search({ resetPage: true }); });
  $('#sort-select').addEventListener('change', event => { state.sort = event.target.value; search({ resetPage: true }); });
  $('#grid-button').addEventListener('click', () => setView('grid'));
  $('#list-button').addEventListener('click', () => setView('list'));
  $('#results').addEventListener('click', event => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    const id = Number(button.dataset.id);
    if (button.dataset.action === 'open') { const asset = state.items.find(item => item.id === id); if (asset) drawer.open(asset); }
    if (button.dataset.action === 'favorite') toggleFavorite(id, button);
  });
  $('#results').addEventListener('change', event => { if (event.target.matches('[data-select]')) selectAsset(Number(event.target.dataset.select), event.target.checked); });
  $('#results').addEventListener('error', event => {
    if (event.target.tagName === 'IMG') { event.target.hidden = true; const fallback = event.target.parentElement.querySelector('.asset-fallback'); if (fallback) fallback.hidden = false; }
  }, true);
  $('#select-page').addEventListener('change', event => {
    if (!event.target.checked) state.items.forEach(item => state.selected.delete(item.id));
    else {
      const additional = state.items.filter(item => !state.selected.has(item.id));
      if (state.selected.size + additional.length > MAX_SELECTION) { notify('一次最多选择 300 份素材，请先取消部分选择。', 'info'); renderSelection(); return; }
      additional.forEach(item => state.selected.set(item.id, item));
    }
    renderSelection();
  });
  $('#clear-selection').addEventListener('click', clearSelection);
  $('#bulk-bar').addEventListener('click', event => { const button = event.target.closest('[data-bulk]'); if (button) management.bulk(button.dataset.bulk); });
  $('#pagination').addEventListener('click', async event => { const button = event.target.closest('[data-page]'); if (!button || button.disabled) return; state.page = Number(button.dataset.page); await search({ readForm: false }); $('#results-summary').scrollIntoView({ behavior: 'smooth', block: 'start' }); });
  $('#reference-file').addEventListener('change', event => uploadReference(event.target.files[0]));
  const drop = $('#reference-drop');
  ['dragenter', 'dragover'].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.add('is-dragging'); }));
  ['dragleave', 'drop'].forEach(name => drop.addEventListener(name, event => { event.preventDefault(); drop.classList.remove('is-dragging'); }));
  drop.addEventListener('drop', event => uploadReference(event.dataTransfer.files[0]));
  $('#add-root-button').addEventListener('click', management.addRoot);
  $('#add-root-nav').addEventListener('click', management.addRoot);
  $('#root-menu-button').addEventListener('click', management.rootMenu);
  $('#add-collection').addEventListener('click', () => management.collectionEditor());
  $('#collection-menu-button').addEventListener('click', () => management.collectionEditor(state.collections.find(item => item.id === state.scope.id)));
  $('#index-button').addEventListener('click', () => management.index());
  $('#new-job-button').addEventListener('click', () => management.index());
  $('#capabilities-button').addEventListener('click', management.capabilities);
  $('#backup-button').addEventListener('click', event => management.backup(event.currentTarget));
  $('#jobs-list').addEventListener('click', event => { const button = event.target.closest('[data-job-action]'); if (button) management.jobAction(button.dataset.jobAction, Number(button.dataset.id), button); });
  $('#refresh-notice').addEventListener('click', () => search({ readForm: false }));
  $('#refresh-button').addEventListener('click', refreshWorkspace);
  $('#nav-toggle').addEventListener('click', () => { const open = !$('#sidebar').classList.contains('is-open'); $('#sidebar').classList.toggle('is-open', open); $('#nav-shade').hidden = !open; $('#nav-toggle').setAttribute('aria-expanded', String(open)); if (open) $('#sidebar .is-active')?.focus(); });
  $('#nav-shade').addEventListener('click', closeNavigation);
  document.addEventListener('keydown', event => {
    const editing = /INPUT|TEXTAREA|SELECT/.test(event.target.tagName) || event.target.isContentEditable;
    if (event.key === '/' && !editing && !event.ctrlKey && !event.metaKey && !document.querySelector('dialog[open]')) {
      event.preventDefault();
      if (state.scope.type === 'tasks') setScope({ type: 'all' });
      $('#search-query').focus();
    }
    if (event.key === 'Escape' && !document.querySelector('dialog[open]') && $('#sidebar').classList.contains('is-open')) { closeNavigation(); $('#nav-toggle').focus({ preventScroll: true }); }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { poll(); schedulePoll(); } });
  window.addEventListener('popstate', () => { if (state.initialized) restoreLocation(); });
  window.addEventListener('beforeunload', () => { if (referenceObjectUrl) URL.revokeObjectURL(referenceObjectUrl); searchController?.abort(); referenceController?.abort(); });
}

async function refreshWorkspace() {
  if (refreshing) return;
  refreshing = true;
  $('#refresh-button').disabled = true;
  try {
    await Promise.all([refreshMetadata(), refreshJobs()]);
    if (state.scope.type !== 'tasks') await search({ readForm: false });
    notify('工作区已刷新');
  } catch (failure) { notify(errorMessage(failure), 'error'); }
  finally { refreshing = false; $('#refresh-button').disabled = false; }
}

async function bootstrap() {
  if (initialising) return;
  initialising = true;
  try {
    const session = await getSession();
    $('#version-label').textContent = `ORIGINAL STUDIO · ${session.version || 'LOCAL'}`;
    const results = await Promise.allSettled([refreshMetadata(), refreshJobs()]);
    if (results[0].status === 'rejected') throw results[0].reason;
    if (results[1].status === 'rejected') notify(`任务列表未读取：${errorMessage(results[1].reason)}`, 'info');
    state.initialized = true;
    setConnection(true);
    await restoreLocation();
  } catch (error) {
    setConnection(false, `无法连接本地工作区：${errorMessage(error)} 请确认服务已启动。`);
    $('#results').innerHTML = renderError('请启动本地服务，然后点击“重新连接”。');
    $('#results').setAttribute('aria-busy', 'false');
    $('#results-summary').textContent = '等待连接本地工作区';
    $('#engine-indicator').innerHTML = '<span class="status-dot muted-dot"></span><span>本地工作区未连接</span>';
  } finally { initialising = false; schedulePoll(); }
}

fillIcons();
setView(state.view);
setMode('filename', false);
updateKindButtons();
bindEvents();
bootstrap();
