# Biztonsági megjegyzések (függőségek és reverse proxy)

[English](../security.md)

Ez az oldal a MediaTrail image-ben **ellenőrzött** állapotot rögzíti. Egy tétel
addig **nyitott**, amíg egy újraépített `ghcr.io/aicon/mediatrail:dev` image
újabb szkennelése el nem tünteti a findinget.

## Pillow és Brotli (image-gate szerint igazolva)

| Kockázat | Azonosító | Állapot |
| --- | --- | --- |
| XBM ReDoS | CVE-2026-112901 | **Igazolva:** Pillow **13.0.0** forrásbuild |
| Brotli OOB | CVE-2026-111497 | **Igazolva:** rendszer **Brotli 1.2.1**, nincs beágyazott 1.2.0 |

A PyPI 12.3.0/13.0.0 wheelök továbbra is Brotli 1.2.0-t ágyaznak be; ezért
`--no-binary-package pillow` + pinelt `brotli-libs=1.2.1-r0` +
`scripts/verify_pillow_native.py`.

## Teljes Trivy-tábla a krb5 / Python HIGH kör előtt

Cél: `ghcr.io/aicon/mediatrail:dev` @ `3a081e4`  
Szűrés: HIGH + CRITICAL  
OS: Alpine 3.23.8

### Alpine (16 × HIGH)

Mind a `krb5-libs` **1.22.1-r0** csomagon: CVE-2026-107364, 112315–112323,
118380, 119079, 40355, 40356, 71199, 71200. Javított verzió: **1.22.3-r0**.

Fában: `krb5-libs=1.22.3-r0` pin a runtime Dockerfile-ban.
**Nem zárt**, amíg az új image-szken ezt meg nem erősíti.

### Python (2 × CRITICAL, 15 × HIGH)

| Sev | ID | Csomag | Telepítve | Fix |
| --- | --- | --- | --- | --- |
| CRITICAL | CVE-2026-102268 | PyJWT | 2.12.1 | 2.14.0 |
| CRITICAL | GHSA-6q48-6c7w-9gw2 | certifi | 2026.2.25 | 2026.10.18 |
| HIGH | CVE-2026-102267 / 102271 / 48526 / GHSA-pxh4-856f-4h89 | PyJWT | 2.12.1 | 2.13.0–2.14.0 |
| HIGH | CVE-2026-69247 / 69249 / GHSA-537c-gmf6-5ccf | cryptography | 46.0.7 | 48.0.1–50.0.0 |
| HIGH | CVE-2026-114136 / 114137 / 114138 | djangorestframework | 3.16.1 | 3.18.2 |
| HIGH | CVE-2026-114605 | dnspython | 2.8.0 | 2.9.0 |
| HIGH | CVE-2026-118669 / 49272 | oauthlib | 3.3.1 | 4.0.0 / 4.0.1 |
| HIGH | CVE-2026-49476 / 49477 | soupsieve | 2.8.3 | 2.8.4 |

Lock célok (újraszkennelésig **nyitottak**): PyJWT ~=2.14.0, certifi ≥2026.10.18,
cryptography ~=50.0, DRF ~=3.18.2, dnspython ~=2.9.0, oauthlib ~=4.0.1
(ehhez `django-allauth~=65.22`), soupsieve ~=2.8.4.

## Nyitott kockázatok

- A fenti Trivy-sorok, amíg az új `:dev` image újraszkennelése nem igazolja a
  javítást.
- Pillow forrásbuild, amíg nincs hivatalos Brotli ≥1.2.1 wheel.
- Az újraszkennelésen megjelenő új findingek külön listázandók.
- A django-allauth 65.22 bővebb ugrás; SSO használatnál érdemes smoke-test.
