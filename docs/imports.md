# Imports

[Magyar változat](hu/imports.md)

Settings, then Import, is where an outside history becomes library rows. Two choices at the top apply to every source:

- **Only new items** adds what is missing locally and leaves existing rows alone.
- **New items and overwrite** also updates the watch date of a row that is already there. Scores and notes stay. Nothing is deleted.

Frequency is once, or a repeat from the clock time you pick. A repeat keeps running until you remove it from Active periodic imports. File uploads cannot be repeated. A username or a saved sign-in can.

The history list below the sources shows the last seven days. A task that says it has started is still in progress. A finished task can still list rows it skipped.

## Nuvio

Nuvio is the first source. It reads movies and episodes from one Nuvio profile. It never writes back to Nuvio, and it does not delete local rows when something disappears upstream.

The form asks for the Nuvio email, the password, and the profile number. The first successful submit stores them encrypted on your MediaTrail account. The next time you open the page, the email and the profile are filled in. Leave the password blank to keep the saved one. Type a new password only when you want to replace it. A different email or a different profile starts that account's import cursor over.

What a run does:

- A movie that is not in the library is added as completed, with the Nuvio watch time.
- An episode that is not in the library is added the same way. The season and the show are created if they are missing.
- In "only new items", a movie or episode that is already there is left as it is, including a date you edited.
- In overwrite, the existing movie, or the latest row of that episode, gets the Nuvio watch time. The rest of the row stays.
- If you remove an episode in MediaTrail and Nuvio still has that watch, the next import adds it again. "Only new items" means missing locally, even when that Nuvio event was imported before.
- A series row that has no season number or no episode number is skipped and remembered, so later runs do not keep reporting it.
- A delete event from Nuvio is ignored.

The profile number is the Nuvio profile, not a MediaTrail user. Most people have one profile, numbered 1.

## Other sources

These sources use the same mode and frequency controls.

| Source | What you provide | Notes |
| --- | --- | --- |
| Trakt | A public username, or a connect button for a private profile | A private profile needs your own Trakt application id and secret. See [Runtime](runtime.md). |
| Simkl | A connect button | A private import needs your own Simkl id and secret if you replace the built-in client. |
| MyAnimeList | A public username | |
| AniList | A public username, or a connect button | A private profile needs your own AniList application. |
| Kitsu | The numeric user id from the profile address | |
| Steam | The 64-bit Steam id | The profile has to be public unless the Steam key belongs to that account. |
| MediaTrail backup | A CSV file from Settings, then Export | One-time only. |
| HowLongToBeat | A CSV export | One-time only. Games. |
| IMDb | A ratings CSV | One-time only. |
| Goodreads | A library export | One-time only. Books. |

Matching uses the catalog ids MediaTrail already stores. A title the catalog does not know is reported on the finished task and is not invented.

## Players

Jellyfin, Plex, and Emby can tell MediaTrail about playback through a webhook. Settings, then Integrations, shows the address for each player. The address includes your token. The page itself lists the clicks for that player. Regenerating the token changes the address.
