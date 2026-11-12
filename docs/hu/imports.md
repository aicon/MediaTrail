# Importálás

[English](../imports.md)

A külső szolgáltatásokból származó megtekintési előzményeidet a Beállítások felületén, az Adatimport menüpont alatt emelheted be a gyűjteményedbe. Az oldal tetején található két működési mód valamennyi adatforrásra érvényes:

- **Csak az új elemek:** kizárólag azokat a tételeket rögzíti, amelyek még hiányoznak a helyi adatbázisodból; a meglévő bejegyzéseket változatlanul hagyja.
- **Új elemek és a meglévők felülírása:** a hiányzó elemek felvétele mellett a már meglévő tételek megtekintési dátumát is frissíti a forrás adatai alapján. A személyes pontszámaid és feljegyzéseid mindvégig megmaradnak, és a folyamat egyetlen sort sem töröl.

Az importálást elindíthatod egyszeri alkalommal, vagy ütemezheted a megadott időponttól kezdődő rendszeres ismétlődéssel. Az ütemezett feladat mindaddig periodikusan lefut, amíg el nem távolítod az aktív időzített importok közül. A fájlfeltöltéssel járó import kizárólag egyszer futtatható le, míg a felhasználónévhez vagy elmentett bejelentkezéshez kötött források ütemezhetők.

A források alatt elhelyezkedő előzménytár az elmúlt hét nap feladatait sorolja fel. A folyamatban lévő feladatoknál külön állapotjelzés látható; a sikeresen lezárult feladatok részletes összegzésében pedig megtekintheted azokat a tételeket is, amelyeket a rendszer figyelmen kívül hagyott.

## Nuvio

Az elsődleges adatforrás a Nuvio, amely közvetlenül egy kiválasztott Nuvio-profilhoz tartozó filmeket és epizódokat olvassa be. A kétirányú előzményszinkronizációt a Beállítások → Integrációk → Nuvio menüpontban tetszésed szerint engedélyezheted: a megtekintett, illetve a még nem látott jelölések átvétele helyben érvényesíti a Nuvio változásait, míg amikor a MediaTrailben bejegyzel vagy törölsz valamit, a rendszer automatikusan elindítja a megfelelő szinkronizációs hívásokat (`sync_push_watched_items` / `sync_delete_watched_items`). A kapcsolók bekapcsolása után a MediaTrail kb. **30 másodpercenként** lekéri a Nuvio deltát a háttérben, kb. **15 percenként** pedig teljes előzmény-ellenőrzést is futtat; a kapcsolók mentése azonnali delta-húzást is sorba állít. Egyszerre csak egy szinkron fut fiókonként (az átfedő poll kimarad). Ehhez elég egyszer sikeresen lefuttatnod az Adatimport → Nuvio importot (bootstrap); utána az interaktív jelölésekhez nem kell kézzel importálnod. Az első import a Nuvio delta-kurzort a history-snapshot **előtt** rögzíti, majd a tip utáni eseményeket a deltából húzza — így a lapozás közben változó megtekintések nem esnek ki a snapshot és a kurzor közül.

A társalkalmazásokból érkező valós idejű **„Most nézem”** sáv működése ettől elkülönül: a MediaTrail beépített kiegészítője közvetlenül az eszközökhöz kötött lejátszási eseményeket fogadja. Az előzmények importálása ezeket az élő sávokat nem érinti. Erről bővebben a [Könyvtár](library.md) fejezetben és a [Live playback / Now Watching](../now-watching.md) dokumentumban olvashatsz.

A bejelentkezési adatok, az importálási mutatók (kurzor) és a beemelt sorok szigorúan az adott MediaTrail-felhasználóhoz tartoznak (minden fiókhoz egyetlen `NuvioAccount` rendelhető). Ha ugyanazon a szerveren több felhasználó is tevékenykedik, mindegyikük önálló Nuvio-fiókkal és független gyűjteménnyel rendelkezik.

Az űrlap a Nuvio-fiókhoz tartozó e-mail-címet, a jelszót és a kívánt profilszámot kéri. Az első sikeres hitelesítést követően a rendszer ezeket titkosítva tárolja a MediaTrail-fiókodhoz. A következő látogatáskor az e-mail-cím és a profilszám már előre kitöltve jelenik meg; a jelszómezőt üresen hagyva a rendszer a már elmentett jelszót használja. Új jelszót csak akkor kell megadnod, ha meg szeretnéd változtatni azt. Egy másik e-mail-cím vagy eltérő profilszám megadása az importálási kurzor elölről kezdését eredményezi.

Az importálás során a rendszer az alábbi szabályok szerint jár el:

