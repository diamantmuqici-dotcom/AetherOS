/* Aether Shell — dock, launcher, topbar, notifications (Wayland, original). */
import { Extension } from 'resource:///org/gnome/shell/extensions/prefs.js';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

const aether = {};

export default class AetherShell extends Extension {
  enable() {
    this._top = new St.BoxLayout({ name: 'aether-topbar', x_expand: true });
    const label = new St.Label({ text: 'AetherOS', style_class: 'aether-top-label' });
    this._top.add_child(label);

    this._dock = new St.BoxLayout({ name: 'aether-dock', vertical: false });
    this._dock.set_position(0, 0);

    this._launcher = new St.BoxLayout({ name: 'aether-launcher' });
    this._launcher.add_child(new St.Label({ text: 'Launcher — press Super' }));

    this._notifications = new St.BoxLayout({ name: 'aether-notifications', vertical: true });
    this._notifications.add_child(new St.Label({ text: 'Notifications' }));

    // Wire Shell global actors if available
    try {
      Main.layoutManager.addTopChrome(this._top);
      Main.layoutManager.addTopChrome(this._dock);
    } catch (e) {
      log('[AetherShell] top chrome unavailable: ' + e);
    }
    this._enabled = true;
    this._dock.enable?.();
    this._launcher.enable?.();
  }

  disable() {
    try {
      Main.layoutManager.removeTopChrome?.(this._top);
      Main.layoutManager.removeTopChrome?.(this._dock);
    } catch (e) {}
    this._top?.destroy?.();
    this._dock?.destroy?.();
    this._launcher?.destroy?.();
    this._notifications?.destroy?.();
    this._enabled = false;
  }
}
