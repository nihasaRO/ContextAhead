// A small semantic lint for Monkey C (no SDK needed): duplicate locals, undefined names, unknown members
// of the project's own modules and classes, private members used from outside.
const p = require('@markw65/prettier-plugin-monkeyc');
const fs = require('fs');
const files = process.argv.slice(2);
const asts = files.map(f => [f, p.parsers.monkeyc.parse(fs.readFileSync(f, 'utf8'), {})]);
const containers = {};   // name -> {kind, members: {name: {kind, priv}}, sup}
function access(attrs) { return attrs && attrs.access ? attrs.access : null; }
for (const [f, ast] of asts) {
  for (const st of ast.body) {
    const d = st.type === 'ClassDeclaration' || st.type === 'ModuleDeclaration' ? st : null;
    if (!d) continue;
    const c = containers[d.id.name] = { kind: st.type, members: {}, sup: d.superClass ? src(d.superClass) : null, file: f };
    for (const el of d.body.body) {
      const it = el.item || el;
      if (it.type === 'FunctionDeclaration') c.members[it.id.name] = { kind: 'fn', priv: (access(it.attrs) || '').includes('private'), params: it.params.length };
      if (it.type === 'VariableDeclaration') for (const v of it.declarations) c.members[v.id.name || (v.id.left && v.id.left.name)] = { kind: it.kind, priv: (access(it.attrs) || '').includes('private') };
    }
  }
}
function src(n) { if (!n) return ''; if (n.type === 'Identifier') return n.name; if (n.type === 'MemberExpression') return src(n.object) + '.' + src(n.property); return n.type; }
const GLOBALS = new Set(['AppBase','WatchFace','View','BehaviorDelegate','ServiceDelegate','method','Toybox','Lang','Math','System','Time','Gregorian','Application','Background','Communications','Graphics','WatchUi','Activity','ActivityMonitor','Position','SensorHistory','Weather','PersistedContent','Dc','Rez','self','me','null','true','false','NaN']);
const INHERITED = new Set(['addItem','setFocus','initialize','getId','setSubLabel']);
let problems = 0;
function report(f, n, msg) { problems++; console.log(`${f.split('/').pop()}:${n.loc ? n.loc.start.line : '?'}: ${msg}`); }
const instanceOf = {};   // container -> member var -> class name (from "x = new C()")
for (const [f, ast] of asts) {
  for (const st of ast.body) {
    if (!containers[st.id && st.id.name]) continue;
    const cname = st.id.name; const C = containers[cname]; instanceOf[cname] = {};
    walk(st, n => { if (n.type === 'AssignmentExpression' && n.left.type === 'Identifier' && n.right.type === 'NewExpression') instanceOf[cname][n.left.name] = src(n.right.callee); });
  }
}
function walk(n, fn) { if (!n || typeof n !== 'object') return; if (Array.isArray(n)) { n.forEach(m => walk(m, fn)); return; } if (n.type) fn(n); for (const k of Object.keys(n)) if (k !== 'loc' && k !== 'start' && k !== 'end') walk(n[k], fn); }
for (const [f, ast] of asts) {
  for (const st of ast.body) {
    const cname = st.id && st.id.name; const C = containers[cname]; if (!C) continue;
    for (const el of st.body.body) {
      const fd = el.item || el; if (fd.type !== 'FunctionDeclaration' || !fd.body) continue;
      const locals = new Set(fd.params.map(x => x.name || (x.left && x.left.name) || src(x)));
      const seen = {};
      walk(fd.body, n => { if (n.type === 'VariableDeclarator') { const nm = n.id.name; if (seen[nm]) report(f, n, `duplicate local '${nm}' in ${cname}.${fd.id.name}`); seen[nm] = 1; locals.add(nm); } });
      // references
      const skip = new WeakSet();
      walk(fd.body, n => {
        if (n.type === 'MemberExpression') {
          if (!n.computed) skip.add(n.property);
          const on = n.object.type === 'Identifier' ? n.object.name : null; const prop = n.property.name;
          if (on && !n.computed && containers[on] && containers[on].kind === 'ModuleDeclaration' && !containers[on].members[prop]) report(f, n, `${on}.${prop} not defined`);
          if (on && !n.computed && instanceOf[cname][on]) { const K = containers[instanceOf[cname][on]]; if (K) { const m = K.members[prop]; if (!m) report(f, n, `${on}.${prop}: no such member in ${instanceOf[cname][on]}`); else if (m.priv) report(f, n, `${on}.${prop} is private in ${instanceOf[cname][on]}`); } }
        }
        if (n.type === 'Property' || n.type === 'ObjectProperty') skip.add(n.key);
        if (n.type === 'UnaryExpression' && n.operator === ':') skip.add(n.argument);
        if (n.type === 'Identifier' && !skip.has(n)) {
          const nm = n.name;
          if (locals.has(nm) || C.members[nm] || GLOBALS.has(nm) || containers[nm] || INHERITED.has(nm)) return;
          report(f, n, `unknown name '${nm}' in ${cname}.${fd.id.name}`);
        }
        if (n.type === 'CallExpression' && n.callee.type === 'Identifier') {
          const m = C.members[n.callee.name];
          if (m && m.kind === 'fn' && m.params !== n.arguments.length) report(f, n, `${n.callee.name} called with ${n.arguments.length} args, takes ${m.params}`);
        }
      });
    }
  }
}
console.log(problems ? `${problems} problem(s)` : 'lint: no problems');
