# Környezet és konfiguráció

[English](../runtime.md)

Az alábbi paraméterek a konténer környezeti változói, amelyeket nem a webes Beállítások felületén, hanem a Docker Compose konfigurációban kell megadni, majd a konténert újra létrehozni. A bizalmas kulcsok és jelszavak fájlútvonalként is átadhatók: a `_FILE` végződésű változók (például `SECRET_FILE`) egy olyan fájlra mutatnak, amelynek tartalma adja meg a tényleges értéket – a Docker secrets mechanizmusa is ezen az elven működik.

Ezeket az értékeket soha ne ágyazza be a lemezkép fordítási folyamatába. A konténerkép magát a programot testesíti meg, míg a hitelesítési kulcsok és titkok biztonságosan azon a kiszolgálón maradnak, amely a rendszert futtatja.

## Gyakran használt alapbeállítások

| Változó | Szerepe és rendeltetése |
| --- | --- |
| `SECRET` | A munkamenetek hitelesítésére és az adatok titkosítására szolgáló kulcs. Célszerű egy hosszú, véletlenszerű karaktersorozatot megadni, mielőtt az oldalt mások számára elérhetővé tenné. |
| `TZ` | Az időzóna neve (például `Europe/Budapest`). A rendszer ebben az időzónában jeleníti meg a rögzített időpontokat. |
| `URLS` | A rendszer nyilvános webcímei vesszővel elválasztva, a `http://` vagy `https://` előtaggal, záró perjel nélkül. Fordított proxy mögött kötelezően megadandó. |
| `ALLOWED_HOSTS` | Azok a hosztnevek és domainek, amelyekre a szerver válaszol. Alapértelmezett értéke `*`. Egyedi lista megadásakor a `localhost` és a `127.0.0.1` automatikusan a listához adódik. |
| `PUID` és `PGID` | A tárolt adatokat őrző `db` mappa tulajdonosi felhasználói és csoportazonosítója. Alapértelmezett értéke `1000`. |
| `MEDIATRAIL_SOURCE_URL` | A futó változat pontos forráskódjának nyilvános `http` vagy `https` elérhetősége. Kötelező megadni, amennyiben az oldalt más felhasználók is elérik. |
| `REGISTRATION` | `True` esetén a nyilvános regisztráció engedélyezett; a `False` érték lezárja a regisztrációs felületet. |
| `ADMIN_ENABLED` | `True` esetén elérhetővé teszi a `/admin/` felületet; alapértelmezés szerint biztonsági okokból ki van kapcsolva. |

A `DEBUG` változó értéke nyilvánosan vagy több felhasználó által elérhető szerveren mindig maradjon `False`.

## Adatbázis-beállítások

Külön adatbázis-kiszolgáló hiányában a MediaTrail a beépített SQLite adatbázist használja, amely a csatolt adatkönyvtárban, a `db/db.sqlite3` fájlban tárolódik. A konténerben futó Redis a saját perzisztens fájljait a `db/redis` mappa alatt őrzi.

A `DB_HOST` változó beállításával a rendszer PostgreSQL adatbázisra vált. Ebben az esetben a `DB_PORT`, `DB_NAME`, `DB_USER` és `DB_PASSWORD` értékeket is meg kell adni. A `DB_SSL_MODE` és `DB_SSL_CERT_MODE` beállítások nem kötelezők, és a PostgreSQL hivatalos kapcsolati elnevezéseit követik.

A `REDIS_URL` alapértelmezés szerint a konténerbe épített Redisre mutat (`redis://127.0.0.1:6379`). Ezt kizárólag akkor szükséges felülbírálni, ha szándékosan egy külső Redis-kiszolgálót szeretne használni. A `CELERY_REDIS_URL` önállóan képes felülírni a háttérfeladatokat kezelő üzenetsor közvetítőjét. A `REDIS_PREFIX` segítségével előtag adható a gyorsítótár-kulcsoknak, amennyiben több alkalmazás osztozik egyazon Redis-példányon.

## Katalógusok API-kulcsai

A filmek, sorozatok, animék, videojátékok, könyvek, képregények és társasjátékok keresése alapértelmezés szerint a programba épített klienskulcsokkal történik. Kulcscserére akkor lehet szükség, ha saját lekérdezési kvótát szeretne fenntartani, vagy ha a szolgáltató ezt előírja. Ha egy változót üresen hagy, a beépített kliens marad érvényben. Saját kulcsait soha ne illessze be se a konténerképbe, se ebbe a kézikönyvbe.

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
| `TRAKT_API` és `TRAKT_API_SECRET` | Saját Trakt-alkalmazás zárt profilok importálásához vagy saját lekérdezési kerethez. |
| `TRAKT_API_PKCE` | Új típusú Trakt-alkalmazás ügyfélazonosítója (Client ID). Az ilyen alkalmazások nem igényelnek titkos kulcsot; az importáló oldal ezt eszközkódos belépésként kínálja fel. Az ingyenes Trakt-fiókok legfeljebb két csatlakoztatott alkalmazást engedélyeznek. |
| `ANILIST_ID` és `ANILIST_SECRET` | Saját AniList-alkalmazás zárt profilok eléréséhez. |
| `SIMKL_ID` és `SIMKL_SECRET` | Saját Simkl-alkalmazás beállításai. |

A `MU_NSFW` a MangaUpdates felnőtt tartalmú szűrőjének kapcsolója.

## Külső fiókkal történő hitelesítés (SSO / OAuth)

A `SOCIAL_PROVIDERS` a django-allauth szolgáltatói moduljainak vesszővel elválasztott listája (például `allauth.socialaccount.providers.github`). A `SOCIALACCOUNT_PROVIDERS` egy JSON-objektum, amely az adott szolgáltatóhoz tartozó ügyfélazonosítót, titkos kulcsot és az egyéb szükséges paramétereket foglalja magában.

A `SOCIALACCOUNT_ONLY` változó `True` értékre állításával elrejthető a hagyományos jelszavas belépés. A `REDIRECT_LOGIN_TO_SSO=True` beállítás a bejelentkezési oldalt közvetlenül a külső hitelesítő szolgáltatóhoz irányítja át.

A külső szolgáltatónál rögzített visszairányítási címnek a MediaTrail nyilvános domainjéből és a szolgáltató által elvárt végpontból kell állnia. A `URLS` változónak pontosan ezzel a nyilvános címmel kell megegyeznie, különben a hitelesítés után visszatérő kérést a rendszer érvénytelennek minősíti és elutasítja.

## A „Most nézem” sáv inaktivitási időkorlátjai

A társalkalmazások a beépített MediaTrail kiegészítőn keresztül frissítik az élő lejátszási sávokat. Az elmaradt leállítási (`stop`) események kezelésére az alábbi opcionális időkorlátok szolgálnak (a legtöbb környezetben a gyári értékek maradéktalanul megfelelnek):

| Változó | Alapérték | Szerepe és feladata |
| --- | --- | --- |
| `LIVE_PLAYBACK_WATCHING_STALE_SECONDS` | `180` | Az előrehaladás nélküli, aktív lejátszású (`watching`) sáv ennyi másodperc inaktivitás után automatikusan törlődik. |
| `LIVE_PLAYBACK_PAUSED_STALE_SECONDS` | `600` | A szüneteltetett állapotban hagyott (`paused`) sáv ennyi másodperc elteltével automatikusan törlődik. |

Részletes információk: [Live playback / Now Watching](../LIVE_PLAYBACK_NOW_WATCHING.md).
