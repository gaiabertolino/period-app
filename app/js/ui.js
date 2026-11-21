import * as store from './storage.js';
import { predict, isoToDay, dayToIso, todayDay } from './model.js';
import { parseCycleCSV, toCSV, DATE_COLUMN } from './csv.js';
import { buildICS, buildShortcutPayload, shortcutURL } from './ics.js';

const $ = (sel) => document.querySelector(sel);
const MS_PER_DAY = 86400000;
const VIEWS = ['home', 'log', 'history', 'data', 'settings'];

const state = { records: [], settings: null, result: null };

// ---------- helpers ----------

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') node.className = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) if (c != null) node.append(c);
  return node;
}

const dateFromDay = (day) => new Date(day * MS_PER_DAY);
const yearOf = (day) => dateFromDay(day).getUTCFullYear();

function fmt(day, opts) {
  return new Intl.DateTimeFormat(undefined, { timeZone: 'UTC', ...opts }).format(dateFromDay(day));
}

function fmtShort(day) {
  const withYear = yearOf(day) !== yearOf(todayDay());
  return fmt(day, withYear ? { day: 'numeric', month: 'short', year: 'numeric' } : { day: 'numeric', month: 'short' });
}

function fmtLong(day) {
  const withYear = yearOf(day) !== yearOf(todayDay());
  return fmt(day, { weekday: 'short', day: 'numeric', month: 'long', ...(withYear ? { year: 'numeric' } : {}) });
}

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

let toastTimer;
function toast(message) {
  const t = $('#toast');
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
}

function isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

function canShareFiles() {
  try {
    return !!navigator.canShare?.({ files: [new File(['x'], 'x.txt', { type: 'text/plain' })] });
  } catch {
    return false;
  }
}

// Hands a file to the user: share sheet, or download/open.
async function deliver(content, filename, type, { share = false, open = false } = {}) {
  const blob = new Blob([content], { type });
  if (share) {
    const file = new File([blob], filename, { type });
    try {
      await navigator.share({ files: [file] });
      return;
    } catch (err) {
      if (err?.name === 'AbortError') return;
      // fall through to download
    }
  }
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url });
  // On iOS, opening an .ics (no download attribute) shows the "Add to Calendar" sheet.
  if (!open) a.download = filename;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function modelOptions(s) {
  return { prior: s.prior, level: s.level, minLength: s.minLength, maxLength: s.maxLength, nPredicted: s.nPredicted };
}

function regularity(result) {
  if (result.prior_only || result.sigma == null) return null;
  const s = result.sigma;
  const label = s <= 3 ? 'Regular cycle' : s <= 6 ? 'Somewhat irregular cycle' : 'Irregular cycle';
  return `${label} · typical variation ±${s.toFixed(1)} days`;
}

// ---------- data flow ----------

async function refresh() {
  [state.records, state.settings] = await Promise.all([store.getAllCycles(), store.getSettings()]);
  state.result = predict(state.records.map((r) => r.date), modelOptions(state.settings));
  render();
}

async function markRemindersStale() {
  const s = await store.getSettings();
  s.remindersStale = true;
  await store.saveSettings(s);
}

async function afterDataChange(message) {
  await markRemindersStale();
  await refresh();
  if (state.settings.shortcutSync && state.result.n_dates) await runShortcut();
  else if (message) toast(message);
}

// Opens the user's iOS Shortcut with the new predictions (see SHORTCUT.md).
async function runShortcut() {
  const r = state.result;
  if (!r.n_dates) return toast('Log at least one date first.');
  const s = await store.getSettings();
  const payload = buildShortcutPayload(r.upcoming, {
    summary: s.reminderText, alertDays: s.alertDays, alertTime: s.alertTime,
  });
  s.remindersStale = false;
  s.remindersExported = true;
  await store.saveSettings(s);
  await refresh();
  const a = el('a', { href: shortcutURL(s.shortcutName, payload) });
  document.body.append(a);
  a.click();
  a.remove();
}

const syncCalendar = () => (state.settings.shortcutSync ? runShortcut() : exportICS(false));

// ---------- rendering ----------

