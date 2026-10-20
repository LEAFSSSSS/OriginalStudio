import { icon } from './icons.js';
import { bytes, clockTime, collectionColor, date, escapeHtml as e, integer, JOB_LABELS, KIND_LABELS, locationLabel, number, OPERATION_LABELS, safeUrl } from './format.js';

export function renderRoots(roots, scope) {
  return roots.map(root => `<div class="root-row"><button class="nav-item ${scope.type === 'root' && scope.id === root.id ? 'is-active' : ''}" data-scope="root" data-id="${integer(root.id)}" title="${e(root.path)}"><span class="root-folder ${root.available === false ? 'unavailable' : ''}">${icon('folder')}</span><span class="nav-item-name">${e(root.name)}</span><span class="nav-count">${number(root.asset_count)}</span>${root.available === false ? '<span class="offline-mark" title="目录当前不可用">!</span>' : ''}</button></div>`).join('');
}

export function renderCollections(collections, scope) {
  if (!collections.length) return '<p class="nav-empty">把零散灵感，收进一个主题。</p>';
  return collections.map(collection => `<button class="nav-item collection-item ${scope.type === 'collection' && scope.id === collection.id ? 'is-active' : ''}" data-scope="collection" data-id="${integer(collection.id)}"><span class="collection-dot" style="--collection-color:${collectionColor(collection.color)}"></span><span class="nav-item-name">${e(collection.name)}</span><span class="nav-count">${number(collection.item_count)}</span></button>`).join('');
}

function thumbnail(asset) {
  const url = safeUrl(asset.thumbnail_url);
  const image = url ? `<img src="${e(url)}" alt="" loading="lazy" decoding="async">` : '';
  const fallback = `<span class="asset-fallback ${asset.kind === 'document' ? 'document-fallback' : ''}" ${url ? 'hidden' : ''}>${icon(asset.kind, '', 40)}${asset.kind === 'document' ? `<strong>${e(String(asset.extension || 'DOC').replace('.', '').toUpperCase())}</strong><span class="document-lines"></span>` : ''}</span>`;
  return `${image}${fallback}${asset.kind === 'video' ? `<span class="video-play">${icon('play', '', 17)}</span><span class="duration">${clockTime(asset.duration)}</span>` : ''}${asset.available === false ? '<span class="missing-badge">文件失联</span>' : ''}`;
}

function resultDetail(asset) {
  const score = Number(asset.score);
  const hasScore = asset.score != null && Number.isFinite(score);
  const location = locationLabel(asset.location);
  const excerpt = asset.excerpt ? `<p class="asset-excerpt" title="${e(asset.excerpt)}">${e(asset.excerpt)}</p>` : '';
  return `${excerpt}<div class="asset-result-detail">${hasScore ? `<span class="score" title="余弦相似度乘以 100；不是匹配概率">${icon('sparkle', '', 12)}${score.toFixed(1)}<span>相似分</span></span>` : ''}${location ? `<span class="location-label">${icon(asset.kind === 'video' ? 'clock' : 'document', '', 12)}${e(location)}</span>` : ''}</div>`;
}

