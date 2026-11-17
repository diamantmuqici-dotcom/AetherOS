/* Aether Dock — GNOME Shell 45+ bottom taskbar. Local Shell/Gio APIs only. */
import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import * as AppFavorites from 'resource:///org/gnome/shell/ui/appFavorites.js';
import Main from 'resource:///org/gnome/shell/ui/main.js';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import GLib from 'gi://GLib';

const MAX_ICONS = 40;          // hard ceiling; a rebuild never exceeds this many cells
const ICON_SIZE = 40;
const CLOCK_INTERVAL_MS = 30000; // bounded timer, removed in disable()

export class AetherDockExtension extends Extension {
  enable() {
    this._signals = [];       // long-lived: tracker, app system, favorites, layout
    this._cellSignals = [];   // per-icon clicked handlers, cleared on rebuild
    this._timerIds = [];
    this._cells = [];
    this._appCache = new Map(); // app id -> Gio.Icon, avoids repeated get_icon()

    this._appSystem = Shell.AppSystem.get_default();
    this._windowTracker = Shell.WindowTracker.get_default();
    this._favorites = AppFavorites.getAppFavorites();

    this._buildPanel();
    this._wireSignals();
    this._startClock();
    this._rebuild();
  }

  // Track every handler so teardown can disconnect it; never rely on GC.
  _connect(obj, signal, callback) {
    if (!obj) return;
    try {
      const id = obj.connect(signal, callback);
      this._signals.push([obj, id]);
    } catch (e) {
      // Signal absent on this shell version.
    }
  }

  _connectCell(obj, signal, callback) {
    if (!obj) return;
    try {
      const id = obj.connect(signal, callback);
      this._cellSignals.push([obj, id]);
    } catch (e) {
      // Button already torn down.
    }
  }

  _buildPanel() {
    this._panel = new St.BoxLayout({
      style_class: 'aether-dock',
      vertical: false,
      x_expand: false,
      y_expand: false,
    });

    this._showApps = new St.Button({
      style_class: 'aether-dock-showapps',
      child: new St.Icon({
        style_class: 'aether-dock-icon',
        icon_name: 'view-app-grid-symbolic',
        icon_size: ICON_SIZE,
      }),
    });
    this._connectCell(this._showApps, 'clicked', () => this._showOverview());

    this._iconStrip = new St.BoxLayout({
      style_class: 'aether-dock-icons',
      x_expand: false,
      y_expand: false,
    });

    this._clock = new St.Label({
      style_class: 'aether-dock-clock',
      text: '',
      y_align: Clutter.ActorAlign.CENTER,
    });

    this._panel.add_child(this._showApps);
    this._panel.add_child(this._iconStrip);
    this._panel.add_child(this._clock);

    Main.layoutManager.addChrome(this._panel, {
      affectsInputRegion: true,
      trackFullscreen: true,
    });
    this._positionPanel();
  }

  _positionPanel() {
    if (!this._panel) return;
    try {
      const lm = Main.layoutManager;
      const x = Math.round(lm.bottomCenter - this._panel.width / 2);
      const y = Math.round(lm.screenHeight - this._panel.height);
      this._panel.set_position(x, Math.max(0, y));
    } catch (e) {
      // Layout manager not ready yet; the 'changed' signal repositions later.
    }
  }

  _showOverview() {
    try {
      Main.overview.toggle();
    } catch (e) {
      // Overview already closing.
    }
  }

  _workspaceManager() {
    try {
      return global.get_workspace_manager?.() ?? global.workspace_manager ?? null;
    } catch (e) {
      return null;
    }
  }

  _wireSignals() {
    this._connect(this._windowTracker, 'tracked-windows-changed', () => this._rebuild());
    this._connect(this._windowTracker, 'notify::focus-app', () => this._updateIndicators());
    this._connect(this._appSystem, 'installed-changed', () => this._rebuild());
    this._connect(this._favorites, 'changed', () => this._rebuild());

    const wm = this._workspaceManager();
    this._connect(wm, 'window-added', () => this._rebuild());
    this._connect(wm, 'window-removed', () => this._rebuild());
    this._connect(Main.layoutManager, 'changed', () => this._positionPanel());
  }

  _collectApps() {
    const out = [];
    const seen = new Set();

    const add = app => {
      if (!app || out.length >= MAX_ICONS) return;
      let id;
      try {
        id = app.get_id();
      } catch (e) {
        return;
      }
      if (!id || seen.has(id)) return;
      seen.add(id);
      out.push(app);
    };

    // Favorites first, then running apps that are not already pinned.
    let favorites = [];
    let running = [];
    try {
      favorites = this._favorites?.getFavorites() ?? [];
    } catch (e) {
      favorites = [];
    }
    try {
      running = this._appSystem?.get_running() ?? [];
    } catch (e) {
      running = [];
    }

    for (const id of favorites) {
      try {
        add(this._appSystem?.lookup_app(id));
      } catch (e) {
        // Stale favorite id; skip it.
      }
    }
    for (const app of running) add(app);
    return out;
  }

