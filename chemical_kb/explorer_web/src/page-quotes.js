import {QUOTES} from './page-quotes-data.js';

export const QUOTE_STORAGE_KEY = 'chemical-page-quotes-v3';

const pools = new Map();

export function candidatesFor(page) {
  if (!pools.has(page)) {
    pools.set(page, QUOTES.filter(quote => quote.pages.includes(page)));
  }
  return pools.get(page);
}

function sessionStorageOrNull() {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null;
  } catch {
    return null;
  }
}

function readState(storage) {
  try {
    const raw = storage?.getItem(QUOTE_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function writeState(storage, state) {
  try {
    storage?.setItem(QUOTE_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // A disabled or full sessionStorage must not affect the page.
  }
}

export function pickQuote(page, {storage = undefined, random = Math.random} = {}) {
  const pool = candidatesFor(page);
  if (!pool.length) return null;

  const store = storage === undefined ? sessionStorageOrNull() : storage;
  const state = readState(store);
  const current = state[page] && typeof state[page] === 'object' ? state[page] : {};
  const known = new Set(pool.map(quote => quote.id));
  const last = typeof current.last === 'string' && known.has(current.last) ? current.last : '';
  const available = pool.length > 1 ? pool.filter(quote => quote.id !== last) : pool;

  const value = Number(random());
  const index = Math.max(0, Math.min(available.length - 1, Math.floor((Number.isFinite(value) ? value : 0) * available.length)));
  const quote = available[index] || available[0];
  state[page] = {last: quote.id};
  writeState(store, state);
  return quote;
}