function render() {
  renderHome();
  renderHistory();
  renderData();
}

function renderHome() {
  const r = state.result;
  const s = state.settings;
  const today = todayDay();
  const warnings = $('#home-warnings');
  warnings.replaceChildren();

  if (r.n_dates === 0) {
    $('#next-date').textContent = '—';
    $('#next-range').textContent = 'Log the first day of your most recent period to get started, or import a CSV in Data.';
    $('#next-countdown').textContent = '';
    $('#regularity').hidden = true;
    $('#stats').hidden = true;
    $('#reminder-banner').hidden = true;
    return;
  }

  const next = isoToDay(r.next_date);
  const lo = isoToDay(r.lo_date);
  const hi = isoToDay(r.hi_date);
  $('#next-date').textContent = fmtLong(next);
  $('#next-range').textContent = `Likely ${fmtShort(lo)} – ${fmtShort(hi)} (${Math.round(r.level * 100)}% interval)`;

  const diff = next - today;
  const sinceLast = today - isoToDay(r.last_date);
  let countdown;
  if (sinceLast > s.maxLength) countdown = `Your last logged start was ${plural(sinceLast, 'day')} ago. Log your recent periods to get an up-to-date prediction.`;
  else if (diff > 1) countdown = `In ${diff} days`;
  else if (diff === 1) countdown = 'Tomorrow';
  else if (diff === 0) countdown = 'Expected today';
  else if (today <= hi) countdown = `${plural(-diff, 'day')} after the expected date, still within the likely range`;
  else countdown = `${plural(-diff, 'day')} after the expected date. If it has started, log it.`;
  $('#next-countdown').textContent = countdown;

  const reg = regularity(r);
  $('#regularity').hidden = !reg;
  $('#regularity').textContent = reg || '';

  if (r.prior_only) {
    warnings.append(el('p', { class: 'warning' },
      'Not much data yet: this prediction uses only a typical 28-day cycle. Log more period starts for a personal prediction.'));
  } else if (r.m < 3) {
    warnings.append(el('p', { class: 'warning' },
      `Based on only ${plural(r.m, 'cycle')}. The prediction gets narrower as you log more.`));
  }
  if (r.n_excluded > 0) {
    warnings.append(el('p', { class: 'warning' },
      `${plural(r.n_excluded, 'gap')} outside ${s.minLength}–${s.maxLength} days ${r.n_excluded === 1 ? 'was' : 'were'} left out of the model (marked in History).`));
  }

  const banner = $('#reminder-banner');
  banner.hidden = !s.remindersStale || bannerDismissed;
  $('#reminder-banner-text').textContent = s.remindersExported
    ? 'Prediction updated → update your calendar reminder.'
    : 'Get alerts before your period: add the predicted dates to your calendar.';
  $('#banner-export').textContent = s.shortcutSync ? 'Sync calendar' : 'Add to Calendar';

  const stats = $('#stats');
  stats.hidden = false;
  stats.replaceChildren(el('dl', {},
    el('dt', {}, 'Last period start'), el('dd', {}, fmtShort(isoToDay(r.last_date))),
    el('dt', {}, 'Average cycle'), el('dd', {}, r.mean == null ? '—' : `${r.mean.toFixed(1)} days`),
    el('dt', {}, 'Cycles used'), el('dd', {}, String(r.m)),
  ));
}

function renderHistory() {
  const list = $('#history-list');
  list.replaceChildren();
  const r = state.result;
  $('#history-summary').textContent = r.n_dates
    ? `${plural(r.n_dates, 'date')} logged · ${plural(r.m, 'cycle')} used by the model`
    : 'No dates yet.';

  const lengthTo = new Map(r.lengths.map((l) => [l.to, l]));
  const records = [...state.records].reverse(); // newest first
  for (const rec of records) {
    const l = lengthTo.get(rec.date);
    const detail = l ? `${l.length} days since the previous start` : 'First logged date';
    const li = el('li', {},
      el('div', { class: 'when' },
        el('strong', {}, fmtLong(isoToDay(rec.date))),
        el('span', { class: 'muted small' }, detail),
        l && !l.included ? el('span', { class: 'badge' }, 'not used') : null,
      ),
      el('div', { class: 'actions' },
        el('button', { type: 'button', class: 'btn small ghost', onclick: () => startEdit(li, rec) }, 'Edit'),
        el('button', { type: 'button', class: 'btn small ghost', onclick: () => removeDate(rec.date) }, 'Delete'),
      ),
    );
    list.append(li);
  }
}