- A gyűjteményben még nem szereplő filmeket befejezettként veszi fel, a Nuvióban rögzített megtekintési időponttal.
- A hiányzó epizódok ugyanígy kerülnek be; amennyiben a hozzájuk tartozó évad vagy sorozat még nem létezik, a rendszer automatikusan létrehozza azokat.
- A „Csak az új elemek” beállítás mellett a már meglévő filmek és epizódok változatlanok maradnak, megőrizve az általad korábban megadott egyedi dátumokat is.
- A felülírási mód alkalmazásakor a már nyilvántartott filmek, illetve az epizódok legutóbbi megtekintési bejegyzései átveszik a Nuvio szerinti időpontot, a tétel többi adata azonban érintetlen marad.
- Ha egy epizódot törölsz a MediaTrail felületén, ám az a Nuvio előzményeiben továbbra is megtekintettként szerepel, a következő importálás ismét beemeli azt. A „Csak az új elemek” elve ugyanis a helyi hiányt pótolja, függetlenül attól, hogy a tétel korábban már szerepelt-e az adatbázisban.
- Azok a sorozatelemek, amelyek nem tartalmaznak évad- vagy epizódszámot, kimaradnak; a rendszer feljegyzi ezeket, hogy a későbbi futások során ne jelezze őket ismételten hibaként.
- A Nuvióban végzett törléseket a rendszer figyelmen kívül hagyja, kivéve, ha az Integrációk menüpontban bekapcsoltad a **Nem megtekintett jelölés szinkronizálása** lehetőséget. Ekkor a művelet a helyi film- és epizód-előzményekből is eltávolítja a megfelelő tételt.

A megadandó profilszám a Nuvio rendszerében érvényes profilra utal, nem a MediaTrail-fiókra. A fiókok többsége egyetlen, 1-es azonosítójú profillal rendelkezik.

## További adatforrások

Az egyéb források ugyanazokat a működési módokat és ütemezési lehetőségeket használják.

| Forrás | Szükséges adatok | Megjegyzések |
| --- | --- | --- |
| Trakt | Nyilvános felhasználónév, zárt API-bejelentkezés (böngészős PKCE az `auth.trakt.tv`-n, vagy eszközkód), vagy webhelyes export ZIP | A zárt belépéshez `TRAKT_API_PKCE` kell (modern Trakt-alkalmazás, secret nélkül). Az eszközkód TV-khez és korlátozott bevitelű eszközökhöz megmarad. A ZIP a Trakt → Beállítások → Export menüből jön (legfeljebb 50 MB). Sérült vagy üres archívumot az import elindítása előtt elutasít a rendszer. A „Csak az új elemek” kihagyja a már meglevő címeket. |
| Simkl | Közvetlen összekapcsolás gombbal | Üzemeltetői kulcs kell: új AUTH V2 alkalmazás a [simkl.com/settings/developer](https://simkl.com/settings/developer/) oldalon (V1 azonosító nem frissíthető). Ajánlott: **Server apps & services**, `SIMKL_V2_ID` / `SIMKL_V2_SECRET`, redirect `{URLS}/import/simkl_private`. Lépések: [Környezet → Simkl AUTH V2](runtime.md#simkl-auth-v2-kulcsok-beszerzese-es-kapcsolas). A V1 tokenek ~2027. áprilisig élnek; V2 után kapcsolódj újra. |
| MyAnimeList | Nyilvános felhasználónév | |
| AniList | Nyilvános felhasználónév, vagy közvetlen összekapcsolás | Zárt profil eléréséhez saját AniList-alkalmazás regisztrációja szükséges. |
| Kitsu | A profil hivatkozásában szereplő numerikus azonosító | |
| Steam | A 64 bites Steam-azonosító | A profilnak nyilvánosnak kell lennie, kivéve, ha az API-kulcs közvetlenül az adott fiókhoz tartozik. |
| MediaTrail biztonsági mentés | A Beállítások → Adatexport menüből származó CSV-fájl | Kizárólag egyszeri importként használható. |
| HowLongToBeat | CSV-exportfájl | Kizárólag egyszeri importként, videojátékokhoz használható. |
| IMDb | Értékeléseket tartalmazó CSV-fájl | Kizárólag egyszeri importként használható. |
| Goodreads | Gyűjteményexport CSV-formátumban | Kizárólag egyszeri importként, könyvekhez használható. |

A tételek párosítása azoknak a katalógusazonosítóknak az alapján történik, amelyeket a MediaTrail alapértelmezés szerint nyilvántart. Ha egy cím a katalógusokban nem azonosítható, az a feladat összegzésében jelenik meg, és a rendszer nem hoz létre hozzá pontatlan, fiktív bejegyzést.

## Médialejátszók

A Jellyfin, a Plex és az Emby szerverek webhookokon keresztül képesek értesíteni a MediaTrailt a lejátszási eseményekről. A Beállítások → Integrációk oldalon valamennyi támogatott lejátszóhoz megtalálod a hozzárendelt webhook-címet, amely magában foglalja a személyes hitelesítési tokenedet is. Az oldalon lépésről lépésre követhető útmutatót találsz a lejátszók beállításához. Amennyiben a Beállításokban új személyes tokent kérsz, ezek a webhook-címek is megváltoznak, így azokat a külső programokban is frissítened kell.
