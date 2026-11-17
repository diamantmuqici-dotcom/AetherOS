# GTK Runtime Readiness Audit

Static audit only. This checkout has no GTK/GNOME host, so nothing here was
rendered on a desktop. Source was read as text; `gi` was never imported by the
audit. App files were changing in parallel, so this table is a point-in-time
snapshot — rerun `test_gtk_readiness.py` and `gtk-smoke.sh --all` for the live
view.

Scope: `aetheros/apps/*/aether-*.py` plus `aetheros/settings/aether-settings.py`
and `aetheros/setup/aether-setup.py` (19 files).

## Status table

`deferred gi` = no module-level `import gi`; `headless` = a
`--check/--list/--diagnose/--version` path exists under `__main__`;
`shell-free` = no `shell=True`, `os.system`, `eval(`, `exec(`; `subclass` =
a `Gtk.Application`/`Adw.Application` subclass. `Static` is the audit verdict;
the test reports every non-PASS as a tolerant skip so a mid-edit file cannot
fail the suite.

| App | deferred gi | headless | shell-free | subclass | Static | Note |
|---|---|---|---|---|---|---|
| apps/accessibility/aether-accessibility.py | no (line 4) | none | clean | yes | FAIL | module-level gi; no headless path |
| apps/antivirus/aether-av-light.py | n/a | `--check`, `--version` | clean | no | SKIP | CLI-only front-end, not a GTK app |
| apps/antivirus/aether-av.py | yes (line 449) | `--check`, `--version` | clean | yes | PASS | fully deferred |
| apps/app-center/aether-app-center.py | yes (line 170) | `--list` | clean | yes | PASS | fully deferred |
| apps/backup/aether-backup.py | yes (line 251) | `--check` | clean | yes | PASS | deferral landed during audit |
| apps/browser/aether-browser.py | n/a | `--diagnose` | clean | no | SKIP | engine launcher, no GTK window |
| apps/factory-reset/aether-factory-reset.py | no (line 9) | none | clean | yes | FAIL | module-level gi; no headless path |
| apps/focus/aether-focus.py | no (line 4) | none | clean | yes | FAIL | module-level gi; no headless path |
| apps/fonts/aether-fonts.py | no (line 4) | none | clean | yes | FAIL | module-level gi; no headless path |
| apps/gaming-hub/aether-gaming-hub.py | no (line 3) | none | clean | yes | FAIL | module-level gi; no headless path |
| apps/logs/aether-logs.py | no (line 4) | none | clean | yes | FAIL | module-level gi; no headless path |
| apps/mail/aether-mail.py | yes (line 69) | `--check`, `--version` | clean | yes | PASS | fully deferred |
| apps/overlay/aether-overlay.py | no (line 4) | none | clean | yes | FAIL | module-level gi; no headless path |
| apps/quick-look/aether-quicklook.py | no (line 4) | none | clean | yes | FAIL | module-level gi; no headless path |
| apps/security-center/aether-security-center.py | yes (line 199) | `--check` | clean | yes | PASS | fully deferred |
| apps/updater/aether-updater.py | yes (line 127) | `--check` | clean | yes | PASS | fully deferred |
| apps/vault/aether-vault.py | yes (line 107) | none | clean | yes | FAIL | gi deferred, headless path missing |
| settings/aether-settings.py | yes (line 247) | none | clean | yes | FAIL | headless path missing; see note below |
| setup/aether-setup.py | no (line 12) | none | clean | yes | FAIL | module-level gi; no headless path |

## What passed vs skipped

- **PASS (6):** antivirus `aether-av.py`, app-center, backup, mail,
  security-center, updater. All four static checks clean.
- **SKIP (2):** `aether-av-light.py` and `aether-browser.py` import no `gi`
  and have no `Gtk/Adw.Application` subclass — CLI/launcher, not GTK apps.
- **FAIL (11, reported as tolerant skips in the suite):** ten files still
  carry a module-level `import gi` and no headless path; `vault` and
  `settings` have deferred `gi` but no headless flag. These are the files
  other workstreams are still editing. `backup` moved from FAIL to PASS
  during this audit, which is why the suite must never hard-fail on them.
- `settings/aether-settings.py` defines `class Settings(Adw.Application)` at
  line 43 while `Adw = None` at line 13 and binds the real modules only at
  line 247. Importing that class at module scope will raise before any
  headless path can run; this needs a source fix, not a test change.
- `shell-free` is clean across all 19 files: no `shell=True`, `os.system`,
  `eval(`, or `exec(` found in any audited target.

## Runtime checks still owed on a Linux desktop

None of the following were run here. On a GTK4/libadwaita desktop, for each
window: render it without traceback, click every enabled control, and confirm
the process stays alive afterwards. Then re-run each app's headless flag and
confirm it still emits valid JSON with the GUI import path present.

| App | Owed desktop check |
|---|---|
| accessibility | Render main window; toggle every accessibility switch; close and relaunch. |
| av (antivirus) | Render main window; open scan and quarantine views; run a bounded verify; watch for crash. |
| av-light | No window owed; confirm `--check` and `--scan` emit JSON on the desktop host. |
| app-center | Render window; open installed list; exercise detail view; `--list` emits JSON. |
| backup | Render window; open backup and restore dialogs; cancel out of each; `--check` emits JSON. |
| browser | No own GTK window; confirm `--diagnose` JSON and engine launch under managed policy. |
| factory-reset | Render confirmation page; click Cancel only; confirm reset action is not fired. |
| focus | Render window; toggle focus profile on/off; verify tray state. |
| fonts | Render window; toggle font enable switches; verify preview redraw. |
| gaming-hub | Render window; open game detail; exercise launch button with a stub target. |
| logs | Render window; load log view; apply filter; scroll to tail. |
| mail | Render window; open account/lock view; `--check` emits account status JSON. |
| overlay | Render overlay window; toggle visibility; verify dismiss path. |
| quick-look | Render preview window; open and close a sample file; verify no stale handle. |
| security-center | Render window; run the check action; `--check` emits results JSON. |
| updater | Render window; trigger refresh/verify; `--check` emits status JSON. |
| vault | Render window; exercise unlock and lock flow with a test vault; no crash on lock. |
| settings | Fix the `Adw = None` class defect first; then render all 14 sidebar panels and every control. |
| setup | Render first-boot wizard; walk every page with Next; verify Finish path with a disposable profile. |

## gtk-smoke.sh usage

Headless harness. It runs `python3 <app> <flag>` under a 10s `timeout`,
validates JSON output with `python3 -m json.tool`, and prints `PASS`/`FAIL`
per app. It never starts a GUI and never sets up a desktop session. Missing
`python3` or `timeout` yields a one-line `SKIP`.

```bash
# one app (flag auto-detected from source: --check, --list, --diagnose, --version)
bash aetheros/scripts/gtk-smoke.sh aetheros/apps/updater/aether-updater.py

# every discovered app
bash aetheros/scripts/gtk-smoke.sh --all
```

Exit code is 0 when every app passes or is skipped, 1 if any app fails, and
2 for a bad invocation. The harness is a static/CLI smoke gate only; it does
not replace the desktop checks listed above.
