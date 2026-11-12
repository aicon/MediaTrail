# MediaTrail

[🇺🇸 English description (README in English)](README.md)

Saját üzemeltetésű személyes médiakatalógus és napló mindarról, amit megnézel, elolvasol vagy végigjátszol.

[![Verzió](https://img.shields.io/badge/verzió-0.25.23-blue.svg)](https://github.com/aicon/MediaTrail/releases)
[![Licenc: AGPL v3](https://img.shields.io/badge/Licenc-AGPL_v3-green.svg)](LICENSE)
[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Faicon%2Fmediatrail-blue?logo=docker)](https://github.com/aicon/MediaTrail/pkgs/container/mediatrail)
[![Dokumentáció](https://img.shields.io/badge/docs-mediatrail--docs-brightgreen.svg)](https://aicon.github.io/mediatrail-docs/hu/)
[![Támogatás Ko-fi-n](https://img.shields.io/badge/Ko--fi-Támogatás-ff5e5b?logo=ko-fi)](https://ko-fi.com/aiconwg)

---

A MediaTrail egy önálló, saját szerveren futtatható webes alkalmazás filmek, sorozatok, évadok, epizódok, animék, mangák, videojátékok, könyvek, képregények és társasjátékok naplózására. Rendszerezd a gyűjteményedet, jegyezz fel dátumokat, értékelj pontszámmal, kövesd a haladásodat, készíts egyéni listákat és böngészd a részletes statisztikákat.

A projekt a [Yamtrack](https://github.com/FuzzyGrim/Yamtrack) független forkjaként indult, olyan hiánypótló funkciókkal kiegészülve, mint a beépített REST API, a részletes epizód-előzmények, a valós idejű lejátszáskövetés, a Nuvio-integráció és a teljes magyar nyelvű felület.

---

## Főbb funkciók

- **Napló mindenhez:** Filmek, sorozatok, anime, manga, videojátékok, könyvek, képregények és társasjátékok. Pontszám, állapot, haladás, ismétlések, kezdő- és záródátum, jegyzet.
- **Évadok, és minden megtekintés:** Minden évad külön követhető. Egy epizódhoz több megtekintés is rögzíthető, saját dátummal és jegyzettel. A filmek és a sorozatok külön kezelhetők.
- **A változtatások előzménye:** Pontosan visszakövethető, mikor vetted fel a tételt, mikor kezdted el nézni/olvasni, és mikor fejezted be vagy nézted újra.
- **Kézi tételek:** Egyedi elem rögzítése, ha a támogatott online források egyike sem tartalmazza.
- **Közös listák:** Egyéni listák létrehozása tetszőleges célra, más fiókok bevonásával.
- **Közelgő megjelenések:** Beépített naptár a várható epizódokról és megjelenésekről, iCalendar (`.ics`) hivatkozással és Apprise értesítésekkel (Discord, Telegram, ntfy, Slack, e-mail stb.).
- **Több felhasználó saját könyvtárral:** Minden fiók teljesen elkülönített gyűjteménnyel rendelkezik. Helyi regisztráció vagy OIDC / közösségi bejelentkezés (Google, GitHub, Discord) a django-allauthon keresztül.
- **Magyar és angol felület:** A felület nyelve fiókonként választható a Beállításokban. A TMDB metaadatok nyelve külön szabályozható a `TMDB_LANG` változóval.
- **Importálás, benne a Nuvio:** Nuvio profilok importálása (csak új tételek hozzáadása vagy meglévők frissítése) titkosított adatokkal és ütemezéssel. Automatikus szinkronizáció érhető el Trakt, SIMKL, MyAnimeList, AniList és Kitsu fiókokhoz is. Teljes könyvtárexport/import CSV-ben, valamint IMDb, Goodreads, Steam és HowLongToBeat listák importja.
- **Beépített Scrobbler (Nuvio és médiaszerverek):** A MediaTrail közvetlenül tartalmazza a Stremio-protokollú addon végpontot, amely külön segédkonténer nélkül fogadja a lejátszási eseményeket a támogatott Nuvio appokból. Élő „Most nézem” sávokat biztosít és automatikusan bejegyzi a befejezéseket. A Jellyfin, Plex és Emby szerverek webhookon keresztül szinkronizálhatók.
- **REST API (Preview):** Modern API a `/api/v1/`, OpenAPI séma a `/api/schema/`, valamint interaktív Swagger felület a `/api/docs/` címen. Részletes dokumentáció: [API_HU.md](API_HU.md) ([English](API.md)).
- **Egyetlen konténeres működés:** Docker Compose telepítés beépített belső Redis-szel. Minden adat egyetlen csatolt mappában (`db`) marad.

---

## Előnézet: „Most nézem” és a beépített Scrobbler

A MediaTrail egy beépített Stremio-protokollú scrobbler szolgáltatást tartalmaz. **Nem streamel és nem játszik le médiát, valamint nem szolgáltat katalógust.** Kizárólag eseményfogadóként működik: fogadja a lejátszó állapotváltozásait (`start`, `pause`, `progress`, `stop`), és valós időben megjeleníti azokat a felületen.

Minden csatlakoztatott eszköz (telefon, nappali tévé, hálószobai tévé) saját, különálló sávot kap a kezdőlapon, így az egyidejű lejátszások nem írják felül egymást:

![Now Watching Banner](docs/screenshots/now-watching-desktop.png)

*(Kompakt nézetben is elérhető a kisebb kijelzőkhöz)*

![Now Watching Compact](docs/screenshots/now-watching-narrow.png)

A sávok közvetlenül a kezdőlap tetején láthatók:

![A Most nézem sáv a kezdőlapon](docs/screenshots/now-watching-desktop2.png)

### Hogyan működik a lejátszáskövetés?

- **Szükséges társalkalmazások:** Mivel a hivatalos Nuvio alkalmazások jelenleg nem küldenek lejátszási eseményeket, a szinkronizációhoz a kifejezetten erre felkészített klienseink kellenek: **[NuvioTV-MT](https://github.com/aicon/NuvioTV-MT)** (Android TV) és **[NuvioMobile-MT](https://github.com/aicon/NuvioMobile-MT)** (Android telefon / táblagép).
- **Nincs külön scrobbler konténer:** A scrobbler közvetlenül a MediaTrail része; nem kell külön hídprogramot vagy segédkonténert futtatnod.
- **Egyszerű beállítás:** Elég a MediaTrail addon manifest hivatkozását bemásolni a kliensben a **Beállítások → Bővítmények** menüpont alatt.
- **Eszközök elkülönítése:** Minden kliens stabil `deviceId`-t és automatikus nevet küld (pl. `TV · Shield` vagy `telefon · Pixel 8`).
- **Egyéni elnevezés:** A sáv neve a kezdőlapon tetszés szerint átírható; az elnevezés eszközönként megmarad stop vagy bezárás után is.
- **Befejezés stopnál:** Ha a kliens `stop` eseményt küld, és a haladás legalább **90%**, a MediaTrail egy befejezett megtekintést ír az előzménybe. A 90% átlépése lejátszás közben önmagában nem zárja le a címet.
- **Automatikus lecsengés:** A szüneteltetés és a leállítás csak az adott eszköz sávját érinti. Ha az alkalmazást bezárják `stop` esemény nélkül, az inaktív sávot az időzítő automatikusan eltávolítja.

---

## Gyors indítás

A MediaTrail egyetlen kész, beépített Redis-t tartalmazó Docker konténerként futtatható.

### Docker Compose

Hozz létre egy `docker-compose.yml` fájlt:

```yaml
services:
  mediatrail:
    image: ghcr.io/aicon/mediatrail:latest
    container_name: mediatrail
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      SECRET: longstring
      TMDB_LANG: hu
      TMDB_API:
      TVDB_API:
      URLS:
      ADMIN_ENABLED: false
      REGISTRATION: false
    volumes:
      - ./db:/mediatrail/db
```

### A környezeti értékek cseréje

Nyisd meg a Compose fájlt, és cseréld le a példa titkot:

```text
SECRET=longstring
```

A `SECRET` legyen egy hosszú, véletlenszerű karaktersorozat. Ha a MediaTrail fordított proxy (reverse proxy) mögött fut, a `URLS` változóban add meg a nyilvános elérést:

```text
URLS=https://mediatrail.pelda.hu
```

A cím mindig tartalmazza a protokollt (`https` vagy `http`), és ne legyen a végén perjel vagy almappa. Több cím vesszővel választható el.

A támogatott beállítások teljes listája a kézikönyvben található: [Környezet](https://aicon.github.io/mediatrail-docs/hu/runtime/).

Indítsd el a konténert:

```bash
docker compose up -d
```

Nyisd meg a böngészőben a `http://localhost:8000` címet.

> **Yamtrackről váltasz?**  
> A MediaTrail konténeren belüli adatútvonala a korábbi `/yamtrack/db` helyett `/mediatrail/db`. Elég a meglévő helyi adatkönyvtáradat átcsatolni: `./db:/mediatrail/db`.

---

## MediaTrail vs. Yamtrack

A MediaTrail egy független, nem hivatalos fork; **nem áll kapcsolatban az eredeti Yamtrack fejlesztőivel**.

### Miért készült a fork?
A MediaTrail alapja a Yamtrack `dev` ága a `v0.25.3` kiadás utánról (a 2026. július 12-i füles részletes oldal), amelybe beolvasztásra került a `#1378`-as REST API és a `#1608`-as epizód-előzmény munka.

Amikor a hivatalos Yamtrack átállt a `0.26`-os ágra, a MediaTrail szándékosan a bevált `0.25.x` ágon maradt a stabilitás, az önálló működés és a saját funkciók (pl. Nuvio) zavartalansága érdekében. A Yamtrack újabb részeiből szándékosan kimaradt az átírt naplóoldal, a statisztika újrarajzolása és a Trakt zip-import.

| Funkció | Hivatalos Yamtrack (Stabil) | MediaTrail |
| :--- | :---: | :---: |
| **REST API** (`/api/v1/`) | Nincs | Van |
| **Többszöri Epizód-előzmény** | Nincs | Van |
| **Beépített Scrobbler & Több eszközös „Most nézem”** | Nincs | Van |
| **Nuvio szinkronizáció / import** | Nincs | Van |
| **Magyar nyelvű felület** | Nincs | Van |
| **Beépített belső Redis** | Nincs *(Külön Redis kell)* | Van *(A konténerben fut)* |
| **Belső Python csomagnév** | `yamtrack` | `yamtrack` *(megtartva a stabilitásért)* |

---

## Kapcsolódó alkalmazások

A MediaTrail beépített scrobbleréhez az alábbi társalkalmazások biztosítják a valós idejű lejátszási adatokat:

| Név | Leírás |
| :--- | :--- |
| **[NuvioTV-MT](https://github.com/aicon/NuvioTV-MT)** | Android TV / Google TV kliens beépített MediaTrail scrobbler-támogatással. |
| **[NuvioMobile-MT](https://github.com/aicon/NuvioMobile-MT)** | Android telefon / táblagép kliens beépített MediaTrail scrobbler-támogatással. |

---

## Dokumentáció

A részletes felhasználói kézikönyv külön felületen érhető el:

- **Kézikönyv:** [https://aicon.github.io/mediatrail-docs/hu/](https://aicon.github.io/mediatrail-docs/hu/)
- **API-leírás:** [API_HU.md](API_HU.md) · [API.md](API.md)

A kézikönyv fejezetei: *Telepítés, Könyvtár, Live playback / Now Watching, Import (benne a Nuvio), Környezet, Fiókok, Karbantartás.*

---

## Támogatás

Ha hasznosnak találod a MediaTrailt és szeretnéd támogatni a fejlesztést és karbantartást:

[![Ko-fi támogatás](https://img.shields.io/badge/Ko--fi-Támogatás-ff5e5b?style=for-the-badge&logo=ko-fi)](https://ko-fi.com/aiconwg)

---

## Licenc és AGPL-3.0

A MediaTrail nyílt forráskódú szoftver a **GNU Affero General Public License v3.0 (AGPL-3.0)** alatt.  
A Yamtrack eredeti szerzői jogi jelzései megmaradtak. A MediaTrail saját kiegészítő nyilatkozata a `NOTICE` fájlban olvasható.

### Hálózati használat (AGPL-3.0 13. szakasz)
Amennyiben a programot hálózaton keresztül (több felhasználó számára) üzemelteted, a licenc megköveteli a futó pontos verzió forráskódjának nyilvános felkínálását:
- Állítsd be a `MEDIATRAIL_SOURCE_URL` környezeti változót a futó verzió publikus HTTP(S) forráskód-címére, mielőtt mások számára elérhetővé tennéd.
- Saját gépen futó, privát tesztpéldány esetén a változó üresen hagyható.