// One number or time per screen: the Signal, line 1 and line 2 at rest, plus the extra line on a wrist raise, must
// not show the same value twice ("~15:00" and "15:00" count as the same). Units tell values apart: "1 H" and "-1°"
// are different values.
const tok = (s) => new Set((String(s || '').match(/-?\d+(?::\d\d)?(?:\.\d+)?\s?(?:°|%|KMH|MPH|MM|CM|IN|KM|MI|M|FT|H)?/g) || []).map(t => t.replace(/\s/g, '')));
function dups(word, detail, l1, l2, extra) {
  const parts = [word, detail, l1, l2, extra].map(tok);
  const out = [];
  for (let a = 0; a < parts.length; a++) for (let b = a + 1; b < parts.length; b++)
    for (const t of parts[a]) if (parts[b].has(t)) out.push(t);
  return out;
}
module.exports = { dups };
