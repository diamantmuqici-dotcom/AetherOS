import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import Gio from 'gi://Gio';
import St from 'gi://St';
import Main from 'resource:///org/gnome/shell/ui/main.js';

const SCHEMA = 'org.aether.animations';
const INTERFACE_SCHEMA = 'org.gnome.desktop.interface';
const WATCHED = [
  'profile',
  'intensity',
  'window-animations',
  'workspace-swipe',
  'lock-fade',
];
const MOTION_CLASSES = [
  'aether-no-window-motion',
  'aether-no-workspace-motion',
  'aether-no-lock-motion',
  'aether-motion-soft',
  'aether-motion-bold',
  'aether-motion-off',
];

export default class AetherAnimations extends Extension {
  enable() {
    this._root = Main.layoutManager.uiGroup;
    this._settings = new Gio.Settings({ schema_id: SCHEMA });
    this._interface = new Gio.Settings({ schema_id: INTERFACE_SCHEMA });
    this._signalIds = WATCHED.map(key =>
      this._settings.connect(`changed::${key}`, () => this._apply()));

    // Activates the .shell-overview stylesheet selector on the real actor.
    try {
      Main.overview.add_style_class_name('shell-overview');
      this._overviewTagged = true;
    } catch (e) {
      this._overviewTagged = false;
    }

    this._apply();
  }

  // Only touch keys the installed schema actually exposes.
  _maybeSetBoolean(schemaId, key, value) {
    let settings;
    try {
      settings = new Gio.Settings({ schema_id: schemaId });
    } catch (e) {
      return;
    }
    try {
      if (!settings.list_keys().includes(key)) return;
      if (settings.get_value(key).get_type_string() === 'b')
        settings.set_boolean(key, value);
    } catch (e) {
      return;
    }
  }

  _apply() {
    const profile = this._settings.get_string('profile');
    const intensity = this._settings.get_double('intensity');
    const windows = this._settings.get_boolean('window-animations');
    const workspace = this._settings.get_boolean('workspace-swipe');
    const lock = this._settings.get_boolean('lock-fade');
    const enabled = profile !== 'off';

    this._interface.set_boolean('enable-animations', enabled);

    try {
      const st = St.Settings.get();
      if (st && 'enable_animations' in st) st.enable_animations = enabled;
    } catch (e) {
      // St setting is read-only or absent on this shell version.
    }

    // Mutter 45-48 exposes no animation key; the guard keeps future ones optional.
    this._maybeSetBoolean('org.gnome.mutter', 'enable-animations', enabled);

    const active = new Set();
    if (!windows) active.add('aether-no-window-motion');
    if (!workspace) active.add('aether-no-workspace-motion');
    if (!lock) active.add('aether-no-lock-motion');

    if (!enabled || intensity <= 0.01) {
      active.add('aether-motion-off');
    } else if (profile === 'reduced' || intensity < 0.75) {
      active.add('aether-motion-soft');
    } else if (intensity > 1.25) {
      active.add('aether-motion-bold');
    }

    for (const cls of MOTION_CLASSES) {
      if (active.has(cls)) this._root.add_style_class_name(cls);
      else this._root.remove_style_class_name(cls);
    }
  }

  disable() {
    for (const id of this._signalIds ?? []) {
      if (id) this._settings?.disconnect(id);
    }
    this._signalIds = [];

    if (this._overviewTagged) {
      try {
        Main.overview.remove_style_class_name('shell-overview');
      } catch (e) {
        // Overview actor already gone.
      }
      this._overviewTagged = false;
    }

    for (const cls of MOTION_CLASSES) {
      try {
        this._root?.remove_style_class_name(cls);
      } catch (e) {
        // Shell is tearing down.
      }
    }

    try {
      St.Settings.get().enable_animations = true;
    } catch (e) {
      // St setting is read-only or absent on this shell version.
    }
    this._interface?.set_boolean('enable-animations', true);

    this._settings = null;
    this._interface = null;
    this._root = null;
  }
}
