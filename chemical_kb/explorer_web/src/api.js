export async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers }
  });
  if (!response.ok) {
    let message = response.statusText;
    try { message = (await response.json()).error || message; } catch {}
    throw new Error(message || `HTTP ${response.status}`);
  }
  return response.json();
}

export function post(path, body) {
  return api(path, { method: 'POST', body: JSON.stringify(body) });
}

export function today() {
  const now = new Date(); return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export function validAt(item, date) {
  if (!date) return true;
  return (!item.valid_from || item.valid_from.slice(0, 10) <= date)
    && (!item.valid_to || date < item.valid_to.slice(0, 10));
}

export function compactNumber(value) {
  return Number(value || 0).toLocaleString('zh-CN');
}

export function sourceLabel(item) {
  return [item.source_doc_id || item.doc_id || '', item.page_start ? `p.${item.page_start}` : '']
    .filter(Boolean).join(' · ') || '来源未标注';
}


