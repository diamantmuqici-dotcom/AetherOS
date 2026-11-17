"""AetherOS signed update core: signature, apt state and release planning."""

from .signature import (
    MAX_MANIFEST_BYTES,
    SCHEMA_VERSION,
    SignatureError,
    canonical_signing_input,
    sign_release,
    verify_release,
)
from .apt_policy import (
    parse_apt_policy,
    parse_simulated_upgrade,
    run_apt_policy,
    run_simulated_upgrade,
)
from .release import (
    CHANNELS,
    ReleaseError,
    load_release,
    plan_upgrade,
    select_channel,
)

__all__ = [
    "SignatureError",
    "SCHEMA_VERSION",
    "MAX_MANIFEST_BYTES",
    "canonical_signing_input",
    "sign_release",
    "verify_release",
    "parse_apt_policy",
    "parse_simulated_upgrade",
    "run_apt_policy",
    "run_simulated_upgrade",
    "ReleaseError",
    "CHANNELS",
    "load_release",
    "select_channel",
    "plan_upgrade",
]
