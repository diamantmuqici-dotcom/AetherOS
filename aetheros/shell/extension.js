/* Aether Shell — GNOME extension entry (Wayland).
 * Components: Dock (magnification, minimize, pinning), Launcher (fuzzy search),
 * TopBar (status icons), Notifications (center). Full implementations in subfolders;
 * this stub registers the prefs page and logs activation.
 */
import { Extension } from 'resource:///org/gnome/shell/extensions/prefs.js';

export default class AetherShell extends Extension {
  enable() { this._actor = null; }
  disable() { this._actor = null; }
}
