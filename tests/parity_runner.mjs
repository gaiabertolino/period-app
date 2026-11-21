// Runs the app's own JS modules under Node, for tests/test_parity.py.
//
//   node tests/parity_runner.mjs predict <csv> [--limit k] [--level p] [--min a] [--max b]
//   node tests/parity_runner.mjs roundtrip <csv>      # parse + re-export, prints the CSV
//
// model.js and csv.js have no imports, so they are loaded from data: URLs; this
// works on any Node version >= 18 without package.json or flags.

import { readFileSync } from 'node:fs';

const jsDir = new URL('../app/js/', import.meta.url);

async function load(name) {
  const src = readFileSync(new URL(name, jsDir), 'utf8');
  return import(`data:text/javascript;base64,${Buffer.from(src).toString('base64')}`);
}

const model = await load('model.js');
const csv = await load('csv.js');

const [mode, file, ...rest] = process.argv.slice(2);
const flags = {};
for (let i = 0; i < rest.length; i += 2) flags[rest[i].replace(/^--/, '')] = rest[i + 1];

if (mode === 'quantile') {
  // node parity_runner.mjs quantile - p nu
  process.stdout.write(JSON.stringify(model.tQuantile(Number(rest[0]), Number(rest[1]))) + '\n');
  process.exit(0);
}

const parsed = csv.parseCycleCSV(readFileSync(file, 'utf8'));
if (!parsed.ok) {
  console.error(parsed.error);
  process.exit(1);
}

if (mode === 'roundtrip') {
  process.stdout.write(csv.toCSV(parsed.columns, parsed.records));
} else if (mode === 'predict') {
  let dates = parsed.records.map((r) => r.date);
  if (flags.limit !== undefined) dates = dates.slice(0, Number(flags.limit));
  const opts = {};
  if (flags.level) opts.level = Number(flags.level);
  if (flags.min) opts.minLength = Number(flags.min);
  if (flags.max) opts.maxLength = Number(flags.max);
  process.stdout.write(JSON.stringify(model.predict(dates, opts)) + '\n');
} else {
  console.error(`unknown mode ${mode}`);
  process.exit(2);
}
