// CSV import/export for the canonical schema (one row per period start):
//
//   cycle_start_date[,extra columns...]
//   2021-03-04
//
// Extra columns are ignored by the model but kept on import and written back
// on export. No imports on purpose (loaded standalone by the parity runner).

export const DATE_COLUMN = 'cycle_start_date';

const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

export function isValidIsoDate(s) {
  const m = ISO_RE.exec(s);
  if (!m) return false;
  const y = +m[1], mo = +m[2], d = +m[3];
  const dt = new Date(Date.UTC(y, mo - 1, d));
  return y >= 1000 && dt.getUTCFullYear() === y && dt.getUTCMonth() === mo - 1 && dt.getUTCDate() === d;
}

// RFC 4180 parser: quoted fields, "" escapes, commas and newlines inside quotes.
export function parseRows(text) {
  const rows = [];
  let row = [], field = '', inQuotes = false, i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i += 2; continue; }
        inQuotes = false; i++; continue;
      }
      field += ch; i++; continue;
    }
    if (ch === '"') { inQuotes = true; i++; continue; }
    if (ch === ',') { row.push(field); field = ''; i++; continue; }
    if (ch === '\r' || ch === '\n') {
      row.push(field); rows.push(row); row = []; field = '';
      if (ch === '\r' && text[i + 1] === '\n') i++;
      i++; continue;
    }
    field += ch; i++;
  }
  if (field !== '' || row.length) { row.push(field); rows.push(row); }
  return rows;
}

const byDate = (a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0);

// Returns { ok, error?, columns, records: [{date, extra}], invalid, duplicates }.
export function parseCycleCSV(text) {
  const rows = parseRows(String(text).replace(/^﻿/, ''));
  const isBlank = (r) => r.every((f) => f.trim() === '');
  const headerIndex = rows.findIndex((r) => !isBlank(r));
  if (headerIndex < 0) return { ok: false, error: 'The file is empty.' };

  const columns = rows[headerIndex].map((h) => h.trim());
  const dateIdx = columns.findIndex((h) => h.toLowerCase() === DATE_COLUMN);
  if (dateIdx < 0) return { ok: false, error: `Missing the required header "${DATE_COLUMN}".` };
  columns[dateIdx] = DATE_COLUMN;

  const records = [], invalid = [], duplicates = [];
  const seen = new Set();
  for (let r = headerIndex + 1; r < rows.length; r++) {
    const row = rows[r];
    if (isBlank(row)) continue;
    const line = r + 1;
    const value = (row[dateIdx] ?? '').trim();
    if (!isValidIsoDate(value)) { invalid.push({ line, value }); continue; }
    if (seen.has(value)) { duplicates.push({ line, value }); continue; }
    seen.add(value);
    const extra = {};
    columns.forEach((col, j) => { if (j !== dateIdx) extra[col] = row[j] ?? ''; });
    records.push({ date: value, extra });
  }
  records.sort(byDate);
  return { ok: true, columns, records, invalid, duplicates };
}

function escapeField(value) {
  const s = String(value ?? '');
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCSV(columns, records) {
  const cols = columns.includes(DATE_COLUMN) ? columns : [DATE_COLUMN, ...columns];
  const lines = [cols.map(escapeField).join(',')];
  for (const r of [...records].sort(byDate)) {
    lines.push(cols.map((c) => (c === DATE_COLUMN ? r.date : r.extra?.[c] ?? '')).map(escapeField).join(','));
  }
  return lines.join('\n') + '\n';
}
