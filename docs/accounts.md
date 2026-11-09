# Accounts

[Magyar változat](hu/accounts.md)

An account is a username and a password. There is no email address on the account. The first account is whoever signs up. Later accounts are separate libraries on the same site.

While `REGISTRATION` is `True`, the sign-up page is `/signup/` and the login page is `/login/`. Set `REGISTRATION` to `False` when the people who should have accounts already have them.

A signed-in person changes the password, the username, the interface language, and the import settings from the settings pages. One account cannot see another's library unless they share a list.

## Admin site

The admin site is off until the container has `ADMIN_ENABLED=True`. Recreate the container after setting it, then open `/admin/`.

An admin login is a staff account, which a normal sign-up is not. From the host, with the container name you chose:

```bash
docker exec -it mediatrail python manage.py createsuperuser
```

To promote an account that already exists, open a shell in the container with `python manage.py shell` and set `is_staff` and `is_superuser` on that user. The admin site edits the database directly. Day-to-day tracking does not need it.

## Tokens

Settings can regenerate the personal token. The calendar export link and the Jellyfin, Plex, and Emby webhook addresses all use that token. After a regeneration, paste the new addresses into those other programs.
