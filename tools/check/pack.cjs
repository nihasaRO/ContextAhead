// The watch's packing (WeatherService.mc pack4): turns the simulation's 24-slot weather array (14 separate hourly
// series, air quality at 22) into the 13-slot array the face stores, so the tests run on the real layout.
const SLOT = [0, 0, 0, 1, 2, 2, 1, 3, 1, 3, 2, 1, 3, 0];
const SHIFT = [0, 11, 18, 0, 0, 12, 7, 0, 15, 8, 22, 24, 19, 25];
const BITS = [11, 7, 7, 7, 12, 10, 8, 8, 9, 11, 8, 7, 12, 6];
const OFF = [1000, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 100, 0];
const UNIT = [1, 1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 10, 1];
// Monkey C integer division truncates; the watch rounds half away from zero before dividing: (v + u/2) / u
function store(v, f) {
  const m = (1 << BITS[f]) - 1;
  if (v == null || v <= -9999) return m;
  const u = UNIT[f];
  let x = Math.trunc((v >= 0 ? v + Math.trunc(u / 2) : v - Math.trunc(u / 2)) / u) + OFF[f];
  return x < 0 ? 0 : (x >= m ? m - 1 : x);
}
function pack(old) {
  if (!old) return { w: null, aq: null };
  const n = old[4] || 0;
  const w = [old[0], old[1], old[2], old[3], old[4], null, null, null, null, old[19], old[20], old[21], null];
  for (let s = 0; s < 4; s++) {
    let any = false;
    for (let f = 0; f < 14; f++) if (SLOT[f] === s && old[5 + f]) any = true;
    if (!any) continue;
    const a = new Array(n).fill(0);
    for (let f = 0; f < 14; f++) {
      if (SLOT[f] !== s) continue;
      const src = old[5 + f];
      for (let i = 0; i < n; i++) a[i] |= store(src && i < src.length ? src[i] : null, f) << SHIFT[f];
    }
    w[5 + s] = a;
  }
  // air: the simulation's 7 fields, padded to the face's 11 (concentration, grains, hourly forecast)
  let aq = old[22] || null;
  if (aq && aq.length < 11) aq = aq.concat(new Array(11 - aq.length).fill(null));
  return { w, aq };
}
module.exports = { pack };
