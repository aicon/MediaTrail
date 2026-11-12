# Security notes (dependencies and reverse proxy)

[Magyar változat](hu/security.md)

Verified against built images, not PyPI version numbers alone.

## Status: security round closed (`8f7af77`)

Image: `ghcr.io/aicon/mediatrail:dev` @ `8f7af77`  
Workflow: https://github.com/aicon/MediaTrail/actions/runs/43234875929  

Trivy (`--severity CRITICAL,HIGH,MEDIUM,LOW`): **0 findings** (Alpine + Python).

Pillow/Brotli gate on the same build:

- `Pillow 13.0.0` built from source (`--no-binary-package pillow`)
- `BrotliDecoderVersion=1.2.1`
- `verify_pillow_native: OK`

## Pillow and Brotli

| Risk | ID | Status |
| --- | --- | --- |
| XBM ReDoS | CVE-2026-112901 | Fixed via Pillow ≥ 13.0.0 source build |
| Brotli OOB | CVE-2026-111497 | Fixed via Alpine `brotli-libs=1.2.1-r0` (not PyPI wheel libs) |

PyPI musllinux/manylinux wheels for Pillow 12.3.0 and 13.0.0 still embed Brotli
1.2.0. MediaTrail keeps building Pillow from source until official wheels ship
Brotli ≥ 1.2.1.

## Closed Trivy findings (trail)

### Was HIGH/CRITICAL on `3a081e4`

- Alpine: 16 × `krb5-libs` `1.22.1-r0` → pinned **`1.22.3-r0`**
- Python: PyJWT, certifi, cryptography, djangorestframework, dnspython,
  oauthlib (via django-allauth 65.22), soupsieve — bumped in lock / Dockerfile

### Was MEDIUM/LOW on `26af91a`

| Item | Resolution |
| --- | --- |
| zlib `1.3.2-r1` (CVE-2026-4738) | Pinned **`zlib=1.4-r0`** / `zlib-dev=1.4-r0` |
| PyJWT `2.14.0` MEDIUM | Locked **`PyJWT~=2.15.0`** (2.15.1) |
| multidict `6.7.1` | Locked **`multidict>=6.9.1`** (7.2.1) |
| soupsieve `2.8.4` MEDIUM | Locked **`soupsieve>=2.9.0`** (4.1) |
| apprise `1.9.9` LOW | Locked **`apprise~=1.11.0`** (compatible minor bump) |
| pip `25.0.1` (base image) | **Removed** from runtime (`/usr/local/.../pip*`); app does not need pip |

## `apk` policy

No blanket `apk upgrade`. Security-relevant OS packages are version-pinned
(`brotli-libs`, `krb5-libs`, `zlib`, …).

## Trusted reverse proxies

`TRUSTED_PROXIES` (comma-separated IPs/CIDRs) configures nginx
`set_real_ip_from` + `real_ip_header X-Forwarded-For` only when set. The
entrypoint validator uses an ash-safe character class (no bare `"` inside
`[!…]`, which broke BusyBox with `unexpected word (expecting ")")`).

## Residual notes (not open CVEs)

- Pillow remains a **source build** until upstream wheels embed Brotli ≥ 1.2.1.
- `django-allauth` is on **65.22** (needed for oauthlib 4); smoke-test SSO if used.
- Future Trivy hits on a newer base image need a new pin + rescan before claiming
  closure again.
