const R = require('./rt.cjs');
const { Context } = require('./ctx.cjs');
const cases = require('./cases.json');
const F = R.F;
const { pack } = require('./pack.cjs');
const { dups } = require('./dups.cjs');
let dupN = 0;
let crashes = 0, same = 0, diff = 0;
const rows = []; const ALL = [];
for (const c of cases) {
  const ctx = new Context();
  c.raises.forEach((r, k) => {
    const x = r.inputs;
    R.setTZ(x.tz);
    ctx.now = x.now; ctx.localMin = x.localMin;
    let w = x.w;
    if (w) { w = JSON.parse(JSON.stringify(w)); w[1] = F(w[1]); w[2] = F(w[2]); }
    const pk = pack(w); ctx.w = pk.w; ctx.aq = pk.aq; ctx.wAge = x.wAge; ctx.q15 = x.q15; ctx.far = x.far;
    ctx.riseM = x.riseM; ctx.setM = x.setM; ctx.dawnM = x.dawnM; ctx.duskM = x.duskM; ctx.polar = x.polar;
    ctx.baroDrop = x.baroDrop == null ? null : F(x.baroDrop); ctx.baroStill = x.baroStill;
    ctx.baroNow = x.baroNow == null ? null : F(x.baroNow);
    ctx.alt = x.alt == null ? null : F(x.alt);
    const imp = !!process.env.IMP; ctx.tempF = imp; ctx.distMi = imp; ctx.elevFt = imp; ctx.t24 = !imp; ctx.pollenOn = x.pollenOn;
    ctx.errText = x.errText;
    if (!x.todaySeenOff) ctx.todaySeen = ctx.dayKey(x.now); else ctx.todaySeen = -1;
    let out;
    try { const m = ctx.pick(); out = [m[1], m[2], m[3], m[4], m[8], m[5], m[6]]; ALL.push(out);
      const d = dups(m[1], m[2], m[3], m[4], m[5]); if (d.length) { dupN++; console.log('DUPLICATE', c.num, d.join(','), '|', m.slice(1, 6).join(' | ')); } }
    catch (e) { crashes++; out = ['CRASH', e.message]; }
    const py = r.py;
    // the watch shows an hourly onset by its hour's end ("BY 16:00") and offline sun times with SETS/RISES; the sim uses
    // the older forms ("~15:00", "20:25"), so compare them as the same signal
    const norm = (d) => String(d).replace(/^BY (\d\d?):(\d\d)$/, (m, h, mi) => '~' + String((+h + 23) % 24).padStart(h.length, '0') + ':' + mi)
      .replace(/^(SETS|RISES) /, '');
    const eq = out[0] === py[0] && norm(out[1]) === py[1];
    if (eq) same++; else diff++;
    rows.push(`${eq ? '  ' : '!!'} ${c.num}${c.raises.length > 1 ? '.' + (k + 1) : ''}  WATCH ${out.slice(0, 4).join(' | ')} [T${out[4]}]\n${' '.repeat(c.num.length + 4)}  SIM   ${py.slice(0, 4).join(' | ')} [T${py[4]}]`);
  });
}
console.log(rows.join('\n'));
if (process.env.SNAP) require('fs').writeFileSync(process.env.SNAP, JSON.stringify(ALL));
console.log(`\n${same} same signal, ${diff} different, ${crashes} crashes, ${dupN} screens repeat a value`);
console.log('runtime warnings:', [...new Set(R.issues)].slice(0, 20));
require('fs').writeFileSync(process.env.IMP ? 'texts_imp.json' : 'texts.json', JSON.stringify(ALL));
