# Környezet

[English](../runtime.md)

Ezek a konténer környezeti változói. Nem a Beállítások oldal. A Compose-fájlban kell őket módosítani, utána a konténert újra kell létrehozni. Egy titok fájlútvonal is lehet: a `VALAMI_FILE` változó arra a fájlra mutat, amelynek a tartalma az érték. A Docker-titkok így olvashatók.

Ezek az értékek ne kerüljenek a kép építésébe. A kép a program. A kulcsok azon a gépen maradnak, amely futtatja.

## Amit általában be kell állítani

| Változó | Szerepe |
| --- | --- |
| `SECRET` | Munkamenet- és titkosítókulcs. Hosszú, véletlen érték, mielőtt az oldalt más is eléri. |
| `TZ` | Időzóna neve, például `Europe/Budapest`. A megjelenített dátumok ezt használják. |
| `URLS` | Nyilvános címek, vesszővel elválasztva, `http://` vagy `https://` előtaggal, záró perjel nélkül. Közvetítő mögött kötelező. |
| `ALLOWED_HOSTS` | Azok a gépnevek, amelyekre az oldal válaszol. Az alapértelmezés `*`. Ha listát adsz meg, a `localhost` és a `127.0.0.1` akkor is hozzáadódik. |
| `PUID` és `PGID` | A `db` könyvtár tulajdonosának felhasználója és csoportja. Az alapértelmezés `1000`. |
| `MEDIATRAIL_SOURCE_URL` | A futó verzió pontos forrásának nyilvános `http` vagy `https` címe. Kötelező, ha mások is használják az oldalt. |
| `REGISTRATION` | `True` esetén új fiók létrehozható. `False` lezárja a regisztrációs oldalt. |
| `ADMIN_ENABLED` | `True` bekapcsolja a `/admin/` címet. Amíg nem állítod be, ki van kapcsolva. |

A `DEBUG` maradjon `False`, ha a gépet más is eléri.

## Adatbázis

Adatbázis-gép nélkül a MediaTrail SQLite-ot használ, a csatolt adatkönyvtár `db/db.sqlite3` fájljában. A képben lévő Redis a fájlját a `db/redis` alatt tartja.

A `DB_HOST` beállítása PostgreSQL-re vált. Mellé kell a `DB_PORT`, a `DB_NAME`, a `DB_USER` és a `DB_PASSWORD`. A `DB_SSL_MODE` és a `DB_SSL_CERT_MODE` nem kötelező, és a PostgreSQL saját elnevezését használja erre a két kapcsolati beállításra.

A `REDIS_URL` alapból a képben lévő Redis, `redis://127.0.0.1:6379`. Csak akkor állítsd, ha szándékosan másik Redisre mutatsz. A `CELERY_REDIS_URL` külön felülírja a háttérfeladat közvetítőjét. A `REDIS_PREFIX` a gyorsítótár kulcsait előtagozza, ha két alkalmazás egy Redist használ.

## Katalóguskulcsok

A film, a sorozat, az anime, a játék, a könyv, a képregény és a társasjáték keresése a programban lévő klienskulcsokkal működik. Kulcsot akkor cserélj, ha saját keretet akarsz, vagy ha a szolgáltató ezt kéri. Ha egy kulcsot nem adsz meg, a beépített kliens marad. Kulcsot ne másolj a képbe, és ebbe a könyvbe se.

| Változó | Szolgáltató |
| --- | --- |
| `TMDB_API` | Filmek és sorozatok. A `TMDB_LANG` a metaadat nyelve, alapból `en`. A `TMDB_NSFW` `True` értéknél a felnőtt találatokat is kéri. |
| `TVDB_API` | További sorozatadatok. |
| `MAL_API` | MyAnimeList. A `MAL_NSFW` `True` értéknél a felnőtt találatokat is kéri. |
| `IGDB_ID` és `IGDB_SECRET` | Játékok. Az `IGDB_NSFW` `True` értéknél. |
| `STEAM_API_KEY` | Steam-áruházi adatok. Beépített kulcs nincs. |
| `HARDCOVER_API` | Könyvek. Az értéknek a `Bearer` szóval és egy szóközzel kell kezdődnie. |
| `COMICVINE_API` | Képregények. |
| `BGG_API_TOKEN` | Társasjátékok. |
| `TRAKT_API` és `TRAKT_API_SECRET` | Saját Trakt-alkalmazás, zárt importhoz vagy saját kerethez. |
| `ANILIST_ID` és `ANILIST_SECRET` | Saját AniList-alkalmazás, zárt importhoz. |
| `SIMKL_ID` és `SIMKL_SECRET` | Saját Simkl-alkalmazás. |

A `MU_NSFW` a MangaUpdates felnőtt tartalmának kapcsolója.

## Belépés másik oldalon keresztül

A `SOCIAL_PROVIDERS` a django-allauth szolgáltatómoduljainak vesszővel elválasztott listája, például `allauth.socialaccount.providers.github`. A `SOCIALACCOUNT_PROVIDERS` JSON-objektum: a szolgáltató kliensazonosítója, titka, és amit a szolgáltató dokumentációja még kér.

A `SOCIALACCOUNT_ONLY` `True` értéke elrejti a jelszavas belépést. A `REDIRECT_LOGIN_TO_SSO` `True` értéke a belépőoldalt egyből a külső szolgáltatóhoz küldi.

A szolgáltatónál regisztrált visszairányítási cím a MediaTrail nyilvános címe, plusz az az útvonal, amelyet a szolgáltató vár. A `URLS` ugyanaz a cím legyen, különben a visszaút elutasításra kerül.
