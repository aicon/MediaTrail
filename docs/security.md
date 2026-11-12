# Security notes (dependencies and reverse proxy)

[Magyar változat](hu/security.md)

This page records what was verified for the MediaTrail image, not claims based
only on package version numbers on PyPI. Items stay **open** until a rebuilt
`ghcr.io/aicon/mediatrail:dev` image is scanned again and the finding is gone.

## Pillow and Brotli (verified in image gate)

| Risk | ID | Status |
| --- | --- | --- |
| XBM ReDoS in `Image.open()` | CVE-2026-112901 / GHSA-xgh8-jp6q-p5x8 | **Verified:** image builds Pillow **13.0.0** from source. |
| Brotli decoder OOB write | CVE-2026-111497 | **Verified:** runtime links Alpine **Brotli 1.2.1** (`BrotliDecoderVersion=1.2.1`); no bundled `pillow.libs` Brotli 1.2.0. |

PyPI musllinux/manylinux wheels for Pillow 12.3.0 and 13.0.0 still embed
`libbrotlidec…so.1.2.0`. MediaTrail therefore uses
`uv sync --no-binary-package pillow` plus pinned
`brotli-libs=1.2.1-r0` / `brotli-dev=1.2.1-r0`, gated by
`scripts/verify_pillow_native.py`.

## Full Trivy table before the krb5 / Python HIGH pass

Scan target: `ghcr.io/aicon/mediatrail:dev` @ `3a081e4`  
Filters: `--severity HIGH,CRITICAL`  
OS: Alpine 3.23.8

### Alpine (16 × HIGH, 0 × CRITICAL)

| Severity | ID | Package | Installed | Fixed |
| --- | --- | --- | --- | --- |
| HIGH | CVE-2026-107364 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-112315 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-112316 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-112317 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-112318 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-112319 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-112320 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-112321 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-112322 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-112323 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-118380 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-119079 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-40355 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-40356 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-71199 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |
| HIGH | CVE-2026-71200 | krb5-libs | 1.22.1-r0 | 1.22.3-r0 |

Mitigation in tree: pin `krb5-libs=1.22.3-r0` in the runtime Dockerfile.
**Not closed until the next image scan confirms the installed version.**

### Python (2 × CRITICAL, 15 × HIGH)

| Severity | ID | Package | Installed | Fixed |
| --- | --- | --- | --- | --- |
| CRITICAL | CVE-2026-102268 | PyJWT | 2.12.1 | 2.14.0 |
| CRITICAL | GHSA-6q48-6c7w-9gw2 | certifi | 2026.2.25 | 2026.10.18 |
| HIGH | CVE-2026-102267 | PyJWT | 2.12.1 | 2.14.0 |
| HIGH | CVE-2026-102271 | PyJWT | 2.12.1 | 2.14.0 |
| HIGH | CVE-2026-48526 | PyJWT | 2.12.1 | 2.13.0 |
| HIGH | GHSA-pxh4-856f-4h89 | PyJWT | 2.12.1 | 2.14.0 |
| HIGH | CVE-2026-69247 | cryptography | 46.0.7 | 50.0.0 |
| HIGH | CVE-2026-69249 | cryptography | 46.0.7 | 49.0.0 |
| HIGH | GHSA-537c-gmf6-5ccf | cryptography | 46.0.7 | 48.0.1 |
| HIGH | CVE-2026-114136 | djangorestframework | 3.16.1 | 3.18.2 |
| HIGH | CVE-2026-114137 | djangorestframework | 3.16.1 | 3.18.2 |
| HIGH | CVE-2026-114138 | djangorestframework | 3.16.1 | 3.18.2 |
| HIGH | CVE-2026-114605 | dnspython | 2.8.0 | 2.9.0 |
| HIGH | CVE-2026-118669 | oauthlib | 3.3.1 | 4.0.0 |
| HIGH | CVE-2026-49272 | oauthlib | 3.3.1 | 4.0.1 |
| HIGH | CVE-2026-49476 | soupsieve | 2.8.3 | 2.8.4 |
| HIGH | CVE-2026-49477 | soupsieve | 2.8.3 | 2.8.4 |

Lock / Dockerfile targets (still **open** until rescanned):

