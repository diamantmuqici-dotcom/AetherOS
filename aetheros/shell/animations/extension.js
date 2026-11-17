import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import Gio from 'gi://Gio';

export default class AetherAnimations extends Extension {
  enable() {
    this._profile = new Gio.Settings({ schema_id: 'org.aether.animations' });
    this._interface = new Gio.Settings({ schema_id: 'org.gnome.desktop.interface' });
    this._changedId = this._profile.connect('changed::profile', () => this._apply());
    this._apply();
  }

  _apply() {
    const profile = this._profile.get_string('profile');
    this._interface.set_boolean('enable-animations', profile !== 'off');
  }

  disable() {
    if (this._changedId) {
      this._profile.disconnect(this._changedId);
      this._changedId = 0;
    }
    this._interface?.set_boolean('enable-animations', true);
    this._profile = null;
    this._interface = null;
  }
}
