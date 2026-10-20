import { api } from './api.js?v=0.1.1';
import { bindFolderBrowser, folderBrowserMarkup } from './folder-browser.js?v=0.1.1';
import { icon } from './icons.js';
import { collectionColor, date, escapeHtml as e, errorMessage, integer, JOB_LABELS, number, OPERATION_LABELS, parseTags, validateTags } from './format.js';
import { confirm, download, getModalGeneration, isModalCurrent, notify, openModal } from './modal.js';

const COLORS = ['#64816c', '#9a835c', '#a26f69', '#658998', '#8a7c9e', '#81994f', '#c29462'];
const OPERATIONS = [
  ['scan', 'scan', '扫描文件', '发现图片、视频与文档，同时读取文档内容'],
  ['visual', 'sparkle', '视觉索引', '用画面描述或参考图片，寻找相似素材'],
  ['documents', 'document', '文档索引', '重新读取可搜索的文字与 PDF 内容'],
  ['transcripts', 'dialogue', '台词索引', '识别视频语音，定位到对应时间片段'],
  ['cleanup', 'refresh', '清理失效索引', '清理失效文件的向量与正文索引'],
];
const CAPABILITIES = [
  ['visual', 'sparkle', '视觉与参考图搜索'],
  ['transcripts', 'dialogue', '视频语音与台词搜索'],
  ['video', 'video', '视频信息与缩略图'],
  ['pdf', 'document', 'PDF 内容读取'],
  ['export', 'clip', '视频片段导出'],
];

function colorControl(color) {
  return `<div class="color-picker-row"><input type="color" name="color" value="${collectionColor(color)}" aria-label="灵感集颜色"><div class="color-swatches">${COLORS.map(value => `<button type="button" class="color-swatch ${value === color ? 'is-active' : ''}" style="--swatch-color:${value}" data-color="${value}" aria-label="选择颜色 ${value}"></button>`).join('')}</div></div>`;
}

function bindColors(dialog) {
  dialog.querySelectorAll('[data-color]').forEach(button => button.addEventListener('click', () => {
    dialog.querySelector('[name="color"]').value = button.dataset.color;
    dialog.querySelectorAll('[data-color]').forEach(item => item.classList.toggle('is-active', item === button));
  }));
  dialog.querySelector('[name="color"]')?.addEventListener('input', () => dialog.querySelectorAll('[data-color]').forEach(item => item.classList.remove('is-active')));
}

