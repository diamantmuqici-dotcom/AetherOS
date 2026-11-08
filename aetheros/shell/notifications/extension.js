/* Aether Notifications — center, DND sync (original). */
import St from 'gi://St';
export class AetherNotifications {
  constructor() { this.actor = new St.BoxLayout({ style_class: 'aether-notifications' }); }
  enable() {}
  disable() {}
}
