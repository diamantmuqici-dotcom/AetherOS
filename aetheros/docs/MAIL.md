# Aether Mail

Aether Mail is a local-first IMAP/SMTP client built into AetherOS. Account
metadata stays local; passwords live in the system keyring or in an
authenticated, passphrase-encrypted container. No plaintext password is
written to disk.

## Files and formats

| Path | Contents | Permissions |
|---|---|---|
| `~/.config/aether/mail/accounts.json` | Account metadata (hosts, ports, TLS modes, username, auth method) | `0600` |
| `~/.local/share/aether/mail/credentials.enc` | Fallback encrypted credential container | `0600` |
| SecretService keyring | Passwords when libsecret is available | daemon-managed |

`XDG_CONFIG_HOME` and `XDG_DATA_HOME` override the two base directories.

The encrypted container reuses the Aether Vault v2 format: Argon2id derives a
256-bit key from the passphrase with a fresh 32-byte salt, ChaCha20-Poly1305
encrypts a JSON payload with a fresh 96-bit nonce, and the header is used as
associated data. Every write is self-verified before an atomic `os.replace()`.
A wrong passphrase or a flipped byte fails closed.

Account JSON contains no secrets:

```json
{
  "format": "aether-mail-accounts",
  "version": 1,
  "accounts": [
    {
      "id": "personal",
      "email": "user@example.org",
      "imap_host": "imap.example.org",
      "imap_port": 993,
      "imap_tls": "ssl",
      "smtp_host": "smtp.example.org",
      "smtp_port": 465,
      "smtp_security": "ssl",
      "username": "user@example.org",
      "auth_method": "password"
    }
  ]
}
```

`imap_tls` and `smtp_security` accept `ssl` (implicit TLS) or `starttls`.
Cleartext transport is rejected by `Account.validate()`, the IMAP layer, and
the SMTP layer. `auth_method` accepts `password` or `oauth2`; OAuth2 supplies
an XOAUTH2 bearer token in place of the password.

## Security model

- TLS is mandatory on both transports; plaintext credentials never cross a
  cleartext socket.
- SecretService is preferred when `gi.repository.Secret` loads. Otherwise the
  passphrase-encrypted file backend is used. Both are gated behind an unlock
  flag; locked state refuses every credential read and write.
- `MailLock` stores only a SHA-256 digest of an Argon2id-derived verifier. It
  locks on demand, after inactivity (default 300 seconds), on logind
  `PrepareForSleep`, and on screen-saver `ActiveChanged`.
- IMAP sessions are read-only (`BODY.PEEK`), capped at 200 headers per fetch
  and 2 MiB per body. Only `text/plain` parts are extracted; HTML is never
  executed.
- Mail bodies pass through an allowlist sanitiser. `script`, `style`, `iframe`,
  event handlers, `javascript:`/`data:` URLs, and active elements are removed.
  Remote images become inline placeholders unless explicitly enabled.

## OpenPGP

`gpg` runs with `--batch --yes --no-tty`, argv only, `shell=False`.
Plaintext/ciphertext travel over stdin; only a validated hex fingerprint
reaches argv. Missing or failing gpg fails closed.

## Commands

`aether-mail` launches the GTK4/libadwaita client.
`aether-mail --check` prints account/lock status JSON without loading gi.
`aether-mail --version` prints the version.

In the UI: Add account, Sync, message read, Compose, Lock / Unlock.
The Compose review step shows PGP status before any send.

## Limitations

No calendar, contacts, or Exchange/MAPI support. No offline queue, no
server-side search, no thread grouping, and no attachments. HTML is shown as
sanitised text, not rendered markup. OAuth2 needs an externally supplied token;
there is no interactive browser login. PGP key generation and key management
are out of scope; import keys into the user's GPG keyring first.