function startEdit(li, rec) {
  const input = el('input', { type: 'date', value: rec.date, max: dayToIso(todayDay()), 'aria-label': 'New date' });
  const save = async () => {
    const value = input.value;
    if (!value || !Number.isFinite(isoToDay(value))) return toast('Pick a valid date.');
    if (value === rec.date) return refresh();
    if (state.records.some((r) => r.date === value)) return toast('That date is already logged.');
    await store.moveCycle(rec.date, { ...rec, date: value });
    await afterDataChange('Date updated. Prediction recalculated.');
  };
  li.replaceChildren(el('div', { class: 'edit-row' },
    input,
    el('button', { type: 'button', class: 'btn small primary', onclick: save }, 'Save'),
    el('button', { type: 'button', class: 'btn small ghost', onclick: () => refresh() }, 'Cancel'),
  ));
  input.focus();
}

async function removeDate(date) {
  if (!confirm(`Delete ${fmtLong(isoToDay(date))}?`)) return;
  await store.deleteCycle(date);
  await afterDataChange('Date deleted. Prediction recalculated.');
}

async function renderData() {
  const r = state.result;
  $('#sync-shortcut').hidden = !state.settings.shortcutSync;
  $('#ics-preview').textContent = r.n_dates
    ? `Next ${r.upcoming.length} predicted dates: ${fmtShort(isoToDay(r.upcoming[0]))} → ${fmtShort(isoToDay(r.upcoming[r.upcoming.length - 1]))}.`
    : 'Log at least one date first.';
  $('#persist-status').textContent = (await store.isPersisted())
    ? 'This browser has agreed to keep the data stored persistently.'
    : 'Persistent storage has not been granted. Keep a CSV backup.';
}

function renderSettingsForm() {
  const s = state.settings;
  $('#set-reminder').value = s.reminderText;
  $('#set-alert-days').value = s.alertDays.join(', ');
  $('#set-alert-time').value = s.alertTime;
  $('#set-shortcut-sync').checked = !!s.shortcutSync;
  $('#set-shortcut-name').value = s.shortcutName;
  $('#set-level').value = Math.round(s.level * 100);
  $('#set-n').value = s.nPredicted;
  $('#set-min').value = s.minLength;
  $('#set-max').value = s.maxLength;
  $('#set-mu0').value = s.prior.mu0;
  $('#set-kappa0').value = s.prior.kappa0;
  $('#set-alpha0').value = s.prior.alpha0;
  $('#set-beta0').value = s.prior.beta0;
  $('#settings-error').hidden = true;
}

// ---------- navigation ----------

let bannerDismissed = false;

function show(view) {
  if (!VIEWS.includes(view)) view = 'home';
  for (const v of VIEWS) $(`#view-${v}`).hidden = v !== view;
  $('#view-title').textContent = $(`#view-${view}`).dataset.title;
  for (const a of document.querySelectorAll('.tabbar a')) {
    if (a.dataset.tab === view) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  }
  if (view === 'log') {
    const today = dayToIso(todayDay());
    $('#log-date').value = today;
    $('#log-date').max = today;
  }
  if (view === 'settings' && state.settings) renderSettingsForm();
  window.scrollTo(0, 0);
}

const route = () => show(location.hash.slice(1) || 'home');

// ---------- actions ----------

async function onLog(event) {
  event.preventDefault();
  const value = $('#log-date').value;
  if (!value || !Number.isFinite(isoToDay(value))) return toast('Pick a valid date.');
  if (value > dayToIso(todayDay())) return toast('That date is in the future.');
  if (state.records.some((r) => r.date === value)) return toast('That date is already logged.');
  await store.putCycle({ date: value, extra: {} });
  store.requestPersistence();
  bannerDismissed = false;
  location.hash = '#home';
  await afterDataChange('Saved. Prediction updated → update your calendar reminder.');
}

