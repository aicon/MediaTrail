# Környezet és konfiguráció

[English](../runtime.md)

Az alábbi paraméterek a konténer környezeti változói, amelyeket nem a webes Beállítások felületén, hanem a Docker Compose konfigurációban kell megadnod, majd a konténert újra létrehoznod. A bizalmas kulcsok és jelszavak fájlútvonalként is átadhatók: a `_FILE` végződésű változók (például `SECRET_FILE`) egy olyan fájlra mutatnak, amelynek tartalma adja meg a tényleges értéket – a Docker secrets mechanizmusa is ezen az elven működik.

Ezeket az értékeket soha ne ágyazd be a lemezkép építési folyamatába. A konténerkép magát a programot testesíti meg, míg a hitelesítési kulcsok és adatok biztonságosan azon a kiszolgálón maradnak, amely a rendszert futtatja.

A függőségi és reverse-proxy keményítés részletei (Pillow/Brotli ellenőrzés, pinelt Alpine csomagok, `TRUSTED_PROXIES`) a [MediaTrail biztonsági jegyzetek](https://github.com/aicon/MediaTrail/blob/main/docs/hu/security.md) oldalon találhatók.

## Gyakran használt alapbeállítások

| Változó | Szerepe és rendeltetése |
| --- | --- |
| `SECRET` | A munkamenetek hitelesítésére és az adatok titkosítására szolgáló kulcs. Célszerű egy hosszú, véletlenszerű karaktersorozatot megadnod, mielőtt az oldalt mások számára elérhetővé tennéd. |
| `TZ` | Az időzóna neve (például `Europe/Budapest`). A rendszer ebben az időzónában jeleníti meg a rögzített időpontokat. |
| `URLS` | A rendszer nyilvános webcímei vesszővel elválasztva, a `http://` vagy `https://` előtaggal, záró perjel nélkül. Fordított proxy mögött kötelezően megadandó. |
| `TRUSTED_PROXIES` | Opcionális. A felső szintű fordított proxyk IP-címei vagy CIDR-hálózatai vesszővel elválasztva (például `192.168.1.0/24,10.0.0.5`). Beállítva az nginx csak ezektől a proxyktól fogadja az `X-Forwarded-For` fejlécet. Üresen hagyva a korábbi viselkedés marad. |
| `ALLOWED_HOSTS` | Azok a hosztnevek és domainek, amelyekre a szerver válaszol. Alapértelmezett értéke `*`. Ha egyedi listát adsz meg, a `localhost` és a `127.0.0.1` automatikusan a listához adódik. |
| `PUID` és `PGID` | A tárolt adatokat őrző `db` mappa tulajdonosi felhasználói és csoportazonosítója. Alapértelmezett értéke `1000`. |
| `MEDIATRAIL_SOURCE_URL` | A futó változat pontos forráskódjának nyilvános `http` vagy `https` elérhetősége. Kötelező megadnod, ha más felhasználók is elérik az oldalt. |
| `REGISTRATION` | `True` esetén a nyilvános regisztráció engedélyezett; a `False` érték lezárja a regisztrációs felületet. |
| `ADMIN_ENABLED` | `True` esetén elérhetővé teszi a `/admin/` felületet; amíg nem állítod be, biztonsági okokból ki van kapcsolva. |

A `DEBUG` változó értéke nyilvánosan vagy több felhasználó által elérhető szerveren mindig maradjon `False`.

## Adatbázis-beállítások

Külön adatbázis-kiszolgáló hiányában a MediaTrail a beépített SQLite adatbázist használja, amely a csatolt adatkönyvtárban, a `db/db.sqlite3` fájlban tárolódik. A konténerben futó Redis a saját perzisztens fájljait a `db/redis` mappa alatt őrzi.

A `DB_HOST` változó beállításával a rendszer PostgreSQL adatbázisra vált. Ebben az esetben a `DB_PORT`, `DB_NAME`, `DB_USER` és `DB_PASSWORD` értékeket is meg kell adnod. A `DB_SSL_MODE` és `DB_SSL_CERT_MODE` beállítások nem kötelezők, és a PostgreSQL hivatalos kapcsolati elnevezéseit követik.

A `REDIS_URL` alapértelmezés szerint a konténerbe épített Redisre mutat (`redis://127.0.0.1:6379`). Ezt kizárólag akkor szükséges felülbírálnod, ha szándékosan egy külső Redis-kiszolgálót szeretnél használni. A `CELERY_REDIS_URL` önállóan képes felülírni a háttérfeladatokat kezelő üzenetsor közvetítőjét. A `REDIS_PREFIX` segítségével előtag adható a gyorsítótár-kulcsoknak, amennyiben több alkalmazás osztozik egyazon Redis-példányon.

## Katalógusok API-kulcsai

A filmek, sorozatok, animék, videojátékok, könyvek, képregények és társasjátékok keresése alapértelmezés szerint a programba épített klienskulcsokkal történik. Kulcscserére akkor lehet szükség, ha saját lekérdezési keretet szeretnél fenntartani, vagy ha a szolgáltató ezt előírja. Ha egy változót üresen hagysz, a beépített kliens marad érvényben. A saját kulcsaidat soha ne illeszd be se a konténerképbe, se ebbe a kézikönyvbe.

| Változó | Szolgáltató |
| --- | --- |
| `TMDB_API` | Filmek és sorozatok metaadatai. A `TMDB_LANG` a leírások nyelvét határozza meg (alapértelmezése `en`). A `TMDB_NSFW` értéke `True` esetén a felnőtt besorolású találatokat is megjeleníti. |
| `TVDB_API` | Kiegészítő metaadatok televíziós sorozatokhoz. |
| `MAL_API` | MyAnimeList adatok. A `MAL_NSFW` értéke `True` esetén a felnőtt tartalmakat is lekéri. |
| `IGDB_ID` és `IGDB_SECRET` | Videojátékok metaadatai. Az `IGDB_NSFW` a felnőtt tartalmak engedélyezésére szolgál. |
| `STEAM_API_KEY` | A Steam áruházból származó adatok (beépített kulcs nem áll rendelkezésre). |
| `HARDCOVER_API` | Könyvek metaadatai. Az értéknek a `Bearer ` előtaggal és egy szóközzel kell kezdődnie. |
| `COMICVINE_API` | Képregények adatai. |
| `BGG_API_TOKEN` | BoardGameGeek társasjáték-adatok. |
| `TRAKT_API` | Trakt API-kulcs a nyilvános / legacy hívások `trakt-api-key` fejlécéhez. |
| `TRAKT_API_SECRET` | Csak a régi, secret-es ügyféllel létrehozott ütemezett importok tokenfrissítéséhez kell. Az új belépések nem használják. |
| `TRAKT_API_PKCE` | Modern Trakt-alkalmazás ügyfélazonosítója (nincs secret). Böngészős PKCE-belépéshez (`auth.trakt.tv`) és eszközkódos belépéshez. Az alkalmazásnál állítsd be a MediaTrail callback URL-t (`…/import/trakt/private`). Az ingyenes Trakt-fiókok legfeljebb két csatlakoztatott alkalmazást engedélyeznek. |
| `ANILIST_ID` és `ANILIST_SECRET` | Saját AniList-alkalmazás zárt profilok eléréséhez. |
| `SIMKL_ID` és `SIMKL_SECRET` | Simkl AUTH V1 alkalmazás (elavult; tervezett kivezetés ~2027. április). Meglévő V1 tokenekhez és V2 nélküli tartalékként. A V1 `client_id` **nem** frissíthető V2-re. |
| `SIMKL_V2_ID` | Simkl AUTH V2 ügyfélazonosító az új kapcsolásokhoz (PKCE). Callback: `…/import/simkl_private`. |
| `SIMKL_V2_SECRET` | V2 titok, ha a Simkl alkalmazástípus **Server apps & services** (ehhez a típushoz kötelező). Nyilvános kliensnél hagyd üresen. Ne kerüljön a repóba; inkább `*_FILE`. |

### Simkl AUTH V2: kulcsok beszerzése és kapcsolás

A MediaTrail a visszatérő OAuth-hívást és a token cseréjét a te szervereden intézi. Új AUTH V2 alkalmazást regisztrálj; a V1 hitelesítő adatok nem működnek a `/oauth2/*` végpontokon.

1. Jelentkezz be a [simkl.com](https://simkl.com)-ra, majd nyisd meg a [Fejlesztői beállításokat](https://simkl.com/settings/developer/).
2. Hozz létre **új** (V2) alkalmazást. A kliens típusa a regisztrációnál rögzül:
   - **Server apps & services** — a MediaTrailhez ajánlott. Kapod a `client_id`-t és egyszer a `client_secret`-et. Állítsd be a `SIMKL_V2_ID` és a `SIMKL_V2_SECRET` értékeket.
   - **Mobile, desktop & browser apps** — nyilvános kliens, nincs secret. Csak a `SIMKL_V2_ID` kell; a MediaTrail így is S256 PKCE-t használ.
   - Az Import gombhoz **ne** válaszd a **TV, devices & command line** típust (nincs redirect URI).
3. Add meg a redirect URI-t pontosan így: `{URLS}/import/simkl_private`  
   Példa: ha `URLS=https://mediatrail.pelda.hu`, akkor `https://mediatrail.pelda.hu/import/simkl_private` (séma, hoszt, port, útvonal; a `URLS`-ön nincs záró perjel).
4. Írd be a Compose / `.env` fájlba, majd hozd létre újra a konténert:

```text
SIMKL_V2_ID=sajat-v2-ugyfelazonosito
SIMKL_V2_SECRET=sajat-v2-titok
# Vagy fájlból:
# SIMKL_V2_ID_FILE=/run/secrets/simkl_v2_id
# SIMKL_V2_SECRET_FILE=/run/secrets/simkl_v2_secret
```

5. Az **Import → Simkl összekapcsolás** gombbal, ha van `SIMKL_V2_ID`, a MediaTrail a `https://simkl.com/oauth2/authorize` címet nyitja (PKCE), titkosított **refresh** tokent tárol, és `auth=v2` mellett ütemez.
6. V2 bekapcsolása után egyszer kapcsolódj újra, hogy az ütemezett feladatok ne V1-only access tokenre támaszkodjanak.

`SIMKL_V2_ID` nélkül a rendszer AUTH V1-re esik vissza (`/oauth/authorize`) és access tokent tárol. A V1 a tervezett ~2027. áprilisi kivezetésig marad. Hivatalos Simkl referencia: [AUTH V2 áttekintés](https://api.simkl.org/api-reference/auth-v2) és [alkalmazás regisztrálása](https://docs.simkl.org/how-to-use-simkl/for-developers/how-to-register-an-app).

A `MU_NSFW` a MangaUpdates felnőtt tartalmú szűrőjének kapcsolója.

## Külső fiókkal történő hitelesítés (SSO / OAuth)

A `SOCIAL_PROVIDERS` a django-allauth szolgáltatói moduljainak vesszővel elválasztott listája (például `allauth.socialaccount.providers.github`). A `SOCIALACCOUNT_PROVIDERS` egy JSON-objektum, amely az adott szolgáltatóhoz tartozó ügyfélazonosítót, titkos kulcsot és az egyéb szükséges paramétereket foglalja magában.

A `SOCIALACCOUNT_ONLY` változó `True` értékre állításával elrejtheted a hagyományos jelszavas belépést. A `REDIRECT_LOGIN_TO_SSO=True` beállítás a bejelentkezési oldalt közvetlenül a külső hitelesítő szolgáltatóhoz irányítja át.

A külső szolgáltatónál rögzített visszairányítási címnek a MediaTrail nyilvános domainjéből és a szolgáltató által elvárt végpontból kell állnia. A `URLS` változónak pontosan ezzel a nyilvános címmel kell megegyeznie, különben a hitelesítés után visszatérő kérést a rendszer érvénytelennek minősíti és elutasítja.

## A „Most nézem” sáv inaktivitási időkorlátjai

A társalkalmazások a beépített MediaTrail kiegészítőn keresztül frissítik az élő lejátszási sávokat. Az elmaradt leállítási (`stop`) események kezelésére az alábbi opcionális időkorlátok szolgálnak (a legtöbb környezetben a gyári értékek maradéktalanul megfelelnek):

| Változó | Alapérték | Szerepe és feladata |
| --- | --- | --- |
| `LIVE_PLAYBACK_WATCHING_STALE_SECONDS` | `180` | Az előrehaladás nélküli, aktív lejátszású (`watching`) sáv ennyi másodperc inaktivitás után automatikusan törlődik. |
| `LIVE_PLAYBACK_PAUSED_STALE_SECONDS` | `600` | A szüneteltetett állapotban hagyott (`paused`) sáv ennyi másodperc elteltével automatikusan törlődik. |

Részletes információk: [Live playback / Now Watching](../now-watching.md).
