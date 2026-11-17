"""Release-channel selection and upgrade planning from verified manifests."""

from __future__ import annotations

from .signature import SCHEMA_VERSION

__all__ = [
    "ReleaseError",
    "CHANNELS",
    "load_release",
    "select_channel",
    "plan_upgrade",
]

CHANNELS = ("stable", "beta", "development")
_REQUIRED = ("schema", "channel", "expires", "packages", "min_os_version")


class ReleaseError(ValueError):
    """Raised when a manifest is structurally invalid or a channel is unknown."""


def load_release(manifest: dict) -> dict:
    """Validate a verified manifest and return a normalized copy."""
    if not isinstance(manifest, dict):
        raise ReleaseError("manifest must be a dict")
    for field in _REQUIRED:
        if field not in manifest:
            raise ReleaseError(f"missing field: {field}")

    if manifest["schema"] != SCHEMA_VERSION:
        raise ReleaseError("unsupported schema")
    if manifest["channel"] not in CHANNELS:
        raise ReleaseError("unknown channel")
    if not isinstance(manifest["expires"], str) or not manifest["expires"].strip():
        raise ReleaseError("invalid expires")
    if not isinstance(manifest["min_os_version"], str) or not manifest["min_os_version"].strip():
        raise ReleaseError("invalid min_os_version")

    packages = manifest["packages"]
    if not isinstance(packages, dict):
        raise ReleaseError("packages must be an object")
    clean = {}
    for name, version in packages.items():
        if not isinstance(name, str) or not name:
            raise ReleaseError("invalid package name")
        if not isinstance(version, str) or not version:
            raise ReleaseError(f"invalid pin for {name}")
        clean[name] = version

    result = dict(manifest)
    result["packages"] = clean
    return result


def select_channel(manifest: dict, channel: str) -> dict:
    """Return the effective release view for a channel; per-channel pins override base pins."""
    release = load_release(manifest)
    if channel not in CHANNELS:
        raise ReleaseError(f"unknown channel: {channel}")

    view = {
        "schema": release["schema"],
        "channel": channel,
        "expires": release["expires"],
        "min_os_version": release["min_os_version"],
        "packages": dict(release["packages"]),
    }
    channels = release.get("channels")
    if isinstance(channels, dict) and isinstance(channels.get(channel), dict):
        override = channels[channel]
        if isinstance(override.get("packages"), dict):
            view["packages"] = dict(override["packages"])
        for key in ("expires", "min_os_version"):
            if key in override:
                view[key] = override[key]
    elif release["channel"] != channel:
        raise ReleaseError(f"manifest is for channel {release['channel']!r}")
    return view


def plan_upgrade(manifest: dict, installed_upgrades: list[dict]) -> list[dict]:
    """Intersect observed upgrades with manifest pins; only exact pinned versions pass."""
    if not isinstance(manifest, dict):
        return []
    pins = manifest.get("packages")
    if not isinstance(pins, dict) or not isinstance(installed_upgrades, list):
        return []

    plan: list[dict] = []
    for entry in installed_upgrades:
        if not isinstance(entry, dict):
            continue
        name = entry.get("package")
        # A candidate that disagrees with the pin is excluded, not rewritten.
        if not isinstance(name, str) or name not in pins:
            continue
        pinned = pins[name]
        if entry.get("candidate") != pinned:
            continue
        plan.append({
            "package": name,
            "version": pinned,
            "current": entry.get("current", ""),
            "origin": entry.get("origin", ""),
        })
    return plan
