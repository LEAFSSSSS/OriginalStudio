import { api } from './api.js?v=0.1.1';
import { icon } from './icons.js';
import { escapeHtml as e, errorMessage } from './format.js';
import { getModalGeneration, isModalCurrent } from './modal.js';

export const folderBrowserMarkup = `<section class="folder-browser" id="folder-browser" aria-label="浏览本机文件夹" hidden>
  <div class="folder-browser-heading"><strong>选择本机文件夹</strong><button type="button" class="text-button" data-folder-close>收起</button></div>
  <div class="folder-browser-location"><button type="button" class="icon-button" data-folder-up aria-label="上一级目录" disabled>${icon('arrow', '', 16)}</button><span data-folder-location>此电脑</span></div>
  <div class="folder-browser-list" data-folder-list role="group" aria-label="子文件夹"></div>
  <p class="folder-browser-status" data-folder-status role="status"></p>
  <div class="folder-browser-actions"><button type="button" class="text-button" data-folder-computer>此电脑</button><button type="button" class="button primary small" data-folder-select disabled>选择此文件夹</button></div>
</section>`;

export function bindFolderBrowser(dialog) {
  const generation = getModalGeneration();
  const browser = dialog.querySelector('#folder-browser');
  const trigger = dialog.querySelector('#pick-root');
  const input = dialog.querySelector('[name="path"]');
  const list = browser.querySelector('[data-folder-list]');
  const location = browser.querySelector('[data-folder-location]');
  const status = browser.querySelector('[data-folder-status]');
  const up = browser.querySelector('[data-folder-up]');
  const select = browser.querySelector('[data-folder-select]');
  let controller = null;
  let requestNumber = 0;
  let current = null;
  const currentModal = () => isModalCurrent(generation) && browser.isConnected;

  function hide() {
    controller?.abort();
    requestNumber += 1;
    browser.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    trigger.focus();
  }

  async function load(path = '') {
    controller?.abort();
    const requestController = new AbortController();
    controller = requestController;
    const request = ++requestNumber;
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; requestController.abort(); }, 12000);
    list.innerHTML = '';
    status.textContent = '正在读取文件夹…';
    list.setAttribute('aria-busy', 'true');
    select.disabled = true;
    up.disabled = true;
    try {
      const result = await api.folders(path, requestController.signal);
      if (!currentModal() || request !== requestNumber || browser.hidden) return;
      current = result;
      location.textContent = result.path || '此电脑';
      location.title = result.path || '此电脑';
      list.innerHTML = result.items.map(item => `<button type="button" class="folder-browser-item" data-folder-path="${e(item.path)}">${icon('folder', '', 17)}<span>${e(item.name)}</span>${icon('chevron', '', 13)}</button>`).join('');
      status.textContent = result.truncated ? '文件夹较多，仅显示前 1000 项；可在上方填写完整路径。' : result.items.length ? `${result.items.length} 个${result.path ? '子文件夹' : '磁盘'} · 点击进入` : '没有子文件夹，可选择当前文件夹。';
      select.disabled = !result.path;
      up.disabled = result.parent === null;
    } catch (failure) {
      if (!currentModal() || request !== requestNumber || browser.hidden) return;
      status.textContent = timedOut ? '读取超时，请检查硬盘连接，或在上方填写完整路径。' : errorMessage(failure);
      current = null;
    } finally {
      clearTimeout(timeout);
      if (currentModal() && request === requestNumber) list.removeAttribute('aria-busy');
    }
  }

  trigger.addEventListener('click', () => {
    if (!browser.hidden) { hide(); return; }
    browser.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    load(input.value.trim());
  });
  browser.querySelector('[data-folder-close]').addEventListener('click', hide);
  browser.querySelector('[data-folder-computer]').addEventListener('click', () => load());
  up.addEventListener('click', () => { if (current?.parent !== null && current) load(current.parent); });
  list.addEventListener('click', event => {
    const item = event.target.closest('[data-folder-path]');
    if (item && list.contains(item)) load(item.dataset.folderPath);
  });
  select.addEventListener('click', () => {
    if (!current?.path || select.disabled) return;
    input.value = current.path;
    hide();
    input.focus();
  });
  return () => { requestNumber += 1; controller?.abort(); };
}
