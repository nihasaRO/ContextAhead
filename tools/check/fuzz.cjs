// Random weather, missing fields, odd units and clocks: the engine must never crash.
const R = require('./rt.cjs');
const { Context } = require('./ctx.cjs');
const F = R.F;
const { pack } = require('./pack.cjs');
const { dups } = require('./dups.cjs');
let dupN = 0; const dupEx = {};
let seed = 12345;
const rnd = () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; };
const ri = (a, b) => a + Math.floor(rnd() * (b - a + 1));
const pick = (a) => a[ri(0, a.length - 1)];
let crashes = 0, runs = 0;
const SNAPS = [];
const seen = {};
const TX = [new Set(), new Set(), new Set(), new Set(), new Set(), new Set(), new Set()];
const zones = ['Europe/Bucharest', 'America/Denver', 'Europe/Berlin', 'Asia/Kolkata', 'Australia/Darwin', 'Europe/Helsinki'];
for (let k = 0; k < 20000; k++) {
  R.setTZ(pick(zones));
  const ctx = new Context();
  for (let r = 0; r < 4; r++) {
    const now = 1780000000 + ri(0, 3e7);
    const n = pick([0, 1, 16, 24, 24, 24]);
    const t0 = Math.floor(now / 3600) * 3600 - pick([0, 0, 0, 3600, 7200]);
    const ser = (lo, hi, nullp) => rnd() < 0.05 ? null : Array.from({ length: n }, () => rnd() < nullp ? -9999 : ri(lo, hi));
    let w = null;
    if (rnd() < 0.85) {
      w = [now - ri(0, 900) * 60, F(ri(-60, 70) + rnd()), F(ri(-130, 40) + rnd()), rnd() < 0.03 ? null : t0, n,
        ser(-400, 450, 0.02), ser(5, 100, 0.02), Array.from({ length: n }, () => pick([0, 1, 2, 3, 45, 48, 51, 56, 61, 63, 65, 66, 67, 71, 73, 75, 80, 85, 86, 95, 96, 97, 99])),
        ser(0, 100, 0.1), ser(0, 120, 0.02), ser(0, 40, 0.02), ser(0, 90, 0.02), ser(0, 359, 0.02), ser(0, 140, 0.02),
        ser(0, 5000, 0.2), ser(0, 120, 0.05), ser(0, 100, 0.02), ser(0, 4000, 0.5), ser(0, 60, 0.05),
        rnd() < 0.5 ? now - now % 900 + 900 : null, rnd() < 0.5 ? Array.from({ length: 8 }, () => pick([0, 0, 1, 3, 9, -9999])) : null,
        rnd() < 0.1 ? null : [ri(-300, 450), ri(-400, 300), ri(0, 120), ri(0, 900), pick([-9999, 200]), pick([-9999, 50]), pick([-9999, 70]),
          pick([null, now - 5000, now + 5000]), pick([null, now - 2000, now + 9000]), pick([-9999, 50, 99]), pick([null, now + 80000]), pick([null, now + 90000]),
          pick([-9999, 0, 150]), pick([-9999, 0, 30, 120])],
        rnd() < 0.5 ? null : [now - ri(0, 20000), ri(0, 1), pick([-9999, 10, 70, 120, 320]), ri(0, 4), pick([-9999, 0, 150]), pick([null, 0, 3, 4]), ri(0, 5),
          pick([null, 0, 48, 160]), pick([null, 0, 540]), pick([null, now - 3000, now + 600]), rnd() < 0.3 ? null : Array.from({ length: pick([0, 6, 12]) }, () => pick([null, 1023, 40, 90, 130, 330]) === null ? null : pick([1023, 40, 90, 130, 330]) + 1024 * pick([0, 60, 150]))],
        null];
    }
    ctx.now = now;
    ctx.localMin = ri(0, 1439);
    const pk = pack(w); ctx.w = pk.w; ctx.aq = pk.aq; ctx.wAge = w ? Math.floor((now - w[0]) / 60) : 9999;
    ctx.q15 = rnd() < 0.5; ctx.far = rnd() < 0.2;
    const hasSun = rnd() < 0.85;
    ctx.riseM = hasSun ? ri(200, 600) : -1; ctx.setM = hasSun ? ri(900, 1300) : -1;
    ctx.dawnM = hasSun ? ctx.riseM - 30 : -1; ctx.duskM = hasSun ? ctx.setM + 30 : -1;
    ctx.polar = hasSun ? 0 : pick([0, 1, -1]);
    ctx.baroDrop = rnd() < 0.5 ? null : F(ri(-80, 80) / 10); ctx.baroStill = rnd() < 0.5; ctx.baroNow = rnd() < 0.3 ? null : F(ri(950, 1040));
    ctx.alt = rnd() < 0.3 ? null : F(ri(-10, 4000));
    ctx.tempF = rnd() < 0.5; ctx.distMi = rnd() < 0.5; ctx.elevFt = rnd() < 0.5; ctx.t24 = rnd() < 0.5;
    ctx.pollenOn = rnd() < 0.5; ctx.errText = 'NO PHONE';
    ctx.yday = rnd() < 0.5 ? null : [0, pick([-9999, -150, 80, 300, 420]), pick([0, 50, 120, 380, 1250]), pick([null, 0, 40, 150])];
    ctx.wetT = pick([0, 0, now - 4000, now - 20000, now - 1000]);
    if (w && w[5] && rnd() < 0.3) for (let i = 0; i < n; i++) if (pk.w && pk.w[7]) pk.w[7][i] |= (1 << 30);
    runs++;
    try {
      const m = ctx.pick();
      if (process.env.SNAP) SNAPS.push(m.map(String).join('|'));
      for (const i of [1, 2, 3, 4, 5, 6]) if (typeof m[i] !== 'string') throw new Error('MONKEYC CRASH: non-string text ' + i + ' ' + m[i]);
      seen[m[1]] = (seen[m[1]] || 0) + 1;
      for (const i of [1, 2, 3, 4, 5, 6]) TX[i].add(m[i]);
      const d = dups(m[1], m[2], m[3], m[4], m[5]); if (d.length) { dupN++; dupEx[m[1] + ' ' + d.join(',')] = m.slice(1, 6).join(' | '); }
    } catch (e) {
      crashes++;
      if (crashes <= 8) console.log(e.message.split('\n')[0], '\n   ', (e.stack.split('\n').find(l => l.includes('ctx.cjs')) || '').trim());
    }
  }
}
console.log(`${runs} runs, ${crashes} crashes, ${dupN} screens repeat a value`);
console.log('repeat examples:', JSON.stringify(Object.entries(dupEx).slice(0, 25), null, 1));
console.log('signals seen:', JSON.stringify(seen));
console.log('warnings:', [...new Set(R.issues)].slice(0, 10));
if (process.env.SNAP) require('fs').writeFileSync(process.env.SNAP, SNAPS.join('\n'));
require('fs').writeFileSync('fuzz_texts.json', JSON.stringify(TX.map(t => [...t])));