export function renderAsset(asset, selected = false) {
  const id = integer(asset.id);
  const tags = Array.isArray(asset.tags) ? asset.tags : [];
  return `<article class="asset-card ${selected ? 'is-selected' : ''} ${asset.available === false ? 'is-unavailable' : ''}" data-asset-id="${id}"><div class="asset-visual"><button class="asset-preview-button" data-action="open" data-id="${id}" aria-label="预览 ${e(asset.name)}">${thumbnail(asset)}</button><label class="asset-select" title="选择素材"><input type="checkbox" data-select="${id}" aria-label="选择 ${e(asset.name)}" ${selected ? 'checked' : ''}><span>${icon('check', '', 13)}</span></label><button class="asset-favorite icon-button ${asset.favorite ? 'is-favorite' : ''}" data-action="favorite" data-id="${id}" aria-label="${asset.favorite ? '取消收藏' : '收藏'} ${e(asset.name)}" aria-pressed="${Boolean(asset.favorite)}">${icon('heart', '', 17)}</button></div><div class="asset-body"><div class="asset-name-row"><span class="asset-kind-icon">${icon(asset.kind, '', 15)}</span><button class="asset-name" data-action="open" data-id="${id}" title="${e(asset.name)}">${e(asset.name)}</button></div><div class="asset-meta"><span>${asset.width && asset.height ? `${integer(asset.width)} × ${integer(asset.height)}` : e(KIND_LABELS[asset.kind] || '文件')}</span><span class="meta-dot">·</span><span>${bytes(asset.bytes)}</span><time datetime="${e(asset.modified_at)}">${date(asset.modified_at)}</time></div>${resultDetail(asset)}<div class="asset-tags">${tags.slice(0, 2).map(tag => `<span>${e(tag)}</span>`).join('')}${tags.length > 2 ? `<span>+${tags.length - 2}</span>` : ''}</div></div></article>`;
}

export function renderEmpty({ noRoots = false, filtered = false, scope = 'all' } = {}) {
  const title = noRoots ? '为灵感，留一个位置。' : filtered ? '还没有找到这份灵感' : scope === 'favorites' ? '喜欢的素材，值得再看一眼。' : scope === 'collection' ? '这个灵感集，等待第一份发现。' : '目录已就绪，让素材浮现。';
  const description = noRoots ? '连接一个本地目录，开始整理图片、视频与文档。' : filtered ? '试试更短的关键词，或调整素材类型与筛选条件。' : scope === 'favorites' ? '点击素材上的爱心，把下一次需要的灵感收藏起来。' : scope === 'collection' ? '选中素材，使用“加入灵感集”将它们收在一起。' : '扫描目录会发现素材；建立索引后，还能按画面、内容与台词查找。';
  return `<div class="empty-state"><div class="empty-art" aria-hidden="true"><span class="empty-sheet sheet-back"></span><span class="empty-sheet sheet-front">${icon(noRoots ? 'folder' : filtered ? 'search' : scope === 'favorites' ? 'heart' : 'library', '', 34)}</span><span class="empty-spark">✳</span></div><p class="eyebrow">A PLACE FOR YOUR IDEAS</p><h2>${title}</h2><p>${description}</p>${noRoots ? `<button class="button primary" data-empty-action="add-root">${icon('plus')}连接素材目录</button>` : filtered ? '<button class="button secondary" data-empty-action="reset">清空搜索与筛选</button>' : scope === 'all' || scope === 'root' ? `<button class="button primary" data-empty-action="index">${icon('scan')}扫描素材目录</button>` : ''}<div class="empty-features"><span>${icon('image', '', 16)}图片</span><span>${icon('video', '', 16)}视频</span><span>${icon('document', '', 16)}文档</span></div></div>`;
}

export function renderLoading() {
  return `<div class="loading-state"><span class="loader"></span><span>正在寻找素材…</span></div>`;
}

export function renderError(message) {
  return `<div class="empty-state error-state"><div class="error-symbol">${icon('alert', '', 30)}</div><h2>暂时无法读取素材</h2><p>${e(message)}</p><button class="button secondary" data-empty-action="retry">${icon('refresh')}重新加载</button></div>`;
}

export function renderPagination(page, total, pageSize) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return '';
  const numbers = new Set([1, pages, page - 1, page, page + 1].filter(value => value > 0 && value <= pages));
  let previous = 0;
  const buttons = [...numbers].sort((a, b) => a - b).map(value => {
    const gap = value - previous > 1 ? '<span class="pagination-gap">…</span>' : '';
    previous = value;
    return `${gap}<button data-page="${value}" ${value === page ? 'aria-current="page" class="is-active"' : ''} aria-label="第 ${value} 页">${value}</button>`;
  }).join('');
  return `<span class="page-range">${number((page - 1) * pageSize + 1)}–${number(Math.min(page * pageSize, total))} / ${number(total)}</span><div class="page-buttons"><button data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''} aria-label="上一页">${icon('arrowLeft', '', 17)}</button>${buttons}<button data-page="${page + 1}" ${page >= pages ? 'disabled' : ''} aria-label="下一页">${icon('arrow', '', 17)}</button></div>`;
}