async function onImport(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file) return;
  const report = $('#import-report');
  report.hidden = false;
  const parsed = parseCycleCSV(await file.text());
  if (!parsed.ok) {
    report.replaceChildren(el('p', { class: 'error' }, parsed.error));
    return;
  }
  const replace = document.querySelector('input[name="import-mode"]:checked').value === 'replace';
  if (replace && state.records.length && !confirm(`Replace all ${state.records.length} existing dates with this file?`)) return;

  await store.putCycles(parsed.records, { replace });
  const s = await store.getSettings();
  s.csvColumns = replace
    ? parsed.columns
    : [...s.csvColumns, ...parsed.columns.filter((c) => !s.csvColumns.includes(c))];
  if (!s.csvColumns.includes(DATE_COLUMN)) s.csvColumns.unshift(DATE_COLUMN);
  s.remindersStale = true;
  await store.saveSettings(s);
  store.requestPersistence();
  bannerDismissed = false;
  await refresh();

  const r = state.result;
  const items = [];
  if (parsed.invalid.length) {
    items.push(`${plural(parsed.invalid.length, 'row')} skipped because the date isn't a valid YYYY-MM-DD (line${parsed.invalid.length > 1 ? 's' : ''} ${parsed.invalid.slice(0, 8).map((x) => x.line).join(', ')}${parsed.invalid.length > 8 ? '…' : ''}).`);
  }
  if (parsed.duplicates.length) items.push(`${plural(parsed.duplicates.length, 'duplicate date')} ignored.`);
  const excluded = r.lengths.filter((l) => !l.included);
  if (excluded.length) {
    items.push(`${plural(excluded.length, 'gap')} outside ${s.minLength}–${s.maxLength} days won't be used by the model: ` +
      excluded.slice(0, 6).map((l) => `${l.length} days before ${l.to}`).join('; ') + (excluded.length > 6 ? '…' : '') + '.');
  }
  report.replaceChildren(
    el('p', { class: 'ok' }, `Imported ${plural(parsed.records.length, 'date')}${replace ? ' (replaced existing data)' : ''}. You now have ${plural(r.n_dates, 'date')}.`),
    items.length ? el('ul', {}, items.map((t) => el('li', {}, t))) : null,
  );
  if (s.shortcutSync && r.n_dates) await runShortcut();
}

function exportCSV(share) {
  const csv = toCSV(state.settings.csvColumns, state.records);
  return deliver(csv, `cycles-${dayToIso(todayDay())}.csv`, 'text/csv', { share });
}

async function exportICS(share) {
  const r = state.result;
  if (!r.n_dates) return toast('Log at least one date first.');
  const s = await store.getSettings();
  s.icsSequence = (s.icsSequence | 0) + 1;
  s.remindersStale = false;
  s.remindersExported = true;
  await store.saveSettings(s);
  const ics = buildICS(r.upcoming, {
    summary: s.reminderText, sequence: s.icsSequence, alertDays: s.alertDays, alertTime: s.alertTime,
  });
  await deliver(ics, 'cycle-reminders.ics', 'text/calendar', { share, open: !share && isIOS() });
  await refresh();
}

