# MediaTrail

MediaTrail is an independent, unofficial fork of [Yamtrack](https://github.com/FuzzyGrim/Yamtrack). It is not affiliated with, endorsed by, or maintained by the Yamtrack project or its developers.

This directory is a local working copy. It has no GitHub remote yet.

The program is the Yamtrack fork that was already in this workspace, including the preview API, episode history, and Now Watching work. The Python package name stays `yamtrack` so the application layout does not change. The name people see is MediaTrail.

## License

MediaTrail is licensed under the GNU Affero General Public License v3.0. The license text is [`LICENSE`](https://github.com/aicon/MediaTrail/blob/main/LICENSE) in this repository, and it is the unchanged GNU text. Yamtrack's copyright notices are kept. MediaTrail's own copyright notice is in [`NOTICE`](NOTICE). Modifications in this tree stay under the same license.

Because this is a modified network program, AGPL-3.0 section 13 requires a prominent offer of the corresponding source of the version that is actually running. Upstream Yamtrack's repository is the original program. It is not a substitute for the source of this modified version.

Set `MEDIATRAIL_SOURCE_URL` to an `http` or `https` address of that exact source before anyone else uses the app over a network. Until then, the footer and `/source/` say that the offer is still missing. Leave the variable empty on a private local copy.

## Support

The left sidebar has a fixed **Buy me a coffee** button to [Ko-fi](https://ko-fi.com/aiconwg), directly under the divider. The caption is “Supports the MediaTrail maintainer.”

## API keys

Provider keys, including a Gemini API key, belong in the operator's own runtime settings. Do not pass them as Docker build arguments, and do not copy them into the image. `.env` files are excluded from the image build.

## Run locally

MediaTrail versions continue from 0.25.3 in small steps. The stable release is `0.25.7`. Day-to-day work is on the `dev` branch, which publishes `ghcr.io/aicon/mediatrail:dev`. A stable image is published only from a `v*` release tag, as `ghcr.io/aicon/mediatrail:<version>` and `latest`. The repository and the image are private. Redis runs inside the image and keeps its data under the existing `db` volume.

`docker-compose.local.yml` can still build this directory on the machine as `mediatrail:local`. It does not start a separate Redis container. Put secrets in the Compose environment or a local `.env` that is not baked into the image.

`docker-compose.yml` and `docker-compose.postgres.yml` are the upstream Yamtrack examples. They are not the MediaTrail image.

Inherited Yamtrack documentation is in [`docs/`](docs/). Notes from the earlier fork packaging are in [`fork.md`](fork.md) and [`docs/yamtrack-fork-readme.md`](docs/yamtrack-fork-readme.md).
