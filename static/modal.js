import { icon } from './icons.js';
import { escapeHtml as e, errorMessage, safeUrl } from './format.js';

const dialog = document.querySelector('#modal');
let returnFocus = null;
let returnFocusSelector = '';
let closeHandler = null;
let submitHandler = null;
let busy = false;
let generation = 0;

dialog.addEventListener('close', () => {
  if (dialog.open) return;
  generation += 1;
  const handler = closeHandler;
  closeHandler = null;
  submitHandler = null;
  busy = false;
  handler?.();
  const target = returnFocus?.isConnected ? returnFocus : returnFocusSelector ? document.querySelector(returnFocusSelector) : null;
  (target?.getClientRects().length ? target : document.querySelector('#main'))?.focus({ preventScroll: true });
});
dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
dialog.addEventListener('click', event => {
  if (busy) { event.preventDefault(); event.stopImmediatePropagation(); }
}, true);
dialog.addEventListener('click', event => {
  if (event.target.closest('[data-modal-close]') && !busy) dialog.close();
  if (event.target === dialog && !busy) {
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  }
});
dialog.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || !submitHandler) return;
  const submissionGeneration = generation;
  const handler = submitHandler;
  const form = event.target;
  const data = new FormData(form);
  const button = dialog.querySelector('[type="submit"]');
  const error = dialog.querySelector('.modal-error');
  const controls = [...form.querySelectorAll('button, input, select, textarea')].map(control => ({ control, disabled: control.disabled }));
  const wasInert = form.inert;
  let focusError = false;
  error.hidden = true;
  busy = true;
  controls.forEach(({ control }) => { control.disabled = true; });
  form.inert = true;
  form.setAttribute('aria-busy', 'true');
  if (button) button.classList.add('is-busy');
  dialog.focus({ preventScroll: true });
  try {
    const result = await handler(data, form);
    if (isModalCurrent(submissionGeneration) && result !== false) dialog.close();
  } catch (failure) {
    if (isModalCurrent(submissionGeneration)) {
      error.textContent = errorMessage(failure);
      error.hidden = false;
      focusError = true;
    }
  } finally {
    if (generation === submissionGeneration) {
      busy = false;
      controls.forEach(({ control, disabled }) => { control.disabled = disabled; });
      form.inert = wasInert;
      form.removeAttribute('aria-busy');
      button?.classList.remove('is-busy');
      if (focusError && dialog.open) error.focus();
    }
  }
});

export function openModal({ title, eyebrow = '', body, submitLabel = '保存', destructive = false, wide = false, onSubmit, onOpen, onClose, footer = '' }) {
  generation += 1;
  busy = false;
  const modalGeneration = generation;
  const alreadyOpen = dialog.open;
  if (!alreadyOpen) {
    returnFocus = document.activeElement;
    returnFocusSelector = returnFocus?.id ? `#${CSS.escape(returnFocus.id)}` : returnFocus?.dataset.jobAction ? `[data-job-action="${CSS.escape(returnFocus.dataset.jobAction)}"][data-id="${Number(returnFocus.dataset.id)}"]` : '';
  }
  else closeHandler?.();
  closeHandler = onClose;
  submitHandler = onSubmit;
  dialog.classList.toggle('modal-wide', wide);
  dialog.setAttribute('tabindex', '-1');
  dialog.innerHTML = `<form class="modal-form"><div class="modal-heading">${eyebrow ? `<p class="eyebrow">${e(eyebrow)}</p>` : ''}<h2 id="modal-title">${e(title)}</h2><button type="button" class="icon-button modal-close" data-modal-close aria-label="关闭对话框">${icon('close')}</button></div><div class="modal-body">${body}</div><p class="modal-error" role="alert" tabindex="-1" hidden></p><div class="modal-footer">${footer}<button type="button" class="button secondary" data-modal-close>${onSubmit ? '取消' : '关闭'}</button>${onSubmit ? `<button type="submit" class="button ${destructive ? 'danger' : 'primary'}">${e(submitLabel)}</button>` : ''}</div></form>`;
  if (!alreadyOpen) dialog.showModal();
  onOpen?.(dialog);
  requestAnimationFrame(() => { if (isModalCurrent(modalGeneration)) dialog.querySelector('[autofocus]')?.focus(); });
  return dialog;
}

export function getModalGeneration() { return generation; }
export function isModalCurrent(value) { return dialog.open && generation === value; }

export function confirm({ title, description, label = '确认删除', onConfirm }) {
  return openModal({ title, body: `<div class="confirmation-symbol">${icon('alert', '', 26)}</div><p class="confirmation-description">${e(description)}</p>`, submitLabel: label, destructive: true, onSubmit: onConfirm });
}

export function notify(message, type = 'success') {
  const item = document.createElement('div');
  item.className = `toast toast-${type}`;
  item.setAttribute('role', type === 'error' ? 'alert' : 'status');
  item.innerHTML = `${icon(type === 'error' ? 'alert' : type === 'info' ? 'info' : 'check', '', 17)}<span></span><button class="icon-button" aria-label="关闭通知">${icon('close', '', 15)}</button>`;
  item.querySelector('span').textContent = message;
  item.querySelector('button').addEventListener('click', () => item.remove());
  document.querySelector('#toast-region').append(item);
  setTimeout(() => item.remove(), type === 'error' ? 9000 : 5000);
}

export function download(url, name = '') {
  const href = safeUrl(url);
  if (!href) throw new Error('下载地址无效，请重试。');
  const link = document.createElement('a');
  link.href = href;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
}
