// Bayesian cycle-length model.
//
// Cycle length ~ Normal(mu, sigma^2), mu and sigma^2 both unknown, with a
// conjugate Normal-Inverse-Gamma prior NIG(mu0, kappa0, alpha0, beta0).
// The posterior is closed-form; the posterior predictive for the next length
// is a Student-t. See README.md, section "The model".
//
// This module has NO imports on purpose: tests/parity_runner.mjs loads it as a
// standalone module. Keep it in sync with pipeline/fit_model.py; the parity
// test (tests/test_parity.py) checks that both give the same numbers.

export const DEFAULT_PRIOR = Object.freeze({ mu0: 28, kappa0: 1, alpha0: 2, beta0: 16 });
export const DEFAULT_OPTIONS = Object.freeze({ level: 0.8, minLength: 15, maxLength: 90, nPredicted: 12 });

// Above this many degrees of freedom the Student-t quantile is replaced by the
// normal quantile (the difference is < 0.1%).
export const NORMAL_FALLBACK_NU = 1000;

const MS_PER_DAY = 86400000;
const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

// ---------- dates (whole days since 1970-01-01, no time zones) ----------

export function isoToDay(iso) {
  const m = ISO_RE.exec(String(iso).trim());
  if (!m) return NaN;
  const y = +m[1], mo = +m[2], d = +m[3];
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (y < 1000 || dt.getUTCFullYear() !== y || dt.getUTCMonth() !== mo - 1 || dt.getUTCDate() !== d) return NaN;
  return Math.round(dt.getTime() / MS_PER_DAY);
}

export function dayToIso(day) {
  return new Date(day * MS_PER_DAY).toISOString().slice(0, 10);
}

export function todayDay(now = new Date()) {
  return Math.round(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) / MS_PER_DAY);
}

// Same rounding in JS and Python (Python's round() rounds half to even).
export function roundHalfUp(x) {
  return Math.floor(x + 0.5);
}

// ---------- special functions ----------

const LANCZOS = [
  0.99999999999980993, 676.5203681218851, -1259.1392167224028,
  771.32342877765313, -176.61502916214059, 12.507343278686905,
  -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
];

export function lgamma(x) {
  if (x < 0.5) return Math.log(Math.PI / Math.abs(Math.sin(Math.PI * x))) - lgamma(1 - x);
  x -= 1;
  let a = LANCZOS[0];
  const t = x + 7.5;
  for (let i = 1; i < 9; i++) a += LANCZOS[i] / (x + i);
  return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a);
}

// Continued fraction for the incomplete beta function (Lentz's method).
function betacf(a, b, x) {
  const MAXIT = 300, EPS = 1e-15, FPMIN = 1e-300;
  const qab = a + b, qap = a + 1, qam = a - 1;
  let c = 1;
  let d = 1 - (qab * x) / qap;
  if (Math.abs(d) < FPMIN) d = FPMIN;
  d = 1 / d;
  let h = d;
  for (let m = 1; m <= MAXIT; m++) {
    const m2 = 2 * m;
    let aa = (m * (b - m) * x) / ((qam + m2) * (a + m2));
    d = 1 + aa * d;
    if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c;
    if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d;
    h *= d * c;
    aa = (-(a + m) * (qab + m) * x) / ((a + m2) * (qap + m2));
    d = 1 + aa * d;
    if (Math.abs(d) < FPMIN) d = FPMIN;
    c = 1 + aa / c;
    if (Math.abs(c) < FPMIN) c = FPMIN;
    d = 1 / d;
    const del = d * c;
    h *= del;
    if (Math.abs(del - 1) < EPS) break;
  }
  return h;
}

// Regularized incomplete beta I_x(a, b).
export function betainc(a, b, x) {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const bt = Math.exp(lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log(1 - x));
  if (x < (a + 1) / (a + b + 2)) return (bt * betacf(a, b, x)) / a;
  return 1 - (bt * betacf(b, a, 1 - x)) / b;
}

export function tCdf(t, nu) {
  const x = nu / (nu + t * t);
  const tail = 0.5 * betainc(nu / 2, 0.5, x);
  return t > 0 ? 1 - tail : tail;
}

// Acklam's rational approximation of the standard normal quantile.
const NA = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
const NB = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01];
const NC = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
const ND = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00];

