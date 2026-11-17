/* Aether Launcher — Super overlay, everything search: apps + files (tracker) + calc + settings. (original) */
import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Shell from 'gi://Shell';

export class AetherLauncher {
  constructor() {
    this.actor = new St.BoxLayout({ style_class: 'aether-launcher' });
    this._query = '';
  }
  enable() {}
  disable() {}
  search(query) {
    this._query = query;
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const results = [];
    // apps via shell
    try {
      const shell = Shell.Global.get_shell();
      const apps = shell.get_all_applications ? shell.get_all_applications() : [];
      for (const app of apps) {
        const name = (app.get_name?.() || '').toLowerCase();
        if (name.includes(q)) results.push({ type: 'app', name: app.get_name?.(), app });
      }
    } catch (e) {}
    // files via tracker (best-effort)
    try {
      const proc = Gio.Subprocess.new(['launcher-search.sh', query], Gio.SubprocessFlags.STDOUT_PIPE);
      // note: async handling omitted in stub; real shell uses search providers
    } catch (e) {}
    // calc — bounded integer parser; no eval (rejects the ** exponentiation bomb).
    const calc = this._safeCalc(q);
    if (calc !== null) results.push({ type: 'calc', name: String(calc) });
    return results.slice(0, 20);
  }

  // Shunting-yard over + - * / ( ) on unsigned integers; rejects anything else.
  _safeCalc(input) {
    if (typeof input !== 'string' || input.length === 0 || input.length > 64) return null;
    if (!/^[0-9+\-*/(). ]+$/.test(input)) return null;
    const out = [];
    const ops = [];
    const prec = { '+': 1, '-': 1, '*': 2, '/': 2 };
    const apply = () => {
      const op = ops.pop();
      const b = out.pop();
      const a = out.pop();
      if (a === undefined || b === undefined) throw new Error('bad expression');
      let v;
      switch (op) {
        case '+': v = a + b; break;
        case '-': v = a - b; break;
        case '*': v = a * b; break;
        case '/': if (b === 0) throw new Error('divide by zero'); v = Math.trunc(a / b); break;
        default: throw new Error('bad operator');
      }
      if (!Number.isSafeInteger(v)) throw new Error('overflow');
      out.push(v);
    };
    try {
      let i = 0;
      while (i < input.length) {
        const c = input[i];
        if (c === ' ') { i++; continue; }
        if (c >= '0' && c <= '9') {
          let n = 0;
          while (i < input.length && input[i] >= '0' && input[i] <= '9') {
            n = n * 10 + (input[i].charCodeAt(0) - 48);
            if (!Number.isSafeInteger(n)) throw new Error('overflow');
            i++;
          }
          out.push(n);
          continue;
        }
        if (c === '(') { ops.push(c); i++; continue; }
        if (c === ')') {
          while (ops.length && ops[ops.length - 1] !== '(') apply();
          if (!ops.length || ops.pop() !== '(') throw new Error('unbalanced');
          i++;
          continue;
        }
        if (Object.prototype.hasOwnProperty.call(prec, c)) {
          while (ops.length && prec[ops[ops.length - 1]] !== undefined &&
                 prec[ops[ops.length - 1]] >= prec[c]) apply();
          ops.push(c); i++;
          continue;
        }
        throw new Error('bad token');
      }
      while (ops.length) {
        if (ops[ops.length - 1] === '(') throw new Error('unbalanced');
        apply();
      }
      if (out.length !== 1) throw new Error('bad expression');
      return out[0];
    } catch (e) {
      return null;
    }
  }
}
