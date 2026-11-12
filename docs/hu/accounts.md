# Fiókok

[English](../accounts.md)

A MediaTrail rendszerében egy felhasználói fiók egy felhasználónévből és egy jelszóból áll; e-mail-cím megadása nem szükséges a fiók létrehozásához. Az elsőként regisztráló felhasználóé lesz a kezdő fiók. A későbbiekben létrehozott fiókok teljesen elkülönülő, önálló gyűjteménnyel rendelkeznek ugyanazon a szerveren.

Mindaddig, amíg a `REGISTRATION` környezeti változó értéke `True`, az új fiókok regisztrációja a `/signup/`, a bejelentkezés pedig a `/login/` oldalon érhető el. Érdemes a változót `False` értékre állítanod, miután minden jogosult felhasználó elkészítette a saját fiókját.

A bejelentkezett felhasználók a Beállítások oldalon módosíthatják a jelszavukat, a felhasználónevüket, a felület nyelvét, valamint az importálási beállításokat. Az egyes fiókok nem láthatják egymás személyes gyűjteményét, kivéve azokat a listákat, amelyeket kifejezetten megosztottak egymással.

## Adminisztrációs felület

Az adminisztrációs felület mindaddig elérhetetlen, amíg a konténer konfigurációjában az `ADMIN_ENABLED` értéke nem `True`. A beállítást követően indítsd újra a konténert, majd nyisd meg a `/admin/` címet.

Az adminisztrátori hozzáférés emelt szintű jogosultságot (staff jogosultságot) igényel, amellyel a hagyományos regisztráció során létrehozott fiókok nem rendelkeznek. Új adminisztrátori fiókot a kiszolgálógép parancssorából, a választott konténernév megadásával hozhatsz létre:

```bash
docker exec -it mediatrail python manage.py createsuperuser
```

Egy már meglévő fiók adminisztrátori rangra emeléséhez nyiss egy interaktív konzolt a konténerben a `python manage.py shell` paranccsal, majd állítsd az adott felhasználónál az `is_staff` és az `is_superuser` mezők értékét `True`-ra. Az adminisztrációs felület közvetlenül az adatbázis rekordjait módosítja, így a mindennapi naplózási feladatokhoz nincs rá szükség.

## Személyes hitelesítési tokenek

A Beállítások felületén bármikor kérhetsz új személyes tokent. A naptár exportálási hivatkozása, valamint a Jellyfin, a Plex és az Emby médiaszerverek webhook-címei mind ezt a tokent használják a hitelesítéshez. Egy új token létrehozása után a megváltozott címeket ismételten be kell másolnod a külső alkalmazások megfelelő beállításaiba.