function readSettingsForm() {
  const num = (id) => Number($(id).value);
  const s = structuredClone(state.settings);
  s.reminderText = $('#set-reminder').value.trim() || 'Personal reminder';
  s.level = num('#set-level') / 100;
  s.nPredicted = num('#set-n');
  s.minLength = num('#set-min');
  s.maxLength = num('#set-max');
  s.prior = { mu0: num('#set-mu0'), kappa0: num('#set-kappa0'), alpha0: num('#set-alpha0'), beta0: num('#set-beta0') };
  const alertParts = $('#set-alert-days').value.split(/[,;\s]+/).filter(Boolean);
  s.alertDays = [...new Set(alertParts.map(Number))].sort((a, b) => b - a);
  s.alertTime = $('#set-alert-time').value || '09:00';
  s.shortcutSync = $('#set-shortcut-sync').checked;
  s.shortcutName = $('#set-shortcut-name').value.trim() || 'Cycle Sync';

  const errors = [];
  if (s.alertDays.some((d) => !Number.isInteger(d) || d < 0 || d > 60)) errors.push('Alert days must be whole numbers from 0 to 60, separated by commas.');
  if (!/^\d{2}:\d{2}$/.test(s.alertTime)) errors.push('Pick a valid alert time.');
  if (!(s.level >= 0.5 && s.level <= 0.99)) errors.push('Credible interval must be between 50 and 99%.');
  if (!(Number.isInteger(s.nPredicted) && s.nPredicted >= 1 && s.nPredicted <= 36)) errors.push('Cycles in the calendar must be a whole number from 1 to 36.');
  if (!(Number.isInteger(s.minLength) && s.minLength >= 1)) errors.push('Minimum length must be a whole number of at least 1.');
  if (!(Number.isInteger(s.maxLength) && s.maxLength > s.minLength)) errors.push('Maximum length must be a whole number above the minimum.');
  if (!(s.prior.mu0 > 0)) errors.push('μ₀ must be positive.');
  if (!(s.prior.kappa0 > 0)) errors.push('κ₀ must be positive.');
  if (!(s.prior.alpha0 > 1)) errors.push('α₀ must be greater than 1.');
  if (!(s.prior.beta0 > 0)) errors.push('β₀ must be positive.');
  return { s, errors };
}

async function onSaveSettings(event) {
  event.preventDefault();
  const { s, errors } = readSettingsForm();
  const err = $('#settings-error');
  if (errors.length) {
    err.textContent = errors.join(' ');
    err.hidden = false;
    return;
  }
  err.hidden = true;
  const old = state.settings;
  const predictionChanged = JSON.stringify(modelOptions(old)) !== JSON.stringify(modelOptions(s)) || old.reminderText !== s.reminderText
    || old.alertDays.join() !== s.alertDays.join() || old.alertTime !== s.alertTime
    || old.shortcutSync !== s.shortcutSync;
  if (predictionChanged) { s.remindersStale = true; bannerDismissed = false; }
  await store.saveSettings(s);
  await refresh();
  toast('Settings saved.');
}

async function onResetSettings() {
  if (!confirm('Restore the default settings? Your dates are not affected.')) return;
  const s = await store.getSettings();
  const keep = { icsSequence: s.icsSequence, csvColumns: s.csvColumns, remindersExported: s.remindersExported };
  await store.saveSettings({ ...structuredClone(store.DEFAULT_SETTINGS), ...keep, remindersStale: true });
  await refresh();
  renderSettingsForm();
  toast('Defaults restored.');
}

async function onDeleteAll() {
  if (!confirm('Delete ALL dates and settings from this device?')) return;
  if (!confirm('This cannot be undone. Have you exported a backup?')) return;
  await store.clearAll();
  await refresh();
  toast('All data deleted.');
}

// ---------- boot ----------

async function init() {
  $('#log-form').addEventListener('submit', onLog);
  $('#import-file').addEventListener('change', onImport);
  $('#export-csv').addEventListener('click', () => exportCSV(false));
  $('#share-csv').addEventListener('click', () => exportCSV(true));
  $('#export-ics').addEventListener('click', () => exportICS(false));
  $('#share-ics').addEventListener('click', () => exportICS(true));
  $('#banner-export').addEventListener('click', syncCalendar);
  $('#sync-shortcut').addEventListener('click', runShortcut);
  $('#banner-dismiss').addEventListener('click', () => { bannerDismissed = true; $('#reminder-banner').hidden = true; });
  $('#settings-form').addEventListener('submit', onSaveSettings);
  $('#settings-reset').addEventListener('click', onResetSettings);
  $('#delete-all').addEventListener('click', onDeleteAll);

  if (canShareFiles()) {
    $('#share-csv').hidden = false;
    $('#share-ics').hidden = false;
  }

  window.addEventListener('hashchange', route);
  await refresh();
  route();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  }
}

init().catch((err) => {
  console.error(err);
  document.body.prepend(el('p', { class: 'warning' }, `Something went wrong while loading your data: ${err?.message || err}`));
});
