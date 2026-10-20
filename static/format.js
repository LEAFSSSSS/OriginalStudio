export const KIND_LABELS = { image: '图片', video: '视频', document: '文档' };
export const MODE_LABELS = { filename: '文件名', semantic: '语义', reference: '以图搜图', document: '文档内容', dialogue: '视频台词' };
export const OPERATION_LABELS = { scan: '扫描文件', visual: '视觉索引', documents: '文档索引', transcripts: '台词索引', cleanup: '清理失效索引' };
export const JOB_LABELS = { queued: '排队中', running: '进行中', stopping: '正在停止', stopped: '已停止', completed: '已完成', failed: '失败', interrupted: '已中断' };

export function escapeHtml(value = '') {
  return String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
}

export function safeUrl(value, fallback = '') {
  if (!value) return fallback;
  try {
    const url = new URL(String(value), location.origin);
    return url.origin === location.origin && url.pathname.startsWith('/api/') ? url.href : fallback;
  } catch { return fallback; }
}

export function collectionColor(value) { return /^#[0-9a-f]{6}$/i.test(value || '') ? value : '#46846e'; }
export function integer(value) { return Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : 0; }
export function number(value = 0) { return Number(value || 0).toLocaleString('zh-CN'); }
export function bytes(value) {
  const amount = Number(value || 0);
  if (amount < 1024) return `${amount} B`;
  const unit = Math.min(Math.floor(Math.log(amount) / Math.log(1024)), 3);
  return `${(amount / 1024 ** unit).toFixed(unit > 1 ? 1 : 0)} ${['B', 'KB', 'MB', 'GB'][unit]}`;
}
export function clockTime(value = 0) {
  const total = Math.max(0, Math.floor(Number(value) || 0));
  const seconds = String(total % 60).padStart(2, '0');
  const minutes = Math.floor(total / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}:${seconds}` : `${minutes}:${seconds}`;
}
export function date(value, includeTime = false) {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleString('zh-CN', includeTime ? { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false } : { year: 'numeric', month: '2-digit', day: '2-digit' });
}
export function locationLabel(location = {}) {
  if (location.page != null) return `第 ${integer(location.page)} 页`;
  if (location.start != null) return `${clockTime(location.start)}${location.end != null ? ` – ${clockTime(location.end)}` : ''}`;
  return '';
}
export function parseTags(value) { return [...new Set(String(value).split(/[,，\n]/).map(tag => tag.trim()).filter(Boolean))]; }
export function validateTags(tags) {
  if (tags.length > 30) throw new Error(`每份素材最多保留 30 个标签，当前填写了 ${tags.length} 个。请减少标签后重试。`);
  const tooLong = tags.findIndex(tag => [...tag].length > 48);
  if (tooLong >= 0) throw new Error(`第 ${tooLong + 1} 个标签超过 48 个字符，请缩短后重试。`);
  return tags;
}

function locationText(parameters, key, maximum) {
  const values = parameters.getAll(key);
  if (values.length !== 1) return '';
  const value = values[0].trim();
  return [...value].length <= maximum && !/[\u0000-\u001f\u007f]/u.test(value) ? value : '';
}

function locationDate(parameters, key) {
  const value = locationText(parameters, key, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) return '';
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value ? value : '';
}

export function parseWorkspaceLocation(search, roots = [], collections = []) {
  const parameters = new URLSearchParams(search);
  const requestedScope = locationText(parameters, 'scope', 40);
  let scope = { type: ['all', 'favorites', 'tasks'].includes(requestedScope) ? requestedScope : 'all' };
  const match = /^(root|collection):([1-9]\d{0,15})$/.exec(requestedScope);
  if (match) {
    const id = Number(match[2]);
    const items = match[1] === 'root' ? roots : collections;
    if (Number.isSafeInteger(id) && items.some(item => item.id === id)) scope = { type: match[1], id };
  }
  const requestedMode = locationText(parameters, 'mode', 20);
  const mode = Object.hasOwn(MODE_LABELS, requestedMode) ? requestedMode : 'filename';
  const requestedKind = locationText(parameters, 'kind', 20);
  const kind = Object.hasOwn(KIND_LABELS, requestedKind) ? requestedKind : '';
  const requestedSort = locationText(parameters, 'sort', 20);
  const sort = ['recent', 'name', 'oldest'].includes(requestedSort) ? requestedSort : 'recent';
  const requestedPage = locationText(parameters, 'page', 7);
  const page = /^[1-9]\d{0,6}$/.test(requestedPage) && Number(requestedPage) <= 1000000 ? Number(requestedPage) : 1;
  const filters = {};
  [['folder', 500], ['tag', 48]].forEach(([key, maximum]) => { const value = locationText(parameters, key, maximum); if (value) filters[key] = value; });
  ['date_from', 'date_to'].forEach(key => { const value = locationDate(parameters, key); if (value) filters[key] = value; });
  if (filters.date_from && filters.date_to && filters.date_from > filters.date_to) { delete filters.date_from; delete filters.date_to; }
  if (['semantic', 'reference'].includes(mode)) {
    const negative = locationText(parameters, 'negative_query', 1000);
    if (negative) filters.negative_query = negative;
    const score = locationText(parameters, 'min_score', 15);
    if (/^-?(?:0|[1-9]\d{0,2})(?:\.\d{1,8})?$/.test(score) && Number(score) >= -100 && Number(score) <= 100) filters.min_score = Number(score);
  }
  return { scope, mode, kind, sort, page, query: locationText(parameters, 'query', 1000), filters };
}

export function workspaceLocationParameters(state) {
  const parameters = new URLSearchParams();
  const scope = state.scope.type;
  if (scope === 'root' || scope === 'collection') parameters.set('scope', `${scope}:${state.scope.id}`);
  else if (scope !== 'all') parameters.set('scope', scope);
  if (state.mode !== 'filename') parameters.set('mode', state.mode);
  if (state.query) parameters.set('query', state.query);
  if (state.kind) parameters.set('kind', state.kind);
  ['folder', 'tag', 'date_from', 'date_to', 'negative_query', 'min_score'].forEach(key => {
    if (state.filters[key] != null && state.filters[key] !== '') parameters.set(key, String(state.filters[key]));
  });
  if (state.page > 1) parameters.set('page', String(state.page));
  if (state.sort !== 'recent') parameters.set('sort', state.sort);
  return parameters;
}

export function errorMessage(error) {
  if (error instanceof TypeError && /fetch|network|load failed/i.test(error.message)) return '无法连接本地服务，请确认服务正在运行。';
  return error?.message || '操作未完成，请稍后重试。';
}