export function renderJob(job) {
  const active = ['queued', 'running', 'stopping'].includes(job.status);
  const canResume = ['stopped', 'failed', 'interrupted'].includes(job.status);
  const canRetry = job.status === 'completed' && job.failed > 0;
  const progress = job.progress == null ? null : Math.min(100, Math.max(0, Number(job.progress) || 0));
  const label = job.stage === 'discovering' || progress === null ? '正在发现文件，数量待确定' : `${number(job.done)} / ${number(job.total)} 项`;
  return `<article class="job-card ${active ? 'job-active' : ''}" data-job-id="${integer(job.id)}"><div class="job-symbol ${active ? 'is-running' : ''}">${icon(OPERATION_LABELS[job.operation] ? ({ scan: 'scan', visual: 'sparkle', documents: 'document', transcripts: 'dialogue', cleanup: 'refresh' })[job.operation] : 'tasks', '', 23)}</div><div class="job-main"><div class="job-title-row"><h2>${e(OPERATION_LABELS[job.operation] || job.operation)}</h2><span class="job-status status-${e(job.status)}">${e(JOB_LABELS[job.status] || job.status)}</span><time>${date(job.created_at, true)}</time></div><p class="job-root">${icon('folder', '', 13)}${e(job.root_name || `目录 ${job.root_id}`)}<span class="job-id">#${integer(job.id)}</span></p><div class="job-progress ${active && progress === null ? 'is-indeterminate' : ''}" role="progressbar" aria-label="任务进度" ${progress === null ? 'aria-valuetext="发现文件中"' : `aria-valuenow="${progress.toFixed(1)}" aria-valuemin="0" aria-valuemax="100"`}><span style="width:${progress ?? 25}%"></span></div><div class="job-metrics"><span>${progress === null && !active ? '尚未统计文件' : label}</span>${progress !== null ? `<strong>${progress.toFixed(0)}%</strong>` : ''}${job.skipped ? `<span>跳过 ${number(job.skipped)}</span>` : ''}${job.failed ? `<button data-job-action="detail" data-id="${integer(job.id)}" class="job-failure-link">${number(job.failed)} 项失败</button>` : ''}</div>${job.current_path && active ? `<p class="job-path" title="${e(job.current_path)}">${e(job.current_path)}</p>` : ''}${job.error ? `<p class="job-error">${e(job.error)}</p>` : ''}</div><div class="job-actions"><button class="icon-button" data-job-action="detail" data-id="${integer(job.id)}" aria-label="查看任务 ${integer(job.id)} 详情" title="任务详情">${icon('more')}</button>${active ? `<button class="button secondary small" data-job-action="stop" data-id="${integer(job.id)}" ${job.status === 'stopping' ? 'disabled' : ''}>${icon('stop', '', 14)}停止</button>` : canResume ? `<button class="button secondary small" data-job-action="resume" data-id="${integer(job.id)}">${icon('play', '', 14)}继续</button>` : canRetry ? `<button class="button secondary small" data-job-action="retry" data-id="${integer(job.id)}">${icon('refresh', '', 14)}重试失败项</button>` : ''}</div></article>`;
}

export function renderJobs(jobs) {
  if (!jobs.length) return `<div class="empty-state"><div class="empty-art"><span class="empty-sheet sheet-back"></span><span class="empty-sheet sheet-front">${icon('tasks', '', 34)}</span></div><h2>让素材，成为可搜索的记忆。</h2><p>从扫描目录开始，再按需要建立视觉、文档与台词索引。</p><button class="button primary" data-empty-action="index">${icon('plus')}创建第一个任务</button></div>`;
  return jobs.map(renderJob).join('');
}