  _iconFor(app) {
    let id = null;
    let gicon = null;
    try {
      id = app.get_id();
    } catch (e) {
      return null;
    }
    if (id) gicon = this._appCache.get(id);
    if (!gicon) {
      try {
        gicon = app.get_icon();
      } catch (e) {
        gicon = null;
      }
      if (id && gicon) this._appCache.set(id, gicon);
    }
    return gicon;
  }

  _makeCell(app) {
    const cell = new St.BoxLayout({
      style_class: 'aether-dock-cell',
      vertical: true,
      x_expand: false,
      y_expand: false,
    });

    const button = new St.Button({
      style_class: 'aether-dock-button',
      child: new St.Icon({
        style_class: 'aether-dock-icon',
        gicon: this._iconFor(app),
        icon_size: ICON_SIZE,
      }),
    });
    this._connectCell(button, 'clicked', () => this._activate(app));

    const dot = new St.Bin({ style_class: 'aether-dock-indicator' });
    cell.add_child(button);
    cell.add_child(dot);
    this._cells.push({ app, dot });
    return cell;
  }

  _clearCellSignals() {
    for (const [obj, id] of this._cellSignals) {
      try {
        if (obj && id) obj.disconnect(id);
      } catch (e) {
        // Actor already destroyed.
      }
    }
    this._cellSignals = [];
  }

  _rebuild() {
    if (!this._iconStrip) return;

    this._clearCellSignals();
    for (const child of this._iconStrip.get_children()) {
      try {
        child.destroy();
      } catch (e) {
        // Child already gone.
      }
    }
    this._cells = [];

    for (const app of this._collectApps()) {
      try {
        this._iconStrip.add_child(this._makeCell(app));
      } catch (e) {
        // Bad app metadata; skip this icon.
      }
    }
    this._updateIndicators();
    this._positionPanel();
  }

  _activate(app) {
    if (!app) return;
    try {
      const windows = (app.get_windows() ?? []).filter(
        w => w instanceof Meta.Window && !w.is_closing?.()
      );
      if (windows.length > 0) {
        windows[0].activate(global.get_current_time());
      } else {
        app.activate();
      }
    } catch (e) {
      try {
        app.activate();
      } catch (e2) {
        // App vanished between render and click.
      }
    }
  }

  _updateIndicators() {
    let focusId = null;
    try {
      focusId = this._windowTracker?.focus_app?.get_id() ?? null;
    } catch (e) {
      focusId = null;
    }

    for (const { app, dot } of this._cells) {
      if (!dot) continue;
      let id = null;
      try {
        id = app.get_id();
      } catch (e) {
        // Ignore stale app.
      }
      try {
        if (id && id === focusId) dot.add_style_class_name('active');
        else dot.remove_style_class_name('active');
      } catch (e) {
        // Dot actor already gone.
      }
    }
  }

  _startClock() {
    this._updateClock();
    const id = GLib.timeout_add(GLib.PRIORITY_DEFAULT, CLOCK_INTERVAL_MS, () => {
      this._updateClock();
      return GLib.SOURCE_CONTINUE;
    });
    if (id) this._timerIds.push(id);
  }

  _updateClock() {
    if (!this._clock) return;
    try {
      const now = GLib.DateTime.new_now_local();
      this._clock.set_text(`${now.format('%a')} ${now.format('%H:%M')}`);
    } catch (e) {
      // Clock label already disposed.
    }
  }

  disable() {
    // Timers first, then handlers, then actors; order prevents stale callbacks.
    for (const id of this._timerIds) {
      if (id) {
        try {
          GLib.source_remove(id);
        } catch (e) {
          // Source already removed.
        }
      }
    }
    this._timerIds = [];

    for (const [obj, id] of this._signals) {
      try {
        if (obj && id) obj.disconnect(id);
      } catch (e) {
        // Object already finalized.
      }
    }
    this._signals = [];
    this._clearCellSignals();

    if (this._panel) {
      try {
        Main.layoutManager.removeChrome(this._panel);
      } catch (e) {
        // Shell is tearing down.
      }
      try {
        this._panel.remove_all_children();
        this._panel.destroy();
      } catch (e) {
        // Panel actor already gone.
      }
    }

    this._panel = null;
    this._showApps = null;
    this._iconStrip = null;
    this._clock = null;
    this._cells = [];
    this._appCache?.clear?.();
    this._appCache = null;
    this._appSystem = null;
    this._windowTracker = null;
    this._favorites = null;
  }
}

export default AetherDockExtension;
