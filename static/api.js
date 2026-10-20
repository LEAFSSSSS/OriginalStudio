let session = null;
let sessionPromise = null;

export class ApiError extends Error {
  constructor(message, code, status) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

async function readResponse(response) {
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(data?.error?.message || `请求失败（${response.status}）`, data?.error?.code || 'request_failed', response.status);
  return data;
}

export async function getSession() {
  if (session) return session;
  if (!sessionPromise) {
    sessionPromise = fetch('/api/session', { cache: 'no-store', credentials: 'same-origin' })
      .then(readResponse).then(value => { session = value; return value; })
      .finally(() => { sessionPromise = null; });
  }
  return sessionPromise;
}

async function request(path, { method = 'GET', body, signal, retried = false } = {}) {
  const headers = { Accept: 'application/json' };
  if (method !== 'GET') headers['X-Studio-Token'] = (await getSession()).token;
  if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, {
    method, signal, headers, credentials: 'same-origin', cache: 'no-store',
    body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
  });
  try { return await readResponse(response); }
  catch (error) {
    if (!retried && method !== 'GET' && error.status === 403 && error.code === 'local_access_denied') {
      const previousToken = headers['X-Studio-Token'];
      session = null;
      const currentSession = await getSession();
      if (currentSession.token !== previousToken) return request(path, { method, body, signal, retried: true });
    }
    throw error;
  }
}

function query(values = {}) {
  const parameters = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') parameters.set(key, String(value));
  });
  return parameters.size ? `?${parameters}` : '';
}

export const api = {
  status: () => request('/api/status'),
  roots: () => request('/api/roots'),
  addRoot: body => request('/api/roots', { method: 'POST', body }),
  removeRoot: id => request(`/api/roots/${id}`, { method: 'DELETE' }),
  folders: (path = '', signal) => request('/api/folders/list', { method: 'POST', body: { path }, signal }),
  assets: (filters, signal) => request(`/api/assets${query(filters)}`, { signal }),
  search: (body, signal) => request('/api/search', { method: 'POST', body, signal }),
  reference: (file, signal) => { const body = new FormData(); body.append('file', file); return request('/api/references', { method: 'POST', body, signal }); },
  asset: (id, signal) => request(`/api/assets/${id}`, { signal }),
  updateAsset: (id, body) => request(`/api/assets/${id}`, { method: 'PATCH', body }),
  batch: body => request('/api/assets/batch', { method: 'POST', body }),
  reveal: id => request(`/api/assets/${id}/reveal`, { method: 'POST', body: {} }),
  clip: (id, body) => request(`/api/assets/${id}/clip`, { method: 'POST', body }),
  collections: () => request('/api/collections'),
  addCollection: body => request('/api/collections', { method: 'POST', body }),
  updateCollection: (id, body) => request(`/api/collections/${id}`, { method: 'PATCH', body }),
  removeCollection: id => request(`/api/collections/${id}`, { method: 'DELETE' }),
  jobs: () => request('/api/jobs?limit=50'),
  job: (id, signal) => request(`/api/jobs/${id}`, { signal }),
  createJob: body => request('/api/jobs', { method: 'POST', body }),
  stopJob: id => request(`/api/jobs/${id}/stop`, { method: 'POST', body: {} }),
  resumeJob: id => request(`/api/jobs/${id}/resume`, { method: 'POST', body: {} }),
  backup: () => request('/api/backups', { method: 'POST', body: {} }),
};
