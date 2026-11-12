# Biztonsági megjegyzések (függőségek és reverse proxy)

[English](../security.md)

Az ellenőrzés a buildelt image-en történik, nem csupán a PyPI verziószámokon.

## Állapot: biztonsági kör lezárva (`8f7af77`)

Image: `ghcr.io/aicon/mediatrail:dev` @ `8f7af77`  
Workflow: https://github.com/aicon/MediaTrail/actions/runs/43234875929  

Trivy (CRITICAL+HIGH+MEDIUM+LOW): **0 találat** (Alpine + Python).

Ugyanazon a builden a Pillow/Brotli gate:

- Pillow **13.0.0** forrásból
- `BrotliDecoderVersion=1.2.1`
- `verify_pillow_native: OK`

## Pillow és Brotli

A PyPI 12.3.0/13.0.0 wheelök Brotli 1.2.0-t ágyaznak be. A MediaTrail ezért
`--no-binary-package pillow` + pinelt `brotli-libs=1.2.1-r0` mellett épít, amíg
nincs hivatalos Brotli ≥ 1.2.1 wheel.

## Lezárt Trivy-tételek (nyomvonal)

- `krb5-libs` → **1.22.3-r0**
- PyJWT / certifi / cryptography / DRF / dnspython / oauthlib(+allauth 65.22) /
  soupsieve frissítve
- MEDIUM/LOW: zlib **1.4-r0**, PyJWT **2.15.x**, multidict **≥6.9.1**, soupsieve
  **≥2.9**, apprise **1.11.x**, a base image **pip** eltávolítva (runtime-ban
  nem kell)

## Egyéb

- Nincs vak `apk upgrade`; OS-csomagok explicit pinjei.
- `TRUSTED_PROXIES`: ash-biztos validáció (a korábbi `"` a karakterosztályban
  BusyBox szintaxishibát okozott).
- Pillow forrásbuild és az allauth 65.22 SSO smoke-test továbbra is
  üzemeltetési megjegyzés, nem nyitott CVE-lista.
