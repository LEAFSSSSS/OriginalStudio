import { api } from './api.js?v=0.1.1';
import { icon } from './icons.js';
import { bytes, clockTime, collectionColor, date, escapeHtml as e, errorMessage, integer, KIND_LABELS, locationLabel, parseTags, safeUrl, validateTags } from './format.js';
import { download, notify } from './modal.js';

const STATE_LABELS = { pending: '待索引', ready: '就绪', failed: '失败', skipped: '已跳过' };

export function createAssetDrawer({ getCollections, onChange }) {
  const dialog = document.querySelector('#asset-dialog');
  let asset = null;
  let controller = null;
  let returnFocus = null;
  let generation = 0;
  let playbackEnd = null;

  dialog.addEventListener('close', () => {
    if (dialog.open) return;
    const assetId = asset?.id;
    controller?.abort();
    generation += 1;
    dialog.querySelector('video')?.pause();
    asset = null;
    if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
    else (document.querySelector(`[data-action="open"][data-id="${integer(assetId)}"]`) || document.querySelector('#search-query')).focus({ preventScroll: true });
  });

  async function open(item) {
    const requestGeneration = ++generation;
    controller?.abort();
    controller = new AbortController();
    playbackEnd = null;
    returnFocus = document.activeElement;
    dialog.innerHTML = `<div class="drawer-loading"><h2 id="asset-title" class="visually-hidden">素材详情</h2><span class="loader"></span><p>正在打开素材…</p><button class="icon-button drawer-close" data-drawer-close aria-label="关闭素材详情">${icon('close')}</button></div>`;
    if (!dialog.open) dialog.showModal();
    try {
      const detail = await api.asset(item.id, controller.signal);
      if (requestGeneration !== generation) return;
      asset = { ...item, ...detail, location: item.location || detail.location, excerpt: item.excerpt || detail.excerpt };
      render();
    } catch (error) {
      if (error.name === 'AbortError' || requestGeneration !== generation) return;
      dialog.innerHTML = `<div class="drawer-loading"><span class="error-symbol">${icon('alert', '', 30)}</span><h2 id="asset-title">无法打开素材</h2><p>${e(errorMessage(error))}</p><button class="button secondary" data-drawer-close>关闭</button></div>`;
    }
  }

  function mediaMarkup() {
    const media = safeUrl(asset.media_url || `/api/assets/${asset.id}/media`);
    if (asset.available === false) return `<div class="preview-unavailable">${icon('link', '', 46)}<h3>原文件暂时不可用</h3><p>重新连接目录后，即可继续预览。</p></div>`;
    if (asset.kind === 'image') return `<button type="button" class="image-stage" aria-label="切换图片原始尺寸" data-zoom><img src="${e(media)}" alt="${e(asset.name)}"></button>`;
    if (asset.kind === 'video') return `<video id="preview-video" controls playsinline preload="metadata" ${safeUrl(asset.thumbnail_url) ? `poster="${e(safeUrl(asset.thumbnail_url))}"` : ''} src="${e(media)}" aria-label="${e(asset.name)}"></video>`;
    return `<div class="document-stage"><div class="document-cover">${icon('document', '', 60)}<strong>${e(String(asset.extension || 'DOC').replace('.', '').toUpperCase())}</strong><span></span><span></span><span></span></div><h3>${e(asset.name)}</h3><p>文档内容摘录见下方，原文件可下载查看。</p><a class="button secondary" href="${e(media)}${media.includes('?') ? '&' : '?'}download=true" download>${icon('download', '', 17)}下载原文档</a></div>`;
  }

  function segmentsMarkup() {
    const segments = Array.isArray(asset.segments) ? asset.segments : [];
    if (!segments.length && !asset.excerpt) return '';
    return `<section class="segments-section"><div class="section-label"><span>${icon(asset.kind === 'video' ? 'dialogue' : 'document', '', 16)}${asset.kind === 'video' ? '台词与片段' : '内容摘录'}</span><span>${segments.length ? `${segments.length} 段` : ''}</span></div>${asset.excerpt ? `<div class="match-excerpt"><span>本次匹配${locationLabel(asset.location) ? ` · ${e(locationLabel(asset.location))}` : ''}</span><p>${e(asset.excerpt)}</p>${asset.kind === 'video' && asset.location?.start != null ? `<button class="text-button" data-seek="${Number(asset.location.start)}" data-end="${Number(asset.location.end) || ''}">${icon('play', '', 14)}播放匹配片段</button>` : ''}</div>` : ''}<div class="segments-list">${segments.map(segment => `<div class="segment">${segment.start != null && asset.kind === 'video' ? `<button class="segment-location" data-seek="${Number(segment.start)}" data-end="${Number(segment.end) || ''}" aria-label="播放 ${clockTime(segment.start)} 的片段">${icon('play', '', 12)}${clockTime(segment.start)}</button>` : `<span class="segment-location">${segment.page != null ? `第 ${integer(segment.page)} 页` : '摘录'}</span>`}<p>${e(segment.text)}</p></div>`).join('')}</div></section>`;
  }

  function collectionsMarkup() {
    const collections = getCollections();
    if (!collections.length) return '<p class="field-hint">在侧栏新建灵感集，按主题归拢素材。</p>';
    return `<div class="drawer-collections">${collections.map(collection => `<label class="collection-choice"><input type="checkbox" name="collection_ids" value="${integer(collection.id)}" ${(asset.collection_ids || []).includes(collection.id) ? 'checked' : ''}><span class="collection-dot" style="--collection-color:${collectionColor(collection.color)}"></span><span>${e(collection.name)}</span></label>`).join('')}</div>`;
  }

  function render() {
    const location = locationLabel(asset.location);
    const media = safeUrl(asset.media_url || `/api/assets/${asset.id}/media`);
    dialog.innerHTML = `<div class="drawer-layout"><section class="drawer-preview"><header class="preview-header"><span>${icon(asset.kind, '', 17)}${e(KIND_LABELS[asset.kind] || '素材')}预览</span><span>${location ? e(location) : asset.width && asset.height ? `${integer(asset.width)} × ${integer(asset.height)}` : bytes(asset.bytes)}</span></header><div class="media-stage">${mediaMarkup()}</div>${asset.kind === 'video' && location ? `<div class="matched-segment">${icon('clock', '', 15)}定位到 ${e(location)}<button class="text-button" data-seek="${Number(asset.location.start) || 0}" data-end="${Number(asset.location.end) || ''}">${icon('play', '', 13)}播放片段</button></div>` : ''}${segmentsMarkup()}</section><section class="drawer-details"><header class="drawer-heading"><p class="eyebrow">ASSET DETAILS</p><h2 id="asset-title">${e(asset.name)}</h2><button class="icon-button drawer-close" data-drawer-close aria-label="关闭素材详情">${icon('close')}</button></header><div class="drawer-scroll"><div class="file-facts"><div><span>文件类型</span><strong>${e(String(asset.extension || asset.kind).replace('.', '').toUpperCase())}</strong></div><div><span>文件大小</span><strong>${bytes(asset.bytes)}</strong></div><div><span>修改日期</span><strong>${date(asset.modified_at)}</strong></div>${asset.duration ? `<div><span>视频时长</span><strong>${clockTime(asset.duration)}</strong></div>` : ''}</div><div class="file-path"><span>原文件位置</span><p>${e(asset.path)}</p><div><button class="text-button" data-reveal ${asset.available === false ? 'disabled' : ''}>${icon('folder', '', 15)}在文件夹中显示</button><button class="text-button" data-copy-path>${icon('copy', '', 14)}复制</button></div></div><form id="asset-edit-form"><label class="favorite-choice"><span>${icon('heart', '', 18)}收藏这份素材</span><input type="checkbox" name="favorite" ${asset.favorite ? 'checked' : ''}><span class="switch" aria-hidden="true"></span></label><label class="field-label">标签 <span>最多 30 个，每个 48 字；用逗号分隔</span><input name="tags" value="${e((asset.tags || []).join(', '))}" placeholder="添加标签，例如：旅行、灵感" maxlength="4000"></label><label class="field-label">素材笔记<textarea name="notes" rows="4" placeholder="为下一次创作，留下一点线索…" maxlength="4000">${e(asset.notes)}</textarea></label><div class="field-label"><span>加入灵感集</span>${collectionsMarkup()}</div><p class="drawer-save-error" role="alert" hidden></p><button class="button primary save-asset" type="submit">${icon('check', '', 16)}保存整理</button></form><details class="index-details"><summary>索引状态${icon('down', '', 14)}</summary><dl>${[['visual_state', '视觉'], ['text_state', '文档'], ['transcript_state', '台词']].map(([key, label]) => `<div><dt>${label}</dt><dd class="index-state state-${e(asset[key] || 'pending')}">${e(STATE_LABELS[asset[key]] || '待索引')}</dd></div>`).join('')}</dl>${asset.error ? `<p class="index-error">${e(asset.error)}</p>` : ''}</details>${asset.kind === 'video' && asset.available !== false ? clipMarkup() : ''}</div><footer class="drawer-footer"><a class="button secondary" href="${e(media)}${media.includes('?') ? '&' : '?'}download=true" download ${asset.available === false ? 'aria-disabled="true" tabindex="-1"' : ''}>${icon('download', '', 16)}下载原文件</a><button class="button secondary" data-drawer-close>完成</button></footer></section></div>`;
    const video = dialog.querySelector('video');
    if (video) {
      video.addEventListener('loadedmetadata', () => { if (asset?.location?.start != null) video.currentTime = Math.min(Number(asset.location.start), video.duration || Infinity); }, { once: true });
      video.addEventListener('timeupdate', () => { if (playbackEnd != null && video.currentTime >= playbackEnd) { video.pause(); playbackEnd = null; } });
    }
    dialog.querySelectorAll('.media-stage img, video').forEach(element => element.addEventListener('error', () => {
      const stage = dialog.querySelector('.media-stage');
      stage.innerHTML = `<div class="preview-unavailable">${icon('alert', '', 38)}<h3>浏览器暂时无法预览此格式</h3><p>可以下载原文件，使用本地应用打开。</p></div>`;
    }, { once: true }));
    dialog.querySelector('#asset-edit-form').addEventListener('submit', save);
    dialog.querySelector('#clip-form')?.addEventListener('submit', exportClip);
    dialog.querySelector('[data-drawer-close]')?.focus({ preventScroll: true });
  }

  function clipMarkup() {
    const start = Number(asset.location?.start) || 0;
    const end = Number(asset.location?.end) || Math.min(Number(asset.duration) || 30, start + 30);
    return `<details class="clip-details"><summary>${icon('clip', '', 16)}导出视频片段${icon('down', '', 14)}</summary><form id="clip-form"><p class="field-hint">以秒为单位，单段最长 1 小时。需要本机 FFmpeg。</p><div class="clip-inputs"><label>开始（秒）<input type="number" name="start" min="0" step="0.1" value="${start.toFixed(1)}" required></label><span>—</span><label>结束（秒）<input type="number" name="end" min="0.1" step="0.1" value="${end.toFixed(1)}" required></label></div><button type="submit" class="button secondary small">${icon('clip', '', 14)}生成并下载片段</button><p class="clip-message" aria-live="polite"></p></form></details>`;
  }

  async function save(event) {
    event.preventDefault();
    const form = event.target;
    const button = form.querySelector('[type="submit"]');
    if (button.disabled || !asset) return;
    const data = new FormData(form);
    const currentId = asset.id;
    form.querySelector('.drawer-save-error').hidden = true;
    let body;
    try {
      const tags = validateTags(parseTags(data.get('tags')));
      const notes = String(data.get('notes'));
      if ([...notes].length > 4000) throw new Error('素材笔记最多 4000 个字符，请缩短后再保存。');
      body = { favorite: data.has('favorite'), tags, notes, collection_ids: data.getAll('collection_ids').map(Number) };
    } catch (error) {
      const message = form.querySelector('.drawer-save-error');
      message.textContent = errorMessage(error);
      message.hidden = false;
      return;
    }
    button.disabled = true;
    try {
      const updated = await api.updateAsset(currentId, body);
      if (asset?.id === currentId) asset = { ...asset, ...updated };
      await onChange(updated);
      notify('素材整理已保存');
    } catch (error) {
      const message = form.querySelector('.drawer-save-error');
      message.textContent = errorMessage(error);
      message.hidden = false;
    } finally { button.disabled = false; }
  }

  async function exportClip(event) {
    event.preventDefault();
    const form = event.target;
    const button = form.querySelector('[type="submit"]');
    if (button.disabled || !asset) return;
    const data = new FormData(form);
    const start = Number(data.get('start'));
    const end = Number(data.get('end'));
    const message = form.querySelector('.clip-message');
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || end - start > 3600 || (asset.duration && end > asset.duration + 0.1)) {
      message.textContent = '请填写有效的起止秒数，结束需晚于开始且位于视频时长内，单段不超过 3600 秒。';
      return;
    }
    button.disabled = true;
    message.textContent = '正在生成片段，请稍候…';
    try {
      const result = await api.clip(asset.id, { start, end });
      download(result.url, result.name);
      message.innerHTML = `片段已生成。<a href="${e(safeUrl(result.url))}" download>再次下载</a>`;
    } catch (error) { message.textContent = errorMessage(error); }
    finally { button.disabled = false; }
  }

  dialog.addEventListener('click', async event => {
    if (event.target.closest('[data-drawer-close]')) { dialog.close(); return; }
    const seek = event.target.closest('[data-seek]');
    if (seek) {
      const video = dialog.querySelector('video');
      if (video) { video.currentTime = Number(seek.dataset.seek) || 0; playbackEnd = Number(seek.dataset.end) || null; video.play().catch(() => {}); }
    }
    if (event.target.closest('[data-zoom]')) event.target.closest('[data-zoom]').classList.toggle('is-zoomed');
    if (event.target.closest('[data-reveal]') && asset) {
      try { await api.reveal(asset.id); } catch (error) { notify(errorMessage(error), 'error'); }
    }
    if (event.target.closest('[data-copy-path]') && asset) {
      try { await navigator.clipboard.writeText(asset.path); notify('原文件路径已复制'); } catch { notify('浏览器未能复制，请从“原文件位置”选取文本。', 'error'); }
    }
    if (event.target.closest('[aria-disabled="true"]')) event.preventDefault();
  });
  return { open, close: () => { if (dialog.open) dialog.close(); } };
}
