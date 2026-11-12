# Security notes (dependencies and reverse proxy)

[Magyar változat](hu/security.md)

This page records what was verified for the MediaTrail image, not claims based
only on package version numbers on PyPI.

## Pillow and Brotli (verified)

| Risk | ID | Status in MediaTrail image policy |
| --- | --- | --- |
| XBM ReDoS in `Image.open()` | CVE-2026-112901 / GHSA-xgh8-jp6q-p5x8 | Fixed only in **Pillow ≥ 13.0.0**. Pillow **12.3.0 is affected**. |
| Brotli decoder OOB write | CVE-2026-111497 | Affects **Brotli 1.0.3–1.2.0**. Fixed in **Brotli 1.2.1**. |

### What the PyPI wheels actually ship

Inspected wheel contents (CPython 3.12):

| Artifact | Bundled `libbrotlidec` |
| --- | --- |
| `pillow-12.3.0-…-musllinux_1_2_x86_64.whl` | `…so.1.2.0` (**vulnerable**) |
| `pillow-13.0.0-…-musllinux_1_2_x86_64.whl` | `…so.1.2.0` (**vulnerable**) |
| `pillow-13.0.0-…-manylinux_2_28_x86_64.whl` | `…so.1.2.0` (**vulnerable**) |

So:

- Staying on 12.3.0 leaves the ReDoS open **and** still embeds Brotli 1.2.0.
- Installing the stock Pillow 13.0.0 wheel fixes the ReDoS but **does not** clear
  CVE-2026-111497, because the wheel still embeds Brotli 1.2.0.
- Alpine Linux **v3.23** publishes `brotli` / `brotli-libs` **1.2.1-r0** (fixed).
- A third-party “patched” manylinux wheel exists, but it is not an official
  Pillow release and has no musl/Alpine build we can trust for this image.

### Chosen mitigation

In the Docker **builder** stage:

1. Install Alpine imaging build deps, with **`brotli-dev=1.2.1-r0`** pinned.
2. Run `uv sync --locked --no-binary-package pillow` so Pillow **13.x** is
   compiled against the system Brotli instead of the PyPI wheel.
3. In the **runtime** stage, install matching shared libraries, with
   **`brotli-libs=1.2.1-r0`** pinned (no floating `apk upgrade`).
4. Run `scripts/verify_pillow_native.py` during the image build. The script
   fails if Pillow &lt; 13.0.0, if a bundled `pillow.libs` Brotli 1.2.0 is
   present, or if `BrotliDecoderVersion()` reports &lt; 1.2.1.

When upstream Pillow **13.1.0** (or later) ships wheels that embed Brotli
≥ 1.2.1, we can reconsider switching back to binary wheels after re-checking
the wheel contents the same way.

## Other dependency bumps (lockfile)

These were upgraded in `pyproject.toml` / `uv.lock` for confirmed advisories
from the Yamtrack #1773 scan and follow-up audit (not Pillow/Brotli):

| Package | Target in lock | Notes |
| --- | --- | --- |
| Django | ≥ 5.2.17 (locked 5.2.19) | CVE-2026-15307, 15337, 15830, 15920 |
| sqlparse | ≥ 0.6.0 (locked 0.6.1) | CVE-2026-54284, 59893, 59894, 71491 |
| aiohttp | ≥ 3.14.1 (locked 3.14.5) | Multiple 2026 advisories fixed in 3.14.x |
| urllib3 | ≥ 2.8.0 (locked 2.8.0) | Audit-listed fixes in 2.8.0 |

## `apk upgrade` and reproducibility

A blanket `apk upgrade --no-cache` was **rejected** for the image:

- It refreshes **every** installed Alpine package to whatever the branch index
  serves at build time.
- Two builds of the same Git commit can therefore ship different
  `openssl` / `sqlite-libs` / `pcre2` / etc. revisions without any repo change.
- CVE closure becomes unverifiable from Git alone.

Preferred approach:

- Pin the base image tag (`python:3.12-alpine3.23`) and pin security-relevant
  packages by version when adding them (for example `brotli-libs=1.2.1-r0`).
- After a Trivy/Grype scan of a built image, add **explicit** `apk add
  pkg=version` lines only for packages that are confirmed vulnerable and have
  a fixed version on the same Alpine branch.
- Do not reintroduce an unscoped `apk upgrade`.

## Trusted reverse proxies

`TRUSTED_PROXIES` (comma-separated IPs/CIDRs) configures nginx
`set_real_ip_from` + `real_ip_header X-Forwarded-For` only when set. Unset
keeps the previous behaviour (no trust of arbitrary forwarded client IPs).

## Open risks

- **Pillow 13.1.0 not yet released**: until official wheels embed Brotli ≥ 1.2.1,
  MediaTrail must keep building Pillow from source on Alpine (or vendor a
  verified wheel). Build time and the need for `-dev` packages are the cost.
- **WOFF2 exposure**: CVE-2026-111497 is reachable through FreeType when decoding
  untrusted WOFF2 fonts. MediaTrail does not intentionally load user-supplied
  fonts; the build still eliminates the vulnerable library copy.
- **Other Alpine OS CVEs** from container scans are **not** auto-closed. They
  need a scan of the built `ghcr.io/aicon/mediatrail` image and explicit
  package pins—blank `apk upgrade` is not an acceptable substitute.
- **Transitive Python advisories** outside the table above may still appear in
  `pip-audit` (for example tooling-only packages). Treat them case by case.
