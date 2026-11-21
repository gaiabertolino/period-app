// IndexedDB persistence. Everything stays in this browser's sandbox.
//
// Stores:
//   cycles   { date: 'YYYY-MM-DD', extra: { column: value } }   keyPath 'date'
//   settings { key: 'settings', ... }                         keyPath 'key'

import { DEFAULT_PRIOR, DEFAULT_OPTIONS } from './model.js';
import { DATE_COLUMN } from './csv.js';
import { DEFAULT_ALERT_DAYS, DEFAULT_ALERT_TIME } from './ics.js';

const DB_NAME = 'cycle-app';
const DB_VERSION = 1;

export const DEFAULT_SETTINGS = Object.freeze({
  key: 'settings',
  prior: { ...DEFAULT_PRIOR },
  level: DEFAULT_OPTIONS.level,
  minLength: DEFAULT_OPTIONS.minLength,
  maxLength: DEFAULT_OPTIONS.maxLength,
  nPredicted: DEFAULT_OPTIONS.nPredicted,
  reminderText: 'Personal reminder',
  alertDays: [...DEFAULT_ALERT_DAYS],
  alertTime: DEFAULT_ALERT_TIME,
  shortcutSync: false,
  shortcutName: 'Cycle Sync',
  icsSequence: 0,
  csvColumns: [DATE_COLUMN],
  remindersStale: true,
  remindersExported: false,
});

let dbPromise = null;

function open() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains('cycles')) db.createObjectStore('cycles', { keyPath: 'date' });
        if (!db.objectStoreNames.contains('settings')) db.createObjectStore('settings', { keyPath: 'key' });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  return dbPromise;
}

const request = (r) => new Promise((resolve, reject) => {
  r.onsuccess = () => resolve(r.result);
  r.onerror = () => reject(r.error);
});

const completion = (t) => new Promise((resolve, reject) => {
  t.oncomplete = () => resolve();
  t.onerror = () => reject(t.error);
  t.onabort = () => reject(t.error);
});

async function write(storeNames, fn) {
  const db = await open();
  const t = db.transaction(storeNames, 'readwrite');
  fn(t);
  return completion(t);
}

// Sorted by date (IndexedDB returns records in key order).
export async function getAllCycles() {
  const db = await open();
  return request(db.transaction('cycles').objectStore('cycles').getAll());
}

export function putCycle(record) {
  return write('cycles', (t) => t.objectStore('cycles').put(record));
}

export function moveCycle(oldDate, record) {
  return write('cycles', (t) => {
    const s = t.objectStore('cycles');
    s.delete(oldDate);
    s.put(record);
  });
}

export function deleteCycle(date) {
  return write('cycles', (t) => t.objectStore('cycles').delete(date));
}

export function putCycles(records, { replace = false } = {}) {
  return write('cycles', (t) => {
    const s = t.objectStore('cycles');
    if (replace) s.clear();
    for (const r of records) s.put(r);
  });
}

export function clearAll() {
  return write(['cycles', 'settings'], (t) => {
    t.objectStore('cycles').clear();
    t.objectStore('settings').clear();
  });
}

export async function getSettings() {
  const db = await open();
  const saved = await request(db.transaction('settings').objectStore('settings').get('settings'));
  const merged = structuredClone({ ...DEFAULT_SETTINGS, ...(saved || {}) });
  merged.prior = { ...DEFAULT_PRIOR, ...(saved?.prior || {}) };
  return merged;
}

export function saveSettings(settings) {
  return write('settings', (t) => t.objectStore('settings').put({ ...settings, key: 'settings' }));
}

// Ask the browser not to evict our data under storage pressure (best effort).
export async function requestPersistence() {
  try {
    if (navigator.storage?.persisted && !(await navigator.storage.persisted())) {
      return await navigator.storage.persist();
    }
    return (await navigator.storage?.persisted?.()) ?? false;
  } catch {
    return false;
  }
}

export async function isPersisted() {
  try { return (await navigator.storage?.persisted?.()) ?? false; } catch { return false; }
}
