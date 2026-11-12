# Könyvtár

[English](../library.md)

A gyűjtemény a kezdőlapon és az oldalsávon keresztül érhető el. A filmek, sorozatok, évadok és egyéb médiatípusok mind saját listával rendelkeznek. A listák keresőmezője a bejelentkezett felhasználó saját tételei között böngészik.

Lejátszás vagy szüneteltetés közben a kezdőlap tetején megjelennek a dinamikus **„Most nézem”** sávok – minden kapcsolódó eszközhöz (telefonhoz vagy különálló televízióhoz) egy-egy önálló sáv. A panelen látható a mű címe, az epizód száma, a megtekintett hányad, a hátralévő idő, valamint a tetszés szerint átnevezhető eszköznév. Ha egy adott eszközön leállítjuk a lejátszást vagy elrejtjük a sávot, az a többi készülék kijelzését nem érinti. Amikor a társalkalmazás leállítási (`stop`) eseményt küld, és az előrehaladás elérte a legalább **90%**-ot, a MediaTrail kiegészítője automatikusan egy befejezett megtekintést rögzít a naplóba. Az alábbi illusztráción a magyar nyelvű kezelőfelület látható.

![A Most nézem sáv a kezdőlapon](../screenshots/now-watching-desktop2.png)

A MediaTrail kiegészítő hivatkozása a Beállítások → Integrációk → Nuvio menüpontból másolható ki, amelyet valamennyi [NuvioMobile-MT](https://github.com/aicon/NuvioMobile-MT) és [NuvioTV-MT](https://github.com/aicon/NuvioTV-MT) kliensben hozzá kell adni a bővítményekhez. Részletes tájékoztató: [Live playback / Now Watching](../LIVE_PLAYBACK_NOW_WATCHING.md). A kétirányú megtekintési-előzmény szinkron (megnézett / nem megtekintett) ugyanezen az Integrációk oldalon kapcsolható; lásd: [Import → Nuvio](imports.md#nuvio).

Egy mű adatlapját megnyitva a külső katalógus adatai és a naplózási űrlap jelenik meg. A bejegyzéshez rögzíthető az aktuális állapot, a személyes értékelés, a megtekintés előrehaladása, a kezdeti és befejezési dátum, valamint egyéni megjegyzés. Amennyiben egy korábban befejezett művet újra megtekintünk vagy újraolvasunk, a rendszer újabb bejegyzést fűz a megtekintési előzményekhez. A sorozatok hierarchikus felépítésűek: az évadok és az epizódok különálló tételként szerepelnek a rendszerben, így egyetlen rész megtekintésének rögzítése nem írja felül a teljes műsort.

## Kezelőfelület és metaadatok nyelve

A Beállításokban adható meg a felület kívánt nyelve (magyar vagy angol), amely a felhasználói fiókhoz kötődve tárolódik. A külső katalógusokból beemelt leírások nyelve attól függ, hogy a kiszolgálót milyen nyelvi paraméterrel kérdezi le a rendszer. A filmek és sorozatok leírásának nyelvét a `TMDB_LANG` környezeti változó határozza meg (lásd a [Környezet](runtime.md) fejezetet).

## Egyéni bejegyzések

Előfordulhat, hogy egy keresett mű nem szerepel az elérhető online katalógusokban. Az oldalsávban található **Egyéni bejegyzés** menüpont révén bármilyen tétel kézzel is rögzíthető: megadható a típus, a cím és igény szerint egy borítókép hivatkozása is. Ezt követően a bejegyzés éppúgy kezelhető és naplózható, mint bármely más katalógustétel.

## Egyéni listák

A listák tetszőlegesen elnevezhető, tematikus gyűjtemények. Egyetlen listán belül különböző típusú művek is vegyíthetők, sőt, a szerkesztésbe ugyanazon a szerveren lévő más felhasználói fiókok is bevonhatók. A listán belüli keresés és a rendezési szempontok az adott lista oldalán érhetők el.

## Naptár

A naptár a gyűjteményben szereplő tételek közelgő megjelenési dátumait foglalja össze. Az oldalon található exportálási hivatkozás révén a naptár privát forrásként beilleszthető bármilyen külső naptárprogramba. Ez a hivatkozás a személyes hitelesítési tokent tartalmazza; amennyiben a Beállításokban új tokent generál, a régi hivatkozás érvényét veszti, és a korábbi tokennel működő médialejátszó webhookok beállítását is frissíteni kell.

## Statisztika

A statisztikai áttekintés összegzi az állapotok megoszlását, a naplózási aktivitást és a választott időszak eredményeit, a mai naptól kezdve egészen a kezdetekig visszamenően. A diagramok feliratai a felület választott nyelvét követik.

## Értesítések

A Beállítások menüpont Értesítések oldalán soronként egy-egy Apprise-cím adható meg. A megjelenési emlékeztetők és a napi összesítők ezekre az értesítési végpontokra érkeznek. Az oldalon található segédlet részletesen felsorolja az Apprise által elfogadott formátumokat.
