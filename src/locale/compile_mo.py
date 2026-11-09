"""Compile a simple gettext catalog to a .mo file. No GNU gettext required."""

import ast
import struct
import sys
from pathlib import Path


def unescape(value):
    return ast.literal_eval(value)


def parse_po(text):
    entries = []
    current = {"msgctxt": None, "msgid": None, "msgid_plural": None, "msgstr": []}
    mode = None

    def finish():
        if current["msgid"] is None:
            return
        entries.append(
            {
                "msgctxt": current["msgctxt"],
                "msgid": current["msgid"],
                "msgid_plural": current["msgid_plural"],
                "msgstr": current["msgstr"],
            }
        )

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgctxt "):
            if current["msgid"] is not None:
                finish()
                current = {"msgctxt": None, "msgid": None, "msgid_plural": None, "msgstr": []}
            mode = "msgctxt"
            current["msgctxt"] = unescape(line.split(" ", 1)[1])
        elif line.startswith("msgid_plural "):
            mode = "msgid_plural"
            current["msgid_plural"] = unescape(line.split(" ", 1)[1])
        elif line.startswith("msgid "):
            if current["msgid"] is not None:
                finish()
                current = {"msgctxt": None, "msgid": None, "msgid_plural": None, "msgstr": []}
            mode = "msgid"
            current["msgid"] = unescape(line.split(" ", 1)[1])
        elif line.startswith("msgstr["):
            mode = "msgstr"
            current["msgstr"].append(unescape(line.split(" ", 1)[1]))
        elif line.startswith("msgstr "):
            mode = "msgstr"
            current["msgstr"] = [unescape(line.split(" ", 1)[1])]
        elif line.startswith('"') and mode:
            current[mode if mode != "msgstr" else "msgstr"] = (
                current["msgstr"][:-1] + [current["msgstr"][-1] + unescape(line)]
                if mode == "msgstr"
                else current[mode] + unescape(line)
            )
    finish()
    return entries


def write_mo(path, entries):
    messages = {}
    for entry in entries:
        key = entry["msgid"]
        if entry["msgctxt"]:
            key = entry["msgctxt"] + "\x04" + key
        if entry["msgid_plural"]:
            key = key + "\0" + entry["msgid_plural"]
            value = "\0".join(entry["msgstr"])
        else:
            value = entry["msgstr"][0] if entry["msgstr"] else ""
        messages[key] = value

    keys = sorted(messages)
    originals = [key.encode("utf-8") for key in keys]
    translations = [messages[key].encode("utf-8") for key in keys]
    count = len(keys)
    header_size = 28
    table_size = 8 * count
    key_offset = header_size + table_size * 2
    original_table = []
    translation_table = []
    original_blob = b""
    translation_blob = b""
    for original, translation in zip(originals, translations):
        original_table.append((len(original), key_offset + len(original_blob)))
        original_blob += original + b"\0"
    value_offset = key_offset + len(original_blob)
    for translation in translations:
        translation_table.append((len(translation), value_offset + len(translation_blob)))
        translation_blob += translation + b"\0"

    output = struct.pack(
        "<Iiiiiii",
        0x950412DE,
        0,
        count,
        header_size,
        header_size + table_size,
        0,
        0,
    )
    for length, offset in original_table:
        output += struct.pack("<ii", length, offset)
    for length, offset in translation_table:
        output += struct.pack("<ii", length, offset)
    output += original_blob + translation_blob
    path.write_bytes(output)


def main():
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    entries = parse_po(source.read_text(encoding="utf-8"))
    write_mo(target, entries)
    print(f"{len(entries)} entries -> {target}")


if __name__ == "__main__":
    main()