| Package | Target | Notes |
| --- | --- | --- |
| PyJWT | ~=2.14.0 | Advisories ask for ≥2.14.0 |
| certifi | ≥2026.10.18 | Locked 2026.10.23 |
| cryptography | ~=50.0 | Covers 48.0.1 / 49.0.0 / 50.0.0 floors |
| djangorestframework | ~=3.18.2 | Installed in Dockerfile after `uv sync` |
| dnspython | ~=2.9.0 | |
| oauthlib | ~=4.0.1 | Requires `django-allauth[socialaccount]~=65.22` (older allauth caps oauthlib &lt;4) |
| soupsieve | ~=2.8.4 | |

## Earlier lockfile bumps (already in prior security commits)

| Package | Locked | Notes |
| --- | --- | --- |
| Django | 5.2.19 | CVE-2026-15307, 15337, 15830, 15920 |
| sqlparse | 0.6.1 | CVE-2026-54284, 59893, 59894, 71491 |
| aiohttp | 3.14.5 | 2026 advisories in 3.14.x |
| urllib3 | 2.8.0 | Audit-listed fixes |

## `apk` reproducibility

No blanket `apk upgrade`. Security-relevant OS packages are pinned explicitly
(`brotli-libs=1.2.1-r0`, `krb5-libs=1.22.3-r0`, …). New Alpine findings need a
new pin after a scan—not an unscoped upgrade.

## Trusted reverse proxies

`TRUSTED_PROXIES` (comma-separated IPs/CIDRs) configures nginx
`set_real_ip_from` + `real_ip_header X-Forwarded-For` only when set.

## Rescan after `26af91a` (HIGH/CRITICAL)

Image: `ghcr.io/aicon/mediatrail:dev` @ `26af91a`  
Workflow: https://github.com/aicon/MediaTrail/actions/runs/43233299217  
Gate: Pillow 13.0.0 source build, `BrotliDecoderVersion=1.2.1`,
`krb5-libs` upgraded `1.22.1-r0 → 1.22.3-r0`.

Trivy `--severity HIGH,CRITICAL`: **Alpine 0**, **Python 0**.

The HIGH/CRITICAL rows in the table above are therefore cleared **on this
image digest**. They stay documented so the before/after trail is auditable.

## Still open (MEDIUM/LOW on the same image — not closed)

Trivy `--severity MEDIUM,LOW` after `26af91a`:

| Severity | Type | ID | Package | Installed | Fixed |
| --- | --- | --- | --- | --- | --- |
| MEDIUM | alpine | CVE-2026-4738 | zlib | 1.3.2-r1 | 1.4-r0 |
| MEDIUM | python-pkg | CVE-2026-101918 | PyJWT | 2.14.0 | 2.15.0 |
| MEDIUM | python-pkg | CVE-2026-102275 | PyJWT | 2.14.0 | 2.15.0 |
| MEDIUM | python-pkg | CVE-2026-104874 | multidict | 6.7.1 | 6.9.1 |
| MEDIUM | python-pkg | CVE-2026-85999 | soupsieve | 2.8.4 | 2.9.0 |
| MEDIUM | python-pkg | CVE-2026-86000 | soupsieve | 2.8.4 | 2.9.0 |
| MEDIUM | python-pkg | CVE-2025-8869 | pip | 25.0.1 | 25.3 |
| MEDIUM | python-pkg | CVE-2026-13346 | pip | 25.0.1 | 26.2.0 |
| MEDIUM | python-pkg | CVE-2026-3219 | pip | 25.0.1 | 26.1 |
| MEDIUM | python-pkg | CVE-2026-6357 | pip | 25.0.1 | 26.1 |
| MEDIUM | python-pkg | CVE-2026-8643 | pip | 25.0.1 | 26.1.2 |
| LOW | python-pkg | CVE-2026-59180 | apprise | 1.9.9 | 1.11.0 |
| LOW | python-pkg | CVE-2026-1703 | pip | 25.0.1 | 26.0 |

These are **open**. Do not treat them as fixed until pinned/upgraded and
rescanned on a new image.

## Other open risks

- **Pillow still built from source** until upstream wheels embed Brotli ≥ 1.2.1
  (expected around Pillow 13.1.0).
- **django-allauth 65.22** is a broader upgrade than a leaf pin; smoke-test
  social login after deploy if SSO is in use.
- Runtime `pip` inside the image is a transitive/tooling surface; bumping it
  needs a deliberate lock/image change, not an implicit claim of closure.
