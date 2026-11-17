"""AetherOS backup core: canonical manifests and non-destructive restore."""

from .manifest import (
    MANIFEST_NAME,
    MAX_FILES,
    MAX_FILE_BYTES,
    MAX_MANIFEST_BYTES,
    MAX_TOTAL_BYTES,
    SCHEMA_VERSION,
    ManifestError,
    build_manifest,
    iter_snapshot_files,
    load_manifest,
    manifest_digest,
    normalize_rel,
    save_manifest,
    sha256_file,
    sign_manifest,
    verify_manifest,
)
from .restore import (
    RestoreError,
    execute_plan,
    plan_restore,
)

__all__ = [
    "SCHEMA_VERSION",
    "MANIFEST_NAME",
    "MAX_MANIFEST_BYTES",
    "MAX_FILES",
    "MAX_FILE_BYTES",
    "MAX_TOTAL_BYTES",
    "ManifestError",
    "normalize_rel",
    "sha256_file",
    "iter_snapshot_files",
    "build_manifest",
    "manifest_digest",
    "sign_manifest",
    "save_manifest",
    "load_manifest",
    "verify_manifest",
    "RestoreError",
    "plan_restore",
    "execute_plan",
]
