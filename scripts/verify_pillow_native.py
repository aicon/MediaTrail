#!/usr/bin/env python3
"""Fail the image build unless Pillow and Brotli match the security policy.

Policy (MediaTrail Alpine image):
- Pillow must be >= 13.0.0 (XBM ReDoS CVE-2026-112901 / GHSA-xgh8-jp6q-p5x8).
- The install must not ship a bundled ``pillow.libs`` Brotli 1.2.0 copy
  (CVE-2026-111497). PyPI musllinux/manylinux 12.3.0 and 13.0.0 wheels both
  embed ``libbrotlidec*.so.1.2.0``; we therefore build Pillow from source and
  link Alpine ``brotli-libs`` 1.2.1+.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import pathlib
import re
import sys

MIN_PILLOW = (13, 0, 0)
MIN_BROTLI = (1, 2, 1)


def _parse_version(text: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", text)
    if not parts:
        msg = f"cannot parse version from {text!r}"
        raise SystemExit(msg)
    return tuple(int(p) for p in parts[:3])


def _brotli_tuple_from_packed(value: int) -> tuple[int, int, int]:
    # BrotliDecoderVersion(): (MAJOR << 24) | (MINOR << 12) | PATCH
    return (value >> 24) & 0xFF, (value >> 12) & 0xFFF, value & 0xFFF


def main() -> int:
    import PIL
    from PIL import Image, features

    pillow_version = _parse_version(PIL.__version__)
    print(f"Pillow {PIL.__version__}")
    if pillow_version < MIN_PILLOW:
        msg = (
            f"Pillow {PIL.__version__} is below required "
            f"{'.'.join(map(str, MIN_PILLOW))} (CVE-2026-112901)."
        )
        raise SystemExit(msg)

    pillow_root = pathlib.Path(PIL.__file__).resolve().parent
    bundled_libs = pillow_root.parent / "pillow.libs"
    if bundled_libs.is_dir():
        brotli_libs = sorted(bundled_libs.glob("*brotli*"))
        print("Bundled native libs dir:", bundled_libs)
        for path in brotli_libs:
            print(" ", path.name)
            if re.search(r"\.so\.1\.2\.0(\.|$)", path.name) or path.name.endswith(
                ".1.2.0",
            ):
                msg = (
                    f"Bundled Brotli 1.2.0 found at {path.name} "
                    "(CVE-2026-111497). Rebuild Pillow from source against "
                    "system brotli >= 1.2.1; do not use the PyPI wheel."
                )
                raise SystemExit(msg)
        if brotli_libs:
            # Any bundled brotli must still be >= 1.2.1.
            for path in brotli_libs:
                match = re.search(r"\.so\.(\d+\.\d+\.\d+)", path.name)
                if match and _parse_version(match.group(1)) < MIN_BROTLI:
                    msg = f"Bundled Brotli too old: {path.name}"
                    raise SystemExit(msg)
    else:
        print("No pillow.libs directory (expected for a system-linked build).")

    lib_name = ctypes.util.find_library("brotlidec")
    if not lib_name:
        # Alpine often needs the soname explicitly.
        for candidate in (
            "libbrotlidec.so.1",
            "libbrotlidec.so",
            "/usr/lib/libbrotlidec.so.1",
        ):
            try:
                ctypes.CDLL(candidate)
                lib_name = candidate
                break
            except OSError:
                continue
    if not lib_name:
        msg = "libbrotlidec not found on the dynamic loader path."
        raise SystemExit(msg)

    lib = ctypes.CDLL(lib_name)
    if not hasattr(lib, "BrotliDecoderVersion"):
        msg = f"{lib_name} has no BrotliDecoderVersion symbol."
        raise SystemExit(msg)
    lib.BrotliDecoderVersion.restype = ctypes.c_uint32
    packed = int(lib.BrotliDecoderVersion())
    brotli_version = _brotli_tuple_from_packed(packed)
    print(
        f"Loaded {lib_name}; BrotliDecoderVersion="
        f"{brotli_version[0]}.{brotli_version[1]}.{brotli_version[2]} "
        f"(packed={packed})",
    )
    if brotli_version < MIN_BROTLI:
        msg = (
            f"System Brotli {brotli_version} is below required {MIN_BROTLI} "
            "(CVE-2026-111497)."
        )
        raise SystemExit(msg)

    # Touch FreeType integration; WOFF2 support is where Brotli is used.
    print("Pillow freetype feature:", features.check("freetype"))
    print("Pillow Image import OK:", Image.__name__)
    print("verify_pillow_native: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
