const p = require('@markw65/prettier-plugin-monkeyc');
const fs = require('fs');
for (const f of process.argv.slice(2)) {
  try { p.parsers.monkeyc.parse(fs.readFileSync(f,'utf8'), {}); console.log('ok', f.split('/').pop()); }
  catch (e) { console.log('FAIL', f.split('/').pop(), e.message, JSON.stringify(e.location && e.location.start)); }
}
