# AetherOS website

Static download and verification site for AetherOS 1.0. No build step, no template
engine, no package manager, no analytics, no cookies, and no third-party requests.

## Files

| Path | Role |
|---|---|
| `index.html` | Product hero, feature grid, calls to download / privacy / verify. |
| `download.html` | Release artifacts and the version-token note. |
| `verify.html` | SHA-256 and Ed25519 verification walkthrough. |
| `privacy.html` | What Aether sends and does not send. |
| `assets/style.css` | Shared dark x blue cyber-noir stylesheet. |
| `assets/aether-logo.svg` | Logo mark (kept as-is). |
| `assets/aether-preview.png`, `assets/aether.ico` | Desktop preview and favicon (kept as-is). |
| `site.js` | Same-page smooth scroll and a local copy-to-clipboard helper only. |

## Publish

1. Copy the whole `website/` directory to any static host (GitHub Pages, a plain
   nginx/Apache docroot, an object-storage bucket with static site hosting).
2. Serve `index.html` as the directory index. There is nothing to compile and no
   server-side configuration to add.
3. Keep `site.js`, `assets/style.css`, and the three image assets alongside the
   HTML files. All paths are relative.
4. Confirm the host does not inject analytics, beacons, or third-party scripts.
   The site itself makes no external requests; any injected tag is the host's.

## Release checklist

1. **Update the version token.** Every release URL on `download.html` and every
   filename in `verify.html` uses `1.0` as the version placeholder. Replace it
   with the exact new version string before publishing the release.
2. **Build the ISO in GitHub Actions.** Use the repository's ISO build pipeline.
   No ISO is built from this website directory.
3. **Generate or rotate the Ed25519 release key** on the offline signing host via
   `aetheros/scripts/signing/generate-release-key.sh`. Record the printed
   `SHA256:<hex>` fingerprint in the release notes.
4. **Stage the public key** in the build tree at
   `iso/config/includes.chroot/usr/share/aether/updates/aether-release.pub.pem`
   so a booted image can verify signed updates.
5. **Produce the release artifacts** with
   `aetheros/scripts/signing/make-release-metadata.py`:
   `release-metadata.json` (canonical JSON with embedded base64 Ed25519
   signature) and `SHA256SUMS` (coreutils format).
6. **Produce the `.sig` files** with `aetheros/scripts/signing/sign-iso.sh`:
   `<iso>.sha256`, the optional GPG `<iso>.sha256.asc` when a GPG key is set, and
   `<manifest>.sig` for an `aether-release/1` update manifest when one is
   published. Publish `aether-release.pub.pem` as well.
7. **Upload all artifacts** to the GitHub Releases entry so the
   `releases/latest/download/<filename>` links resolve. Keep the filenames
   identical to the ones referenced in the HTML.
8. **Do not paste a checksum into the HTML.** The site deliberately prints no
   digest; `SHA256SUMS` is the only source. Keep it that way.
9. **Recheck the external-link audit** before publishing: the only `http(s)`
   URLs in the site are the GitHub Releases links, the DuckDuckGo link on
   `privacy.html`, and the SVG XML namespace in the kept logo.

## Build status

No ISO was built, signed, or uploaded from this bench. The GitHub Releases links
follow the project's published URL pattern; whether a given asset exists depends
on the release pipeline, not on this site. Treat the verification steps in
`verify.html` as the authority on what a valid release looks like.

## External-link audit

```sh
# Expect only GitHub Releases URLs and the DuckDuckGo link.
grep -RInE 'https?://' website --include='*.html' --include='*.js' --include='*.css'

# Expect no matches in shipped code.
grep -RInE 'fetch\(|XMLHttpRequest|sendBeacon|navigator\.geolocation|document\.cookie|localStorage|sessionStorage|googletagmanager|google-analytics|gtag\(' website --include='*.html' --include='*.js'
```

The SVG XML namespace (`http://www.w3.org/2000/svg`) is an identifier, not a
network request, and the logo is kept as-is. The second command returns no
matches in the HTML or JavaScript.