export function createManagement({ state, refreshMetadata, setScope, refreshSearch, refreshJobs, renderSelection }) {
  async function syncAfterSave(action) {
    try { await action(); }
    catch (failure) { notify(`操作已保存，界面暂未更新：${errorMessage(failure)}`, 'info'); }
  }

  function addRoot() {
    let closeBrowser = () => {};
    openModal({ title: '连接素材目录', eyebrow: 'A NEW PLACE FOR INSPIRATION', submitLabel: '连接目录', body: `<p class="modal-description">选择存放图片、视频或文档的本地文件夹，建立属于你的素材库。</p><label>目录的完整路径<div class="path-input-row"><input name="path" placeholder="例如 G:\\素材\\摄影" required autofocus maxlength="4096" autocomplete="off"><button type="button" class="button secondary" id="pick-root" aria-controls="folder-browser" aria-expanded="false">${icon('folder', '', 15)}浏览</button></div></label>${folderBrowserMarkup}<label>显示名称 <span>可选，默认为文件夹名称</span><input name="name" placeholder="例如：日常拾光" maxlength="80"></label><label class="checkbox-line"><input type="checkbox" name="scan" checked>连接后扫描素材</label><div class="modal-info">${icon('shield')}<p>素材保留在原文件夹中。请选择已有的完整目录路径；重复或互相包含的目录不能再次添加。</p></div>`, onOpen: dialog => {
      closeBrowser = bindFolderBrowser(dialog);
    }, onClose: () => closeBrowser(), onSubmit: async data => {
      const name = String(data.get('name')).trim();
      const root = await api.addRoot({ path: String(data.get('path')).trim(), ...(name ? { name } : {}) });
      let started = false;
      if (data.has('scan')) {
        try { await api.createJob({ root_id: root.id, operation: 'scan' }); started = true; }
        catch (failure) { notify(`目录已连接，扫描未开始：${errorMessage(failure)}`, 'error'); }
      }
      state.roots.push(root);
      await syncAfterSave(refreshMetadata);
      await setScope({ type: 'root', id: root.id });
      if (started) await syncAfterSave(refreshJobs);
      notify(started ? '目录已连接，扫描任务已加入队列' : '素材目录已连接');
    } });
  }

  function rootMenu() {
    const root = state.roots.find(item => item.id === state.scope.id);
    if (!root) return;
    openModal({ title: root.name, eyebrow: 'SOURCE DIRECTORY', body: `<p class="modal-description">${root.available === false ? '这个目录当前不可用，请检查硬盘或网络连接。' : '这个目录已连接到你的素材库。'}</p><p class="detail-path">${e(root.path)}</p><div class="task-detail-grid" style="margin-top:18px"><div><span>已发现素材</span><strong>${number(root.asset_count)} 项</strong></div><div><span>连接状态</span><strong>${root.available === false ? '暂时不可用' : '可用'}</strong></div></div><div class="modal-row-actions"><button type="button" class="button secondary" id="root-scan">${icon('scan', '', 15)}扫描此目录</button><button type="button" class="button secondary danger-text" id="root-remove">${icon('logout', '', 15)}移除目录</button></div>`, onOpen: dialog => {
      dialog.querySelector('#root-scan').addEventListener('click', () => index('scan', root.id));
      dialog.querySelector('#root-remove').addEventListener('click', () => confirm({ title: '移除素材目录？', description: `“${root.name}”的目录登记与素材索引将被移除。该目录下的原始文件会保留。`, label: '移除目录', onConfirm: async () => {
        await api.removeRoot(root.id);
        state.roots = state.roots.filter(item => item.id !== root.id);
        await syncAfterSave(refreshMetadata);
        await setScope({ type: 'all' });
        notify('目录登记与索引已移除');
      } }));
    } });
  }

  function collectionEditor(collection = null) {
    const editing = Boolean(collection);
    openModal({ title: editing ? '整理灵感集' : '新建灵感集', eyebrow: 'GATHER YOUR IDEAS', submitLabel: editing ? '保存修改' : '创建灵感集', body: `<p class="modal-description">让相关的素材相遇，汇成一个新的创作主题。</p><label>灵感集名称<input name="name" value="${e(collection?.name || '')}" placeholder="例如：山野、光与日常" maxlength="80" required autofocus></label><label>主题颜色${colorControl(collection?.color || COLORS[0])}</label>${editing ? `<div class="modal-row-actions"><button type="button" class="button secondary" id="export-collection">${icon('download', '', 15)}导出 CSV 清单</button><button type="button" class="button secondary danger-text" id="delete-collection">${icon('trash', '', 15)}删除灵感集</button></div>` : ''}`, onOpen: dialog => {
      bindColors(dialog);
      dialog.querySelector('#export-collection')?.addEventListener('click', () => download(`/api/collections/${collection.id}/export.csv`, `${collection.name}.csv`));
      dialog.querySelector('#delete-collection')?.addEventListener('click', () => confirm({ title: '删除这个灵感集？', description: `“${collection.name}”及其中的归类关系将被删除，素材和原始文件会保留。`, onConfirm: async () => {
        await api.removeCollection(collection.id);
        state.collections = state.collections.filter(item => item.id !== collection.id);
        await syncAfterSave(refreshMetadata);
        if (state.scope.type === 'collection' && state.scope.id === collection.id) await setScope({ type: 'all' });
        notify('灵感集已删除');
      } }));
    }, onSubmit: async data => {
      const body = { name: String(data.get('name')).trim(), color: data.get('color') };
      if (!body.name) throw new Error('请为灵感集填写一个名称。');
      const saved = editing ? await api.updateCollection(collection.id, body) : await api.addCollection(body);
      if (editing) state.collections = state.collections.map(item => item.id === saved.id ? saved : item);
      else state.collections.push(saved);
      await syncAfterSave(refreshMetadata);
      if (!editing) await setScope({ type: 'collection', id: saved.id });
      notify(editing ? '灵感集已更新' : '灵感集已创建');
    } });
  }

  function operationMessage(operation) {
    const capabilities = state.status?.capabilities || {};
    const key = { visual: 'visual', transcripts: 'transcripts', documents: 'pdf' }[operation];
    if (key && capabilities[key]?.message) return capabilities[key].message;
    if (operation === 'scan') return '扫描会发现新素材、更新已有文件并索引文档内容。视觉和台词索引可分别建立。';
    if (operation === 'cleanup') return '清理原文件已失效的向量与正文索引，保留收藏、标签、笔记和灵感集归属。请先确认外接硬盘与网络目录均已连接。';
    return '根据当前目录中的素材，建立可搜索的内容索引。';
  }

  function index(operation = 'scan', rootId = state.scope.type === 'root' ? state.scope.id : null) {
    if (!state.roots.length) { addRoot(); return; }
    const selectedRoot = rootId || state.roots[0].id;
    openModal({ title: '让素材，变得可被发现。', eyebrow: 'BUILD YOUR CREATIVE MEMORY', submitLabel: '加入任务队列', wide: true, body: `<label>目标目录<select name="root_id">${state.roots.map(root => `<option value="${integer(root.id)}" ${root.id === selectedRoot ? 'selected' : ''}>${e(root.name)}${root.available === false ? '（当前不可用）' : ''}</option>`).join('')}</select></label><p class="modal-section-title">选择要执行的工作</p><div class="operation-options">${OPERATIONS.map(([value, symbol, title, description]) => `<label class="operation-choice"><input type="radio" name="operation" value="${value}" ${value === operation ? 'checked' : ''}><span class="operation-icon">${icon(symbol, '', 17)}</span><span>${title}<small>${description}</small></span></label>`).join('')}</div><div class="modal-info">${icon('info')}<p id="operation-message">${e(operationMessage(operation))}</p></div><label class="checkbox-line cleanup-acknowledgement" ${operation !== 'cleanup' ? 'hidden' : ''}><input type="checkbox" name="cleanup_confirm" ${operation === 'cleanup' ? 'required' : 'disabled'}><span>确认清理失效素材的向量与正文索引</span></label><label class="checkbox-line"><input type="checkbox" name="retry_failed">只重试之前失败的文件</label><p class="field-hint" style="margin-top:8px">首次运行请选择正常索引；重试仅处理此目录、此操作已有的失败记录。</p>`, onOpen: dialog => {
      dialog.querySelectorAll('[name="operation"]').forEach(input => input.addEventListener('change', () => {
        dialog.querySelector('#operation-message').textContent = operationMessage(input.value);
        const cleanup = input.value === 'cleanup';
        const acknowledgement = dialog.querySelector('[name="cleanup_confirm"]');
        acknowledgement.disabled = !cleanup;
        acknowledgement.required = cleanup;
        acknowledgement.closest('label').hidden = !cleanup;
      }));
    }, onSubmit: async data => {
      const chosenOperation = data.get('operation');
      if (chosenOperation === 'cleanup') {
        const root = state.roots.find(item => item.id === Number(data.get('root_id')));
        if (root?.available === false) throw new Error('目录当前不可用，请恢复连接后再清理失效索引。');
        if (!data.has('cleanup_confirm')) throw new Error('请确认清理失效素材的内容索引。');
      }
      await api.createJob({ root_id: Number(data.get('root_id')), operation: chosenOperation, retry_failed: data.has('retry_failed') });
      await syncAfterSave(refreshJobs);
      notify('任务已加入队列，可在“索引任务”查看进度');
    } });
  }

  function capabilities() {
    const values = state.status?.capabilities || {};
    openModal({ title: '本地引擎与能力', eyebrow: 'YOUR LOCAL TOOLKIT', wide: true, body: `<p class="modal-description">以下状态由正在运行的本地服务提供。首次建立模型索引时，可能需要下载模型文件。</p><div class="capability-list">${CAPABILITIES.map(([key, symbol, title]) => {
      const capability = values[key];
      const installed = capability?.installed === true;
      const label = !capability ? '读取中' : !installed ? '尚未安装' : capability.loaded ? '模型已加载' : '已安装';
      return `<section class="capability-item"><div class="capability-item-header">${icon(symbol)}<strong>${title}</strong><span class="capability-badge ${installed ? '' : 'is-missing'}">${label}</span></div><p>${e(capability?.message || '正在读取此项能力的状态。')}${capability?.model ? `\n模型：${e(capability.model)}` : ''}</p></section>`;
    }).join('')}</div><div class="install-help"><p>文件名搜索、收藏、标签、笔记与灵感集可直接使用。</p><p>安装可选引擎后，请重启本地服务，再刷新此面板。具体命令以上述引擎提示及应用目录的 README.md 为准。</p>${state.status?.data_dir ? `<p>工作区数据：<code>${e(state.status.data_dir)}</code></p>` : ''}</div>` });
  }

  async function jobDetail(id) {
    const controller = new AbortController();
    openModal({ title: `任务详情 · #${integer(id)}`, eyebrow: 'TASK DETAILS', wide: true, body: '<div class="loading-state" style="min-height:150px"><span class="loader"></span><span>正在读取任务详情…</span></div>', onClose: () => controller.abort() });
    const generation = getModalGeneration();
    try {
      const job = await api.job(id, controller.signal);
      if (!isModalCurrent(generation)) return;
      openModal({ title: `${OPERATION_LABELS[job.operation] || '索引任务'} · #${integer(job.id)}`, eyebrow: 'TASK DETAILS', wide: true, body: `<div class="task-detail-grid"><div><span>状态</span><strong>${e(JOB_LABELS[job.status] || job.status)}</strong></div><div><span>目录</span><strong>${e(job.root_name)}</strong></div><div><span>处理 / 总数</span><strong>${number(job.done)} / ${job.total ? number(job.total) : '发现中'}</strong></div><div><span>成功 / 跳过 / 失败</span><strong>${number(Math.max(0, job.done - job.skipped - job.failed))} / ${number(job.skipped)} / ${number(job.failed)}</strong></div><div><span>创建时间</span><strong>${date(job.created_at, true)}</strong></div><div><span>最近更新</span><strong>${date(job.updated_at, true)}</strong></div></div>${job.current_path ? `<h3 class="modal-section-title">最近处理的文件</h3><p class="detail-path">${e(job.current_path)}</p>` : ''}${job.error ? `<div class="modal-info">${icon('alert')}<p>${e(job.error)}</p></div>` : ''}<h3 class="modal-section-title">失败详情${job.failed ? ` · ${number(job.failed)} 项` : ''}</h3>${job.failures?.length ? `<p class="field-hint">显示最近 ${job.failures.length} 条记录，最多 100 条。</p><ul class="failure-list">${job.failures.map(failure => `<li><strong>${e(failure.path)}</strong><p>${e(failure.code)} · ${e(failure.message)}</p></li>`).join('')}</ul>` : '<p class="field-hint">暂无文件失败记录。</p>'}` });
    } catch (failure) {
      if (failure.name === 'AbortError' || !isModalCurrent(generation)) return;
      openModal({ title: '任务详情暂时无法读取', body: `<p class="modal-description">${e(errorMessage(failure))}</p>` });
    }
  }

  async function jobAction(action, id, button) {
    if (action === 'detail') { await jobDetail(id); return; }
    const job = state.jobs.find(item => item.id === id);
    if (!job) return;
    button.disabled = true;
    try {
      if (action === 'stop') await api.stopJob(id);
      if (action === 'resume') await api.resumeJob(id);
      if (action === 'retry') await api.createJob({ root_id: job.root_id, operation: job.operation, retry_failed: true });
      await syncAfterSave(refreshJobs);
      notify(action === 'stop' ? '已请求停止，当前文件处理完毕后结束' : action === 'resume' ? '任务已重新加入队列' : '失败项已加入重试队列');
    } catch (failure) { notify(errorMessage(failure), 'error'); }
    finally { if (button.isConnected) button.disabled = false; }
  }

  async function runBatch(body) {
    const ids = [...state.selected.keys()];
    if (!ids.length) return;
    const result = await api.batch({ ids, ...body });
    state.selected.clear();
    renderSelection();
    const refreshes = await Promise.allSettled([refreshMetadata(), refreshSearch()]);
    refreshes.filter(result => result.status === 'rejected').forEach(result => notify(`整理已保存，界面暂未刷新：${errorMessage(result.reason)}`, 'info'));
    notify(`已整理 ${number(result.updated)} 份素材`);
  }

  async function bulk(action) {
    if (!state.selected.size) return;
    if (action === 'paths') {
      const paths = [...state.selected.values()].map(item => item.path).join('\n');
      try { await navigator.clipboard.writeText(paths); notify(`已复制 ${state.selected.size} 个文件路径`); }
      catch { openModal({ title: '复制原文件路径', body: `<p class="modal-description">浏览器未允许自动复制，请选中下方路径并复制。</p><textarea readonly rows="8" aria-label="已选素材的原文件路径" style="width:100%">${e(paths)}</textarea>`, onOpen: dialog => { const input = dialog.querySelector('textarea'); input.focus(); input.select(); } }); }
      return;
    }
    if (action === 'favorite') {
      try { await runBatch({ favorite: ![...state.selected.values()].every(item => item.favorite) }); }
      catch (failure) { notify(errorMessage(failure), 'error'); }
    }
    if (action === 'tags') openModal({ title: '整理素材标签', submitLabel: '应用标签', body: `<p class="modal-description">统一整理选中的 ${state.selected.size} 份素材。</p><fieldset class="tag-operation"><legend>操作方式</legend><label><input type="radio" name="tag_operation" value="add" checked>添加标签</label><label><input type="radio" name="tag_operation" value="remove">移除标签</label></fieldset><label>标签 <span>最多 30 个，每个不超过 48 个字符</span><input name="tags" placeholder="用逗号分隔，例如：旅行、自然" required autofocus maxlength="4000"></label><p class="field-hint">移除操作只影响填写的标签，素材的其他标签会保留。</p>`, onSubmit: async data => {
      const tags = validateTags(parseTags(data.get('tags')));
      if (!tags.length) throw new Error('请至少填写一个标签。');
      if (data.get('tag_operation') !== 'remove') {
        for (const asset of state.selected.values()) {
          if (new Set([...(asset.tags || []), ...tags]).size > 30) throw new Error(`“${asset.name}”添加后将超过 30 个标签，请减少新增标签或先移除部分标签。`);
        }
      }
      await runBatch({ [data.get('tag_operation') === 'remove' ? 'remove_tags' : 'add_tags']: tags });
    } });
    if (action === 'collection') {
      let createdId = null;
      openModal({ title: '把灵感收在一起', submitLabel: '加入灵感集', body: `<p class="modal-description">将选中的 ${state.selected.size} 份素材加入一个主题。</p>${state.collections.length ? `<label>选择灵感集<select name="collection_id">${state.collections.map(collection => `<option value="${integer(collection.id)}">${e(collection.name)}</option>`).join('')}</select></label>` : `<label>新灵感集名称<input name="name" placeholder="为这个主题取个名字" required autofocus maxlength="80"></label><label>主题颜色${colorControl(COLORS[0])}</label>`}`, onOpen: bindColors, onSubmit: async data => {
        if (!state.collections.length && !createdId) {
          const name = String(data.get('name')).trim();
          if (!name) throw new Error('请填写灵感集名称。');
          const created = await api.addCollection({ name, color: data.get('color') });
          createdId = created.id;
        }
        await runBatch({ collection_id: createdId || Number(data.get('collection_id')) });
      } });
    }
    if (action === 'remove-collection' && state.scope.type === 'collection') {
      try { await runBatch({ collection_id: state.scope.id, remove_collection: true }); }
      catch (failure) { notify(errorMessage(failure), 'error'); }
    }
  }

  async function backup(button) {
    button.disabled = true;
    try { const result = await api.backup(); download(result.url, result.name); notify('工作区备份已生成并开始下载'); }
    catch (failure) { notify(errorMessage(failure), 'error'); }
    finally { button.disabled = false; }
  }

  return { addRoot, rootMenu, collectionEditor, index, capabilities, jobAction, bulk, backup };
}
