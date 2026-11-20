// Prints the engine's full result for chosen raises (for the store images): node extract.cjs 14 04 15.1 ...
const R = require('./rt.cjs');
const { Context, IC } = require('./ctx.cjs');
const { pack } = require('./pack.cjs');
const cases = require('./cases.json');
const F = R.F;
const names = Object.fromEntries(Object.entries(IC).filter(([k, v]) => typeof v === 'number').map(([k, v]) => [v, k]));
const want = process.argv.slice(2);
const out = {};
for (const c of cases) {
  const ctx = new Context();
  c.raises.forEach((r, k) => {
    const id = c.raises.length > 1 ? `${c.num}.${k + 1}` : c.num;
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
    ctx.tempF = false; ctx.distMi = false; ctx.elevFt = false; ctx.t24 = true; ctx.pollenOn = x.pollenOn;
    ctx.errText = x.errText;
    if (!x.todaySeenOff) ctx.todaySeen = ctx.dayKey(x.now); else ctx.todaySeen = -1;
    const m = ctx.pick();
    if (want.includes(id)) {
      const d = new Date((x.now + 0) * 1000);
      out[id] = { icon: names[m[0]] || null, word: m[1], detail: m[2], l1: m[3], l2: m[4], e1: m[5], e2: m[6], inv: m[7],
        tier: R.val(m[8]), localMin: x.localMin, wAge: x.wAge, tz: x.tz,
        date: new Intl.DateTimeFormat('en-GB', { timeZone: x.tz, weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(d) };
    }
  });
}
console.log(JSON.stringify(out, null, 1));
