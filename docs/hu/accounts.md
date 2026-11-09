# Fiókok

[English](../accounts.md)

A fiók egy felhasználónév és egy jelszó. E-mail-cím nincs a fiókon. Az első fiók azé, aki regisztrál. A későbbi fiókok ugyanazon az oldalon külön könyvtárak.

Amíg a `REGISTRATION` értéke `True`, a regisztráció a `/signup/`, a belépés a `/login/` címen van. Állítsd `False` értékre, ha már mindenkinek megvan a fiókja, akinek kell.

A bejelentkezett személy a beállítások oldalain cseréli a jelszót, a felhasználónevet, a felület nyelvét és az importot. Egy fiók nem látja a másik könyvtárát, kivéve a megosztott listát.

## Adminfelület

Az adminfelület addig ki van kapcsolva, amíg a konténeren az `ADMIN_ENABLED` értéke nem `True`. A beállítás után hozd létre újra a konténert, majd nyisd meg a `/admin/` címet.

Az adminbelépés személyzeti fiók, a sima regisztráció nem az. A gépről, a választott konténernévvel:

```bash
docker exec -it mediatrail python manage.py createsuperuser
```

Meglévő fiók feljogosításához nyiss héjat a konténerben a `python manage.py shell` paranccsal, és állítsd az adott felhasználón az `is_staff` és az `is_superuser` mezőt. Az adminfelület közvetlenül az adatbázist szerkeszti. A mindennapi követéshez nem kell.

## Token

A Beállításokban új személyes tokent lehet kérni. A naptár exportlinkje és a Jellyfin, a Plex és az Emby webhookcíme ezt a tokent használja. Az új token után ezeket a címeket újra be kell illeszteni a másik programba.
