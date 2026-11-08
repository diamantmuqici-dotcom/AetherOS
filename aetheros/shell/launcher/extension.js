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
    // calc
    try {
      if (/^[0-9+\-*/(). ]+$/.test(q)) results.push({ type: 'calc', name: String(eval(q)) });
    } catch (e) {}
    return results.slice(0, 20);
  }
}
