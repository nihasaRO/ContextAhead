// A strict Monkey C-like runtime for the transpiled engine. Numbers are integers; Floats are boxed (MF).
class MF { constructor(v) { this.v = v; } }
const F = (v) => new MF(v);
const isF = (x) => x instanceof MF;
const val = (x) => (x instanceof MF ? x.v : x);
const issues = [];
function fail(msg) { throw new Error('MONKEYC CRASH: ' + msg); }
function warn(msg) { issues.push(msg); }
function isNum(x) { return typeof x === 'number' || x instanceof MF; }

function bin(op, a, b) {
  if (op === '==' || op === '!=') {
    let eq;
    if (a === null || b === null || a === undefined || b === undefined) eq = (a ?? null) === (b ?? null);
    else if (isNum(a) && isNum(b)) eq = val(a) === val(b);
    else if (typeof a === 'boolean' || typeof b === 'boolean') eq = a === b;
    else if (typeof a === 'string' && typeof b === 'string') { warn('String == String (reference compare on the watch): ' + a); eq = a === b; }
    else eq = a === b;
    return op === '==' ? eq : !eq;
  }
  if (op === '+' && (typeof a === 'string')) {
    if (b === null || b === undefined) fail('String + null');
    if (b instanceof MF) warn(`String + Float prints 6 decimals: "${a}" + ${b.v}`);
    if (Array.isArray(b)) fail('String + Array');
    return a + (b instanceof MF ? b.v.toFixed(6) : String(b));
  }
  if (typeof b === 'string' && op === '+') fail(`Number + String: ${val(a)} + "${b}"`);
  if (a === null || b === null || a === undefined || b === undefined) fail(`null operand for ${op}: ${a} ${op} ${b}`);
  if (typeof a === 'boolean' || typeof b === 'boolean') fail(`boolean operand for ${op}`);
  if (!isNum(a) || !isNum(b)) fail(`non-number operand for ${op}: ${typeof a} ${typeof b}`);
  const fl = isF(a) || isF(b);
  const x = val(a), y = val(b);
  switch (op) {
    case '+': return fl ? F(x + y) : (x + y) | 0;
    case '-': return fl ? F(x - y) : (x - y) | 0;
    case '*': return fl ? F(x * y) : x * y;
    case '/': if (!fl && y === 0) fail('integer division by zero'); return fl ? F(x / y) : Math.trunc(x / y);
    case '%': if (fl) fail('% on a Float'); if (y === 0) fail('modulo by zero'); return x % y;
    case '<': return x < y;
    case '<=': return x <= y;
    case '>': return x > y;
    case '>=': return x >= y;
    case '>>': case '<<': case '&': case '|':
      if (fl) fail('bit operator on a Float');
      return op === '>>' ? x >> y : op === '<<' ? x << y : op === '&' ? x & y : x | y;
  }
  fail('operator ' + op);
}
function neg(a) { if (!isNum(a)) fail('negate ' + a); return isF(a) ? F(-a.v) : -a; }
function bool(x) {
  if (x === null || x === undefined) return false;
  if (typeof x === 'boolean') return x;
  fail('non-boolean condition: ' + JSON.stringify(x));
}
function idx(a, i) {
  if (a === null || a === undefined) fail('index into null');
  if (typeof i !== 'number' || !Number.isInteger(i)) fail('non-integer index ' + JSON.stringify(i));
  if (!Array.isArray(a)) fail('index into non-array');
  if (i < 0 || i >= a.length) fail(`array index ${i} out of range (size ${a.length})`);
  const v = a[i];
  return v === undefined ? null : v;
}
function set(a, i, v) { idx(a, i); a[i] = v; return v; }
function newArr(n) { return new Array(val(n)).fill(null); }
function inst(x, t) {
  if (t === 'Lang.Number') return typeof x === 'number';
  if (t === 'Lang.Float') return x instanceof MF;
  if (t === 'Lang.Array') return Array.isArray(x);
  if (t === 'Lang.String') return typeof x === 'string';
  fail('instanceof ' + t);
}
function printf(fmt, x) {
  const m = /^%(0?)(\d*)(?:\.(\d+))?([df])$/.exec(fmt);
  if (!m) fail('format ' + fmt);
  if (m[4] === 'd' && x instanceof MF) fail(`Float.format("%d") of ${x.v}: prints garbage on the watch`);
  let s = m[4] === 'd' ? String(Math.trunc(val(x))) : val(x).toFixed(m[3] ? +m[3] : 6);
  const w = m[2] ? +m[2] : 0;
  while (s.length < w) s = (m[1] ? '0' : ' ') + s;
  return s;
}
function m(o, name, args) {
  if (o === null || o === undefined) fail(`.${name}() on null`);
  if (typeof o === 'string') {
    if (name === 'find') { const i = o.indexOf(args[0]); return i < 0 ? null : i; }
    if (name === 'equals') return o === args[0];
    if (name === 'length') return o.length;
    if (name === 'substring') return o.substring(args[0], args[1]);
    if (name === 'toNumber') { const v = parseFloat(o); return isNaN(v) ? null : Math.trunc(v); }
    fail('String.' + name);
  }
  if (isNum(o)) {
    if (name === 'format') return printf(args[0], o);
    if (name === 'toNumber') return Math.trunc(val(o));
    if (name === 'toFloat') return F(val(o));
    if (name === 'abs') return isF(o) ? F(Math.abs(o.v)) : Math.abs(o);
    fail('Number.' + name);
  }
  if (Array.isArray(o)) {
    if (name === 'size') return o.length;
    fail('Array.' + name);
  }
  fail(`.${name}() on ${typeof o}`);
}
let TZ = 'UTC';
function setTZ(z) { TZ = z; }
function newObj(cls, args) {
  if (cls === 'Time.Moment') return { moment: val(args[0]) };
  fail('new ' + cls);
}
function info(mom) {
  const d = new Date(mom.moment * 1000);
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric', hourCycle: 'h23' }).formatToParts(d);
  const g = {};
  for (const p of parts) if (p.type !== 'literal') g[p.type] = parseInt(p.value, 10);
  return { hour: g.hour, min: g.minute, day: g.day, month: g.month, year: g.year };
}
const mod = {
  Math: { PI: F(Math.PI), sqrt: (x) => F(Math.sqrt(val(x))), pow: (a, b) => F(Math.pow(val(a), val(b))), cos: (x) => F(Math.cos(val(x))), sin: (x) => F(Math.sin(val(x))) },
  Time: { FORMAT_SHORT: 0, Moment: null },
  Gregorian: { info: (mom, f) => info(mom) },
  Lang: {}, System: {},
};
// property access on info objects (g.hour) goes through R.m? No: the transpiler only allows module members,
// so Gregorian results are read with getters below.
function prop(o, k) { if (o === null || o === undefined) fail('.' + k + ' of null'); if (!(k in o)) fail('no field ' + k); return o[k]; }
module.exports = { prop, F, MF, bin, neg, bool, idx, set, newArr, inst, m, newObj, mod, setTZ, issues, val };