export function normQuantile(p) {
  if (!(p > 0 && p < 1)) throw new RangeError('p must be in (0, 1)');
  const plow = 0.02425;
  if (p < plow) {
    const q = Math.sqrt(-2 * Math.log(p));
    return (((((NC[0] * q + NC[1]) * q + NC[2]) * q + NC[3]) * q + NC[4]) * q + NC[5]) /
      ((((ND[0] * q + ND[1]) * q + ND[2]) * q + ND[3]) * q + 1);
  }
  if (p <= 1 - plow) {
    const q = p - 0.5;
    const r = q * q;
    return ((((((NA[0] * r + NA[1]) * r + NA[2]) * r + NA[3]) * r + NA[4]) * r + NA[5]) * q) /
      (((((NB[0] * r + NB[1]) * r + NB[2]) * r + NB[3]) * r + NB[4]) * r + 1);
  }
  const q = Math.sqrt(-2 * Math.log(1 - p));
  return -(((((NC[0] * q + NC[1]) * q + NC[2]) * q + NC[3]) * q + NC[4]) * q + NC[5]) /
    ((((ND[0] * q + ND[1]) * q + ND[2]) * q + ND[3]) * q + 1);
}

// Student-t quantile: bisection on the exact CDF (via the incomplete beta).
// Deterministic, so JS and Python agree to floating-point precision.
export function tQuantile(p, nu) {
  if (!(p > 0 && p < 1)) throw new RangeError('p must be in (0, 1)');
  if (nu >= NORMAL_FALLBACK_NU) return normQuantile(p);
  if (p === 0.5) return 0;
  if (p < 0.5) return -tQuantile(1 - p, nu);
  let lo = 0, hi = 1;
  while (tCdf(hi, nu) < p) { lo = hi; hi *= 2; }
  for (let i = 0; i < 200; i++) {
    const mid = (lo + hi) / 2;
    if (tCdf(mid, nu) < p) lo = mid; else hi = mid;
    if (hi - lo < 1e-12) break;
  }
  return (lo + hi) / 2;
}

// ---------- model ----------

export function cycleLengths(days, minLength, maxLength) {
  const out = [];
  for (let i = 1; i < days.length; i++) {
    const length = days[i] - days[i - 1];
    out.push({ from: days[i - 1], to: days[i], length, included: length >= minLength && length <= maxLength });
  }
  return out;
}

export function fitNIG(lengths, prior = DEFAULT_PRIOR) {
  const { mu0, kappa0, alpha0, beta0 } = prior;
  const m = lengths.length;
  if (m === 0) {
    return { m: 0, mean: null, S: 0, kappa_n: kappa0, mu_n: mu0, alpha_n: alpha0, beta_n: beta0 };
  }
  let sum = 0;
  for (const x of lengths) sum += x;
  const mean = sum / m;
  let S = 0;
  for (const x of lengths) S += (x - mean) * (x - mean);
  const kappa_n = kappa0 + m;
  const mu_n = (kappa0 * mu0 + m * mean) / kappa_n;
  const alpha_n = alpha0 + m / 2;
  const beta_n = beta0 + 0.5 * S + (kappa0 * m * (mean - mu0) * (mean - mu0)) / (2 * kappa_n);
  return { m, mean, S, kappa_n, mu_n, alpha_n, beta_n };
}

export function predictive(post) {
  return {
    nu: 2 * post.alpha_n,
    loc: post.mu_n,
    scale: Math.sqrt((post.beta_n * (post.kappa_n + 1)) / (post.alpha_n * post.kappa_n)),
  };
}

// Full pipeline: ISO start dates -> posterior, predictive, next date + interval.
export function predict(isoDates, options = {}) {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const prior = { ...DEFAULT_PRIOR, ...(options.prior || {}) };
  const days = [...new Set(isoDates.map(isoToDay).filter(Number.isFinite))].sort((a, b) => a - b);
  const n = days.length;

  const lengths = cycleLengths(days, opts.minLength, opts.maxLength);
  const post = fitNIG(lengths.filter((l) => l.included).map((l) => l.length), prior);
  const { nu, scale } = predictive(post);
  const q = tQuantile((1 + opts.level) / 2, nu);
  const lo_len = post.mu_n - q * scale;
  const hi_len = post.mu_n + q * scale;

  const result = {
    n_dates: n,
    ...post,
    nu,
    scale,
    q,
    level: opts.level,
    lo_len,
    hi_len,
    sigma: post.alpha_n > 1 ? Math.sqrt(post.beta_n / (post.alpha_n - 1)) : null,
    prior_only: post.m === 0,
    lengths: lengths.map((l) => ({ from: dayToIso(l.from), to: dayToIso(l.to), length: l.length, included: l.included })),
    n_excluded: lengths.filter((l) => !l.included).length,
    last_date: null,
    next_date: null,
    lo_date: null,
    hi_date: null,
    upcoming: [],
  };

  if (n > 0) {
    const last = days[n - 1];
    result.last_date = dayToIso(last);
    result.next_date = dayToIso(last + roundHalfUp(post.mu_n));
    result.lo_date = dayToIso(last + Math.max(1, roundHalfUp(lo_len)));
    result.hi_date = dayToIso(last + Math.max(1, roundHalfUp(hi_len)));
    for (let k = 1; k <= opts.nPredicted; k++) {
      result.upcoming.push(dayToIso(last + roundHalfUp(k * post.mu_n)));
    }
  }
  return result;
}
