from django.urls import path, re_path

from integrations import views

urlpatterns = [
    # Per-account addon URL (token matches Jellyfin/Plex/Emby webhooks).
    path(
        "nuvio/<str:token>/manifest.json",
        views.nuvio_manifest,
        name="nuvio_manifest",
    ),
    re_path(r"^nuvio/(?P<token>[^/]+)/manifest/?$", views.nuvio_manifest),
    re_path(
        r"^nuvio/(?P<token>[^/]+)/player/(?P<media_type>[^/]+)/(?P<video_id>[^/]+)"
        r"(?:/(?P<extra>.+))?$",
        views.nuvio_player,
        name="nuvio_player",
    ),
    # Legacy untokened routes: only safe when MediaTrail has a single account.
    path("nuvio/manifest.json", views.nuvio_manifest, name="nuvio_manifest_legacy"),
    re_path(r"^nuvio/manifest/?$", views.nuvio_manifest),
    re_path(
        r"^nuvio/player/(?P<media_type>[^/]+)/(?P<video_id>[^/]+)"
        r"(?:/(?P<extra>.+))?$",
        views.nuvio_player,
        name="nuvio_player_legacy",
    ),
    path("import/nuvio", views.import_nuvio, name="import_nuvio"),
    path("import/trakt-oauth", views.trakt_oauth, name="trakt_oauth"),
    path("import/trakt/device", views.trakt_device_start, name="trakt_device_start"),
    path(
        "import/trakt/device/poll",
        views.trakt_device_poll,
        name="trakt_device_poll",
    ),
    path(
        "import/trakt/private",
        views.import_trakt_private,
        name="import_trakt_private",
    ),
    path("import/trakt/public", views.import_trakt_public, name="import_trakt_public"),
    path(
        "import/trakt/export",
        views.import_trakt_export,
        name="import_trakt_export",
    ),
    path("import/simkl-oauth", views.simkl_oauth, name="simkl_oauth"),
    path(
        "import/simkl_private",
        views.import_simkl_private,
        name="import_simkl_private",
    ),
    path("import/mal", views.import_mal, name="import_mal"),
    path("import/anilist/oauth", views.anilist_oauth, name="import_anilist_oauth"),
    path(
        "import/anilist/private",
        views.import_anilist_private,
        name="import_anilist_private",
    ),
    path(
        "import/anilist/public",
        views.import_anilist_public,
        name="import_anilist_public",
    ),
    path("import/kitsu", views.import_kitsu, name="import_kitsu"),
    path("import/mediatrail", views.import_yamtrack, name="import_yamtrack"),
    path("import/hltb", views.import_hltb, name="import_hltb"),
    path("import/steam", views.import_steam, name="import_steam"),
    path("import/imdb", views.import_imdb, name="import_imdb"),
    path("import/goodreads", views.import_goodreads, name="import_goodreads"),
    path("export/csv", views.export_csv, name="export_csv"),
    path(
        "webhook/jellyfin/<str:token>",
        views.jellyfin_webhook,
        name="jellyfin_webhook",
    ),
    path(
        "webhook/plex/<str:token>",
        views.plex_webhook,
        name="plex_webhook",
    ),
    path(
        "webhook/emby/<str:token>",
        views.emby_webhook,
        name="emby_webhook",
    ),
]
