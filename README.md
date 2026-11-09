# MediaTrail

MediaTrail is an independent, unofficial fork of [Yamtrack](https://github.com/FuzzyGrim/Yamtrack). It is not affiliated with, endorsed by, or maintained by the Yamtrack project or its developers.

This directory is a local working copy. It has no GitHub remote yet.

The program is the Yamtrack fork that was already in this workspace, including the preview API, episode history, and Now Watching work. The Python package name stays `yamtrack` so the application layout does not change. The name people see is MediaTrail.

## License

Yamtrack is licensed under the GNU Affero General Public License v3.0. MediaTrail keeps that license and the copyright notices. The license text is [`LICENSE`](LICENSE). Modifications in this tree are under the same license.

Because this is a modified network program, AGPL-3.0 section 13 requires a prominent offer of the corresponding source of the version that is actually running. Upstream Yamtrack's repository is the original program. It is not a substitute for the source of this modified version.

Set `MEDIATRAIL_SOURCE_URL` to an `http` or `https` address of that exact source before anyone else uses the app over a network. Until then, the footer and `/source/` say that the offer is still missing. Leave the variable empty on a private local copy.

## Support

The left sidebar has a fixed **Buy me a coffee** button to [Ko-fi](https://ko-fi.com/aiconwg). It supports the MediaTrail maintainer. It does not support Yamtrack or its developers, and Yamtrack does not endorse MediaTrail.

## API keys

Provider keys, including a Gemini API key, belong in the operator's own runtime settings. Do not pass them as Docker build arguments, and do not copy them into the image. `.env` files are excluded from the image build.

## Run locally

The first image is `ghcr.io/aicon/mediatrail:0.1.0` (`latest` is the same build). It is private, like the repository. Redis runs inside that image and keeps its data under the existing `db` volume.

`docker-compose.local.yml` can still build this directory on the machine as `mediatrail:local`. It does not start a separate Redis container. Put secrets in the Compose environment or a local `.env` that is not baked into the image.

`docker-compose.yml` and `docker-compose.postgres.yml` are the upstream Yamtrack examples. They are not the MediaTrail image.

Inherited Yamtrack documentation is in [`docs/`](docs/). Notes from the earlier fork packaging are in [`fork.md`](fork.md) and [`docs/yamtrack-fork-readme.md`](docs/yamtrack-fork-readme.md).
