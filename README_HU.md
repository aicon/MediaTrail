# MediaTrail

[🇺🇸 English description (README in English)](README.md)

Önállóan üzemeltethető személyes médiakatalógus és digitális krónika mindarról, amit megnézel, elolvasol vagy végigjátszol.

[![Verzió](https://img.shields.io/badge/verzió-0.25.28-blue.svg)](https://github.com/aicon/MediaTrail/releases)
[![Licenc: AGPL v3](https://img.shields.io/badge/Licenc-AGPL_v3-green.svg)](LICENSE)
[![Docker Image](https://img.shields.io/badge/docker-ghcr.io%2Faicon%2Fmediatrail-blue?logo=docker)](https://github.com/aicon/MediaTrail/pkgs/container/mediatrail)
[![Dokumentáció](https://img.shields.io/badge/docs-mediatrail--docs-brightgreen.svg)](https://aicon.github.io/mediatrail-docs/hu/)
[![Támogatás Ko-fi-n](https://img.shields.io/badge/Ko--fi-Támogatás-ff5e5b?logo=ko-fi)](https://ko-fi.com/aiconwg)

---

A MediaTrail egy önállóan üzemeltethető webes alkalmazás filmek, tévésorozatok, évadok, epizódok, animék, mangák, videojátékok, könyvek, képregények és társasjátékok egy helyen történő követésére és rendszerezésére. Gondozd a gyűjteményedet, jegyezz fel fontos dátumokat, értékeld a műveket, kövesd nyomon az előrehaladásodat, állíts össze egyéni listákat, és fedezd fel a személyes statisztikáidat.

A projekt a [Yamtrack](https://github.com/FuzzyGrim/Yamtrack) független leágazásaként (forkjaként) indult útjára, olyan alapvető képességekkel gazdagodva, mint a beépített REST API, a részletes epizód-előzmények, a valós idejű lejátszáskövetés, a mélyreható Nuvio-integráció, valamint a teljes körű magyar kezelőfelület.

---

## Főbb funkciók

- **Minden műnek saját lapja van:** Filmek, sorozatok, animék, mangák, videojátékok, könyvek, képregények és társasjátékok. Rögzíthetsz személyes értékelést, megtekintési állapotot, előrehaladást, számlálhatod az ismétléseket, megadhatsz kezdő- és záródátumot, valamint egyéni jegyzeteket fűzhetsz hozzájuk.
- **Évadok és teljes újranézési előzmények:** Az évadokat egymástól függetlenül követheted nyomon. Egyetlen epizódhoz több önálló megtekintési bejegyzést is fűzhetsz, mindegyikhez saját időbélyeggel és jegyzettel. A filmek és sorozatok áttekinthetően elkülönülnek egymástól.
- **Napló (Journal):** Napról napra átnézheted, mit néztél, olvastál vagy játszottál — poszterekkel, állapotjelzőkkel és relatív időbélyegekkel.
- **Részletesebb statisztikák:** Asztali nézetben egy sorban az összefoglaló kártyák, a diagramfeliratok a választott nyelven, plusz Folyamatban, Értékelt arány és fogyasztási bontás.
- **Részletes műveletnapló:** Lépésről lépésre visszakövetheted az eseményeket: mikor adtál hozzá egy tételt a gyűjteményedhez, mikor kezdted el nézni vagy olvasni, és mikor értél a végére vagy kezdted elölről.
- **Egyéni tételek kézi rögzítése:** Tetszés szerint felvehetsz egyedi bejegyzéseket akkor is, ha az online katalógusok egyike sem ismeri az adott művet.
- **Együttműködés és megosztott listák:** Bármilyen célra létrehozhatsz tematikus listákat, és a szerkesztésbe bevonhatod a szerver többi felhasználóját is.
- **Közelgő megjelenések és naptár:** Mindig szem előtt tarthatod a várható bemutatókat a külső alkalmazásokba exportálható iCalendar (`.ics`) hivatkozás és az automatikus Apprise-értesítések (Discord, Telegram, ntfy, Slack, e-mail stb.) segítségével.
- **Több felhasználó, teljesen elkülönülő gyűjtemények:** Minden felhasználó saját, elszeparált médiatárat kezel. A belépés történhet helyi jelszóval vagy közösségi / OIDC azonosítóval (Google, GitHub, Discord) a django-allauth modulon keresztül.
- **Magyar és angol kezelőfelület:** A kívánt nyelvet fiókonként külön-külön megválaszthatod a Beállításokban. A TMDB-ből érkező leírások nyelve a `TMDB_LANG` környezeti változóval határozható meg.
- **Előzmények importálása, Nuvio-integrációval:** Beemelheted a profilodat közvetlenül a Nuvióból (akár csak az új tételek hozzáadásával, akár a meglévők frissítésével), titkosított hitelesítő adatokkal és automatikus ütemezéssel. A szinkronizáció elérhető a Trakt, SIMKL, MyAnimeList, AniList és Kitsu rendszerekkel is. A Trakt webexport ZIP is importálható ellenőrzéssel és előnézettel. A teljes gyűjteményedet bármikor exportálhatod vagy importálhatod CSV formátumban, emellett feldolgozhatók az IMDb, Goodreads, Steam és HowLongToBeat listái is.
- **Beépített lejátszáskövető (Scrobbler Nuvio és médiaszerverek számára):** A MediaTrail közvetlenül magában foglalja a Stremio protokollját támogató kiegészítő-végpontot, amely külső segédkonténer nélkül fogadja a lejátszási eseményeket a támogatott társalkalmazásokból. Élő „Most nézem” sávokat jelenít meg a kezdőlapon, és a megtekintés végén automatikusan rögzíti a befejezést. A Jellyfin, Plex és Emby szerverek webhookokon keresztül csatlakoztathatók.
- **Korszerű REST API (előzetes változat):** Teljes értékű REST API a `/api/v1/`, OpenAPI séma a `/api/schema/`, és interaktív Swagger dokumentáció a `/api/docs/` címen. Részletes útmutató: [API_HU.md](API_HU.md) ([English](API.md)).
- **Egyetlen, önálló konténer:** Azonnal futtatható Docker Compose konfiguráció beépített Redis-kiszolgálóval. Minden adat egyetlen csatolt mappában (`db`) marad a szervereden.

---

## Előnézet: „Most nézem” és a beépített lejátszáskövető

A MediaTrail egy beépített, Stremio-protokollú scrobbler szolgáltatást tartalmaz. **Fontos megjegyezni, hogy nem tárol és nem streamel médiatartalmakat, valamint nem nyújt saját katalógust sem.** Egyszerű, megbízható eseményfogadóként működik: figyeli a lejátszókból érkező állapotváltozásokat (`start`, `pause`, `progress`, `stop`), és ezek alapján valós időben frissíti a kezdőlapodat.

Minden egyes csatlakoztatott eszköz (telefonok és tetszőleges számú televízió) saját, elkülönített sávot kap a kezdőlapon, így az egyidejű lejátszások soha nem írják felül egymást:

![Now Watching Banner](docs/screenshots/now-watching-desktop.png)

*(Kisebb kijelzőkön vagy keskenyebb ablakban kompakt formátumban is megjelenik)*

![Now Watching Compact](docs/screenshots/now-watching-narrow.png)

A sávok jól láthatóan a kezdőlapod legfelső részén helyezkednek el:

![A Most nézem sáv a kezdőlapon](docs/screenshots/now-watching-desktop2.png)

### Hogyan működik a lejátszáskövetés?

- **Szükséges társalkalmazások:** Mivel a hivatalos Nuvio alkalmazások nem küldenek lejátszási eseményeket, a folyamatos követéshez a kifejezetten erre a célra felkészített klienseink szükségesek: a **[NuvioTV-MT](https://github.com/aicon/NuvioTV-MT)** (Android TV) és a **[NuvioMobile-MT](https://github.com/aicon/NuvioMobile-MT)** (Android telefon és táblagép).
- **Nincs szükség plusz konténerekre:** A követőmodul közvetlenül a MediaTrail belsejében fut, így nem kell semmilyen külön hídalkalmazást vagy segédkonténert üzemeltetned.
- **Egyszerű beállítás:** Mindössze annyi a teendőd, hogy kimásolod a MediaTrail kiegészítőd manifest hivatkozását, és beilleszted a társalkalmazásban a **Beállítások → Bővítmények** menüpont alatt.
- **Több eszköz teljes elkülönítése:** Minden kliens egyedi, stabil `deviceId` azonosítót küld a csatlakozáskor, egy automatikus megnevezéssel kiegészítve (például `TV · Shield` vagy `telefon · Pixel 8`).
- **Egyedi elnevezések:** A sávok nevét közvetlenül a kezdőlapon bármikor átírhatod; a megadott egyedi név a lejátszás leállítása vagy a sáv bezárása után is megmarad.
- **Befejezés a lejátszás leállításakor:** Amikor a kliens leállítási (`stop`) eseményt küld, és az előrehaladás elérte a legalább **90%**-ot, a MediaTrail bejegyzi a befejezett megtekintést az előzményeidbe. A 90%-os határ átlépése folyamatban lévő lejátszás mellett önmagában még nem zárja le a tételt.
- **Gondos időtúllépés-kezelés:** A szüneteltetés és a leállítás kizárólag az adott eszköz sávját érinti. Ha egy lejátszót váratlanul, leállítási esemény küldése nélkül zárnak be, az inaktivitási időzítő egy idő után önműködően eltávolítja a magára hagyott sávot.

---

## Első lépések

A MediaTrail egy könnyen kezelhető, előre beállított Docker konténerként érhető el, amely magában foglalja a belső Redis-szolgáltatást is.

### Docker Compose

Hozz létre egy `docker-compose.yml` fájlt az alábbi tartalommal:

```yaml
services:
  mediatrail:
    image: ghcr.io/aicon/mediatrail:latest
    container_name: mediatrail
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      SECRET: hosszu-veletlenszeru-karaktersor
      TMDB_LANG: hu
      TMDB_API:
      TVDB_API:
      URLS:
      ADMIN_ENABLED: false
      REGISTRATION: false
    volumes:
      - ./db:/mediatrail/db
```

### A környezeti változók testreszabása

Nyisd meg a konfigurációs fájlt, és a példaként megadott kulcs helyére írj be egy saját értéket:

```text
SECRET=hosszu-veletlenszeru-karaktersor
```

A `SECRET` kulcshoz válassz egy biztonságos, hosszú és véletlenszerű karaktersorozatot. Amennyiben a MediaTrailt fordított proxy (reverse proxy) mögött futtatod, a `URLS` változóban add meg a nyilvános webcímedet:

```text
URLS=https://mediatrail.pelda.hu
```

A megadott címnek minden esetben tartalmaznia kell a protokollt (`https://` vagy `http://`), záró perjel vagy almappa-útvonal nélkül. Több domain esetén az értékeket vesszővel választhatod el.

A támogatott beállítások részletes leírását a kézikönyv [Környezet](https://aicon.github.io/mediatrail-docs/hu/runtime/) fejezetében találod.

Indítsd el a konténert:

```bash
docker compose up -d
```

Ezt követően nyisd meg a böngésződben a `http://localhost:8000` címet.

> **Tudnivaló Yamtrackről történő áttérés esetén:**  
> A MediaTrail belső tárolási útvonala `/mediatrail/db` (a korábbi `/yamtrack/db` helyett). Elegendő a meglévő helyi adatkönyvtáradat a fenti módon becsatolnod: `./db:/mediatrail/db`.

---

## A MediaTrail és a Yamtrack viszonya

A MediaTrail egy független, nem hivatalos leágazás; **nem áll kapcsolatban az eredeti Yamtrack fejlesztőivel, és nem annak hivatalos támogatásával működik**.

### Háttér és célkitűzések
A MediaTrail fejlesztése a Yamtrack `dev` ágából indult a `v0.25.3` kiadást követően (konkrétan a 2026. július 12-i, fülekkel ellátott részletes adatlap állapotából), beépítve a `#1378`-as számú REST API előzetest és a `#1608`-as epizód-előzménykezelést.

A MediaTrail a `0.25.x` vonalon folytatódik, a stabilitást, az önálló üzemeltethetőséget és a saját integrációkat (Nuvio, napló, statisztikák, importeszközök) helyezve előtérbe.

| Funkció | Eredeti Yamtrack (Stabil) | MediaTrail |
| :--- | :---: | :---: |
| **REST API** (`/api/v1/`) | Nincs | Van |
| **Többszöri epizód-megtekintési előzmények** | Nincs | Van |
| **Beépített Scrobbler és többeszközös „Most nézem”** | Nincs | Van |
| **Nuvio szinkronizáció és import** | Nincs | Van |
| **Magyar nyelvű kezelőfelület** | Nincs | Van |
| **Beépített belső Redis-kiszolgáló** | Nincs *(külön szolgáltatást igényel)* | Van *(a konténer része)* |
| **Belső Python csomagnév** | `yamtrack` | `yamtrack` *(a kompatibilitás megőrzéséért)* |

---

## Kapcsolódó alkalmazások

A MediaTrail a kifejezetten hozzá fejlesztett társalkalmazásokra támaszkodik a lejátszási események valós idejű rögzítéséhez és a beépített scrobbler kiszolgálásához:

| Alkalmazás | Leírás |
| :--- | :--- |
| **[NuvioTV-MT](https://github.com/aicon/NuvioTV-MT)** | Android TV / Google TV kliens közvetlen MediaTrail scrobbler-támogatással. |
| **[NuvioMobile-MT](https://github.com/aicon/NuvioMobile-MT)** | Android telefonos és táblagépes kliens közvetlen MediaTrail scrobbler-támogatással. |

---

## Részletes dokumentáció

A részletes felhasználói kézikönyv, a telepítési útmutató és a konfigurációs példák a hivatalos dokumentációs tárban találhatók:

- **Kézikönyv:** [https://aicon.github.io/mediatrail-docs/hu/](https://aicon.github.io/mediatrail-docs/hu/)
- **API-dokumentáció:** [API_HU.md](API_HU.md) · [API.md](API.md)

A kézikönyv fejezetei: *Telepítés, Könyvtár, Live playback / Now Watching, Importálás (benne a Nuvio), Környezet és konfiguráció, Fiókok, Karbantartás és üzemeltetés.*

---

## Támogatás

Ha elnyerte a tetszésedet a MediaTrail, és szívesen hozzájárulnál a rendszer karbantartásához és további fejlesztéséhez:

[![Ko-fi támogatás](https://img.shields.io/badge/Ko--fi-T%C3%A1mogat%C3%A1s-ff5e5b?style=for-the-badge&logo=ko-fi)](https://ko-fi.com/aiconwg)

---

## Licencfeltételek és AGPL-3.0 megfelelőség

A MediaTrail nyílt forráskódú szabad szoftver, amely a **GNU Affero General Public License v3.0 (AGPL-3.0)** alatt áll.  
Az eredeti Yamtrack projekt szerzői jogi jelzéseit mindvégig megőriztük. A MediaTrail saját kiegészítő szerzői jogi nyilatkozata a `NOTICE` fájlban található.

### Hálózati használatra vonatkozó rendelkezés (AGPL-3.0 13. szakasz)
Mivel a MediaTrail egy hálózaton keresztül igénybe vehető, módosított szoftver, az AGPL-3.0 licenc 13. szakasza előírja a futó változat pontos forráskódjának nyilvános felkínálását valamennyi hálózati felhasználó számára:
- Állítsd be a `MEDIATRAIL_SOURCE_URL` környezeti változót a futó verzió nyilvános HTTP(S) forráskód-elérhetőségére, mielőtt a szervert mások számára is elérhetővé tennéd a hálózaton.
- Kizárólag saját gépen futtatott, szigorúan zárt körű telepítés esetén a változó üresen hagyható.
