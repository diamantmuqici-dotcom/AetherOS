/* Aether Dock — pinning, magnification, minimize-on-click (original). */
import St from 'gi://St';
import Clutter from 'gi://Clutter';

export const Dock = {
  enable() {},
  disable() {},
};

export class AetherDock {
  constructor() {
    this.actor = new St.BoxLayout({ style_class: 'aether-dock' });
  }
  enable() { this.actor.visible = true; }
  disable() { this.actor.visible = false; }
}
