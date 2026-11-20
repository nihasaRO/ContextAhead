// Transpiles the Context class (Context.mc) and the Ic module into JavaScript that runs on a strict runtime
// (rt.cjs) mimicking Monkey C: integer vs float arithmetic, crashes on null arithmetic, out-of-range array
// access, String + Number, Float.format("%d"). Used only to test the engine's logic and crash-safety.
const p = require('@markw65/prettier-plugin-monkeyc');
const fs = require('fs');

function parse(f) { return p.parsers.monkeyc.parse(fs.readFileSync(f, 'utf8'), {}); }

function transpile(ctxFile, icFile) {
  const ic = parse(icFile);
  const icConsts = {};
  for (const st of ic.body) if (st.type === 'ModuleDeclaration') for (const el of st.body.body) {
    const it = el.item || el;
    if (it.type === 'VariableDeclaration') for (const d of it.declarations) icConsts[d.id.name] = d.init;
  }
  const ast = parse(ctxFile);
  const cls = ast.body.find(s => s.type === 'ClassDeclaration');
  const consts = {}, vars = {}, fns = {};
  for (const el of cls.body.body) {
    const it = el.item || el;
    if (it.type === 'VariableDeclaration') for (const d of it.declarations) (it.kind === 'const' ? consts : vars)[d.id.name] = d.init;
    if (it.type === 'FunctionDeclaration') fns[it.id.name] = it;
  }
  let locals = new Set();
  const E = (n) => {
    switch (n.type) {
      case 'Literal':
        if (n.value === null) return 'null';
        if (typeof n.value === 'number') return /[.eE]/.test(n.raw) && !/^0x/i.test(n.raw) ? `R.F(${n.value})` : String(n.value);
        return JSON.stringify(n.value);
      case 'Identifier':
        if (locals.has(n.name)) return 'l_' + n.name;
        if (n.name in consts) return 'C_' + n.name;
        if (n.name in vars) return 'this.' + n.name;
        if (n.name in fns) return 'this.' + n.name + '.bind(this)';
        if (n.name === 'true' || n.name === 'false' || n.name === 'null') return n.name;
        throw new Error('unknown identifier ' + n.name);
      case 'MemberExpression': {
        if (n.computed) return `R.idx(${E(n.object)}, ${E(n.property)})`;
        const o = n.object.type === 'Identifier' ? n.object.name : null;
        if (o === 'Ic') return 'IC.' + n.property.name;
        if (o === 'Math' || o === 'Time' || o === 'Gregorian' || o === 'Lang' || o === 'System') return `R.mod.${o}.${n.property.name}`;
        if (n.object.type === 'MemberExpression' && src(n.object) === 'Time.Gregorian') return `R.mod.Gregorian.${n.property.name}`;
        return `R.prop(${E(n.object)}, ${JSON.stringify(n.property.name)})`;
      }
      case 'CallExpression': {
        const a = n.arguments.map(E).join(', ');
        if (n.callee.type === 'Identifier') {
          if (!(n.callee.name in fns)) throw new Error('unknown call ' + n.callee.name);
          const f = fns[n.callee.name];
          if (f.params.length !== n.arguments.length) throw new Error(`arity ${n.callee.name}`);
          return `this.${n.callee.name}(${a})`;
        }
        if (n.callee.type === 'MemberExpression' && !n.callee.computed) {
          const o = n.callee.object.type === 'Identifier' ? n.callee.object.name : null;
          if (['Math', 'Gregorian', 'System'].includes(o)) return `R.mod.${o}.${n.callee.property.name}(${a})`;
          return `R.m(${E(n.callee.object)}, ${JSON.stringify(n.callee.property.name)}, [${a}])`;
        }
        throw new Error('call ' + n.callee.type);
      }
      case 'NewExpression': return `R.newObj(${JSON.stringify(src(n.callee))}, [${n.arguments.map(E).join(', ')}])`;
      case 'BinaryExpression':
        if (n.operator === 'instanceof') return `R.inst(${E(n.left)}, ${JSON.stringify(src(n.right))})`;
        return `R.bin(${JSON.stringify(n.operator)}, ${E(n.left)}, ${E(n.right)})`;
      case 'LogicalExpression': return `(R.bool(${E(n.left)}) ${n.operator} R.bool(${E(n.right)}))`;
      case 'UnaryExpression':
        if (n.operator === '!') return `(!R.bool(${E(n.argument)}))`;
        if (n.operator === '-') return `R.neg(${E(n.argument)})`;
        throw new Error('unary ' + n.operator);
      case 'ConditionalExpression': return `(R.bool(${E(n.test)}) ? ${E(n.consequent)} : ${E(n.alternate)})`;
      case 'ArrayExpression': return `[${n.elements.map(E).join(', ')}]`;
      case 'SizedArrayExpression': return `R.newArr(${E(n.size)})`;
      case 'AssignmentExpression': {
        const op = n.operator;
        const rhs = op === '=' ? E(n.right) : `R.bin(${JSON.stringify(op[0])}, ${E(n.left)}, ${E(n.right)})`;
        if (n.left.type === 'MemberExpression' && n.left.computed) return `R.set(${E(n.left.object)}, ${E(n.left.property)}, ${rhs})`;
        return `(${E(n.left)} = ${rhs})`;
      }
      default: throw new Error('expr ' + n.type);
    }
  };
  const S = (n, ind) => {
    const pad = '  '.repeat(ind);
    switch (n.type) {
      case 'BlockStatement': return n.body.map(s => S(s, ind)).join('\n');
      case 'ExpressionStatement': return pad + E(n.expression) + ';';
      case 'VariableDeclaration': return n.declarations.map(d => { locals.add(d.id.name); return `${pad}let l_${d.id.name} = ${d.init ? E(d.init) : 'null'};`; }).join('\n');
      case 'ReturnStatement': return pad + 'return' + (n.argument ? ' ' + E(n.argument) : '') + ';';
      case 'BreakStatement': return pad + 'break;';
      case 'ContinueStatement': return pad + 'continue;';
      case 'IfStatement': return `${pad}if (R.bool(${E(n.test)})) {\n${S(n.consequent, ind + 1)}\n${pad}}` + (n.alternate ? ` else {\n${S(n.alternate, ind + 1)}\n${pad}}` : '');
      case 'ForStatement': {
        const init = n.init ? S(n.init, 0).trim().replace(/;$/, '') : '';
        return `${pad}for (${init}; R.bool(${E(n.test)}); ${E(n.update)}) {\n${S(n.body, ind + 1)}\n${pad}}`;
      }
      case 'WhileStatement': return `${pad}while (R.bool(${E(n.test)})) {\n${S(n.body, ind + 1)}\n${pad}}`;
      default: throw new Error('stmt ' + n.type);
    }
  };
  let out = [];
  out.push('const IC = {' + Object.entries(icConsts).map(([k, v]) => `${k}: ${v.type === 'ArrayExpression' ? '[' + v.elements.map(e => e.value).join(',') + ']' : v.value}`).join(', ') + '};');
  locals = new Set();
  for (const [k, v] of Object.entries(consts)) out.push(`const C_${k} = ${E(v)};`);
  out.push('class Context {');
  out.push('  constructor() {');
  for (const [k, v] of Object.entries(vars)) out.push(`    this.${k} = ${v ? E(v) : 'null'};`);
  out.push('    if (this.init) this.init();');
  out.push('  }');
  for (const [name, f] of Object.entries(fns)) {
    if (name === 'initialize') { out.push('  init() {'); locals = new Set(); out.push(S(f.body, 2)); out.push('  }'); continue; }
    locals = new Set(f.params.map(x => x.name));
    out.push(`  ${name}(${f.params.map(x => 'l_' + x.name).join(', ')}) {`);
    out.push(S(f.body, 2));
    out.push('  }');
  }
  out.push('}');
  out.push('module.exports = { Context, IC };');
  return out.join('\n');
}
function src(n) { if (n.type === 'Identifier') return n.name; if (n.type === 'MemberExpression') return src(n.object) + '.' + src(n.property); return n.type; }

const [ctxFile, icFile, outFile] = process.argv.slice(2);
fs.writeFileSync(outFile, "const R = require('./rt.cjs');\n" + transpile(ctxFile, icFile));
console.log('transpiled to', outFile);
