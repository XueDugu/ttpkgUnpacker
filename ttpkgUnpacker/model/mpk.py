import json
import struct
from dataclasses import dataclass
from io import SEEK_END
from typing import Dict, Optional

from ttpkgUnpacker.util.io_helper import IOHelper

MPK_MAGIC = b"TPKG"
MPK_VERSION = 131072
MAX_ENTRY_NAME_LENGTH = 4096
PLAIN_LAYOUT_CANDIDATES = (
    {"label": "reserved-u32", "reserved_bytes": 4, "first_entry_padding": 0},
    {"label": "no-reserved-u32", "reserved_bytes": 0, "first_entry_padding": 0},
    {"label": "reserved-u32-first-padding-3", "reserved_bytes": 4, "first_entry_padding": 3},
    {"label": "no-reserved-u32-first-padding-3", "reserved_bytes": 0, "first_entry_padding": 3},
)
TTKS_NAME_HINTS = {
    0: "app-config.json",
    1: "game.js",
    2: "game.json",
    3: "libs/common/engine/Audio.js",
    4: "libs/common/engine/AudioEngine.js",
    5: "libs/common/engine/DeviceMotionEvent.js",
    6: "libs/common/engine/Editbox.js",
    7: "libs/common/engine/Game.js",
    8: "libs/common/engine/globalAdapter/BaseSystemInfo.js",
    9: "libs/common/engine/globalAdapter/ContainerStrategy.js",
    10: "libs/common/engine/globalAdapter/index.js",
    11: "libs/common/engine/globalAdapter/View.js",
    12: "libs/common/engine/index.js",
    13: "libs/common/engine/InputManager.js",
    14: "libs/common/engine/Loader.js",
    15: "libs/common/engine/Screen.js",
    16: "libs/common/engine/Texture2D.js",
    17: "libs/common/engine/VideoPlayer.js",
    18: "libs/common/remote-downloader.js",
    19: "libs/common/xmldom/dom-parser.js",
    20: "libs/common/xmldom/dom.js",
    21: "libs/common/xmldom/entities.js",
    22: "libs/common/xmldom/sax.js",
    23: "libs/wrapper/builtin/Audio.js",
    24: "libs/wrapper/builtin/Canvas.js",
    25: "libs/wrapper/builtin/document.js",
    26: "libs/wrapper/builtin/Element.js",
    27: "libs/wrapper/builtin/Event.js",
    28: "libs/wrapper/builtin/EventIniter/index.js",
    29: "libs/wrapper/builtin/EventIniter/MouseEvent.js",
    30: "libs/wrapper/builtin/EventIniter/TouchEvent.js",
    31: "libs/wrapper/builtin/EventTarget.js",
    32: "libs/wrapper/builtin/FileReader.js",
    33: "libs/wrapper/builtin/HTMLAudioElement.js",
    34: "libs/wrapper/builtin/HTMLCanvasElement.js",
    35: "libs/wrapper/builtin/HTMLElement.js",
    36: "libs/wrapper/builtin/HTMLImageElement.js",
    37: "libs/wrapper/builtin/HTMLMediaElement.js",
    38: "libs/wrapper/builtin/HTMLVideoElement.js",
    39: "libs/wrapper/builtin/Image.js",
    40: "libs/wrapper/builtin/ImageBitmap.js",
    41: "libs/wrapper/builtin/index.js",
    42: "libs/wrapper/builtin/localStorage.js",
    43: "libs/wrapper/builtin/location.js",
    44: "libs/wrapper/builtin/navigator.js",
    45: "libs/wrapper/builtin/Node.js",
    46: "libs/wrapper/builtin/util/index.js",
    47: "libs/wrapper/builtin/WebGLRenderingContext.js",
    48: "libs/wrapper/builtin/WebSocket.js",
    49: "libs/wrapper/builtin/window.js",
    50: "libs/wrapper/builtin/WindowProperties.js",
    51: "libs/wrapper/builtin/Worker.js",
    52: "libs/wrapper/builtin/XMLHttpRequest.js",
    53: "libs/wrapper/engine/index.js",
    54: "libs/wrapper/engine/Loader.js",
    55: "libs/wrapper/fs-utils.js",
    56: "libs/wrapper/systemInfo.js",
    57: "libs/wrapper/unify.js",
    58: "libs/wrapper/utils.js",
    59: "main.js",
    356: "src/project.js",
    357: "src/settings.js",
}


class MPKParseError(ValueError):
    pass


@dataclass
class MPKEntry:
    index: int
    offset: int
    data_size: int
    name: str
    data: Optional[bytes] = None


class MPK:
    def __init__(self, io):
        self._io = io
        self._files = []
        self._version = MPK_VERSION
        self._layout = None
        self._index_end = 0
        self._package_variant = "plain"
        self._header_metadata = {}

    @staticmethod
    def load(io):
        instance = MPK(io)
        file_size = MPK._file_size(io)

        io.seek(0)
        magic = IOHelper.read_exact(io, 4)
        if magic != MPK_MAGIC:
            magic_text = magic.decode("ascii", errors="replace")
            raise MPKParseError(f"Unsupported package magic: {magic_text!r}")

        version = IOHelper.read_struct(io, "<I")[0]
        instance.set_version(version)

        errors = []

        encrypted_header = MPK._read_ttks_header(io, file_size)
        if encrypted_header is not None:
            try:
                entries, index_end, metadata = MPK._parse_ttks_entries(io, file_size, encrypted_header)
            except (MPKParseError, EOFError, UnicodeDecodeError, ValueError) as exc:
                errors.append(f"ttks-encrypted: {exc}")
            else:
                instance._layout = {"label": "ttks-encrypted"}
                instance._index_end = index_end
                instance._package_variant = "ttks-encrypted"
                instance._header_metadata = metadata
                for entry in entries:
                    instance.insert_file(entry)
                return instance

        for layout in PLAIN_LAYOUT_CANDIDATES:
            try:
                entries, index_end = MPK._parse_plain_entries(io, file_size, layout)
            except (MPKParseError, EOFError) as exc:
                errors.append(f"{layout['label']}: {exc}")
                continue

            instance._layout = layout
            instance._index_end = index_end
            for entry in entries:
                instance.insert_file(entry)
            return instance

        error_text = "; ".join(errors) if errors else "no parser candidates were attempted"
        raise MPKParseError(f"Unable to parse package index: {error_text}")

    @staticmethod
    def _file_size(io):
        current = io.tell()
        io.seek(0, SEEK_END)
        size = io.tell()
        io.seek(current)
        return size

    @staticmethod
    def _read_ttks_header(io, file_size):
        io.seek(8)
        metadata_block_size = IOHelper.read_struct(io, "<I")[0]
        metadata_length = IOHelper.read_struct(io, "<I")[0]
        if metadata_length <= 0 or metadata_length > min(file_size - 16, MAX_ENTRY_NAME_LENGTH):
            return None

        metadata_raw = IOHelper.read_exact(io, metadata_length)
        if not metadata_raw.startswith(b"JSON{"):
            return None

        try:
            metadata = json.loads(metadata_raw[4:].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

        if "__ttks" not in metadata:
            return None

        return {
            "metadata_block_size": metadata_block_size,
            "metadata_length": metadata_length,
            "metadata": metadata,
        }

    @staticmethod
    def _parse_plain_entries(io, file_size, layout):
        io.seek(8)
        if layout["reserved_bytes"]:
            IOHelper.read_exact(io, layout["reserved_bytes"])

        count = IOHelper.read_struct(io, "<I")[0]
        max_entries = max(file_size // 12, 0)
        if count > max_entries:
            raise MPKParseError(f"entry count {count} is larger than file bounds allow")

        entries = []
        for index in range(count):
            name_length = IOHelper.read_struct(io, "<I")[0]
            if name_length > MAX_ENTRY_NAME_LENGTH:
                raise MPKParseError(f"entry {index} name length {name_length} is too large")

            if index == 0 and layout["first_entry_padding"]:
                IOHelper.read_exact(io, layout["first_entry_padding"])

            remaining = file_size - io.tell()
            if name_length > remaining:
                raise MPKParseError(f"entry {index} name length exceeds remaining file size")

            raw_name = IOHelper.read_exact(io, name_length)
            try:
                name = raw_name.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise MPKParseError(f"entry {index} has a non-UTF-8 file name") from exc

            offset = IOHelper.read_struct(io, "<I")[0]
            data_size = IOHelper.read_struct(io, "<I")[0]
            entries.append(MPKEntry(index=index, offset=offset, data_size=data_size, name=name))

        index_end = io.tell()
        MPK._validate_entries(entries, index_end, file_size)
        return entries, index_end

    @staticmethod
    def _parse_ttks_entries(io, file_size, header):
        io.seek(16 + header["metadata_length"])
        count = IOHelper.read_struct(io, "<I")[0]
        max_entries = max(file_size // 16, 0)
        if count > max_entries:
            raise MPKParseError(f"encrypted entry count {count} is larger than file bounds allow")

        raw_entries = []
        for index in range(count):
            name_length = IOHelper.read_struct(io, "<I")[0]
            if name_length <= 0 or name_length > 68:
                raise MPKParseError(f"encrypted entry {index} name length {name_length} is not supported")
            encrypted_name = IOHelper.read_exact(io, name_length)
            encrypted_meta = IOHelper.read_exact(io, 8)
            raw_entries.append(
                {
                    "index": index,
                    "name_length": name_length,
                    "encrypted_name": encrypted_name,
                    "encrypted_meta": encrypted_meta,
                },
            )

        index_end = io.tell()
        key_stream = MPK._derive_ttks_key_stream(raw_entries)
        entries = []
        for raw_entry in raw_entries:
            name = MPK._decode_name(raw_entry["encrypted_name"], key_stream)
            offset, data_size = MPK._decode_meta(raw_entry, key_stream)
            entries.append(
                MPKEntry(
                    index=raw_entry["index"],
                    offset=offset,
                    data_size=data_size,
                    name=name,
                ),
            )

        MPK._validate_entries(entries, index_end, file_size)
        return entries, index_end, header["metadata"]

    @staticmethod
    def _derive_ttks_key_stream(raw_entries):
        key_stream = {}

        for index, expected_name in TTKS_NAME_HINTS.items():
            if index >= len(raw_entries):
                raise MPKParseError("Encrypted package does not match the supported template.")
            raw_entry = raw_entries[index]
            if raw_entry["name_length"] != len(expected_name):
                raise MPKParseError(
                    f"Encrypted package template mismatch at entry {index}: "
                    f"expected name length {len(expected_name)}, got {raw_entry['name_length']}",
                )
            MPK._apply_name_hint(raw_entry["encrypted_name"], expected_name, key_stream)

        import_entry = next(
            (
                entry
                for entry in raw_entries
                if entry["name_length"] == 55
                and MPK._decode_name_prefix(entry["encrypted_name"], key_stream).startswith("res/import/")
            ),
            None,
        )
        if import_entry is None:
            raise MPKParseError("Unable to locate an encrypted import entry for key-stream recovery.")
        key_stream[53] = import_entry["encrypted_name"][53] ^ ord("o")
        key_stream[54] = import_entry["encrypted_name"][54] ^ ord("n")

        for index in range(1, len(raw_entries) - 1):
            previous_entry = raw_entries[index - 1]
            current_entry = raw_entries[index]
            next_entry = raw_entries[index + 1]
            if previous_entry["name_length"] != 28 or current_entry["name_length"] != 55 or next_entry["name_length"] != 28:
                continue

            previous_meta = MPK._decode_meta_if_possible(previous_entry, key_stream)
            next_meta = MPK._decode_meta_if_possible(next_entry, key_stream)
            if previous_meta is None or next_meta is None:
                continue

            current_offset = previous_meta[0] + previous_meta[1]
            current_size = next_meta[0] - current_offset
            if current_size <= 0:
                continue

            MPK._apply_meta_hint(current_entry["encrypted_meta"][:4], current_entry["name_length"], current_offset, key_stream)
            MPK._apply_meta_hint(current_entry["encrypted_meta"][4:], current_entry["name_length"] + 4, current_size, key_stream)
            break
        else:
            raise MPKParseError("Unable to derive the import-entry meta key-stream.")

        raw_start_index = next((index for index, entry in enumerate(raw_entries) if entry["name_length"] == 58), None)
        if raw_start_index is None or raw_start_index == 0:
            raise MPKParseError("Unable to locate the raw-assets section in the encrypted package.")

        previous_meta = MPK._decode_meta_if_possible(raw_entries[raw_start_index - 1], key_stream)
        if previous_meta is None:
            raise MPKParseError("Unable to decode the entry before raw-assets.")

        raw_start_offset = previous_meta[0] + previous_meta[1]
        MPK._apply_meta_hint(
            raw_entries[raw_start_index]["encrypted_meta"][:4],
            58,
            raw_start_offset,
            key_stream,
        )

        next_offset = MPK._decode_offset_if_possible(raw_entries[raw_start_index + 1], key_stream)
        if next_offset is None:
            raise MPKParseError("Unable to decode the second raw-assets offset.")
        raw_start_size = next_offset - raw_start_offset
        if raw_start_size <= 0:
            raise MPKParseError("Derived an invalid first raw-assets size.")
        MPK._apply_meta_hint(
            raw_entries[raw_start_index]["encrypted_meta"][4:],
            62,
            raw_start_size,
            key_stream,
        )

        length_60_index = next((index for index, entry in enumerate(raw_entries) if entry["name_length"] == 60), None)
        if length_60_index is None or length_60_index + 1 >= len(raw_entries):
            raise MPKParseError("Unable to locate a 60-byte raw-assets entry for key-stream recovery.")

        current_offset = MPK._decode_offset_if_possible(raw_entries[length_60_index], key_stream)
        next_offset = MPK._decode_offset_if_possible(raw_entries[length_60_index + 1], key_stream)
        if current_offset is None or next_offset is None:
            raise MPKParseError("Unable to decode a 60-byte raw-assets offset.")
        current_size = next_offset - current_offset
        if current_size <= 0:
            raise MPKParseError("Derived an invalid 60-byte raw-assets size.")
        MPK._apply_meta_hint(
            raw_entries[length_60_index]["encrypted_meta"][4:],
            64,
            current_size,
            key_stream,
        )

        missing_positions = [position for position in range(68) if position not in key_stream]
        if missing_positions:
            raise MPKParseError(f"Key-stream recovery is incomplete: missing {missing_positions}")

        return bytes(key_stream[position] for position in range(68))

    @staticmethod
    def _apply_name_hint(encrypted_name, plain_name, key_stream):
        for position, plain_byte in enumerate(plain_name.encode("utf-8")):
            key_byte = encrypted_name[position] ^ plain_byte
            existing = key_stream.get(position)
            if existing is not None and existing != key_byte:
                raise MPKParseError(f"Name key-stream conflict at position {position}")
            key_stream[position] = key_byte

    @staticmethod
    def _apply_meta_hint(encrypted_meta, key_start, plain_value, key_stream):
        for index, plain_byte in enumerate(struct.pack("<I", plain_value)):
            key_position = key_start + index
            key_byte = encrypted_meta[index] ^ plain_byte
            existing = key_stream.get(key_position)
            if existing is not None and existing != key_byte:
                raise MPKParseError(f"Meta key-stream conflict at position {key_position}")
            key_stream[key_position] = key_byte

    @staticmethod
    def _decode_name(encrypted_name, key_stream):
        raw_name = bytes(encrypted_name[index] ^ key_stream[index] for index in range(len(encrypted_name)))
        return raw_name.decode("utf-8")

    @staticmethod
    def _decode_name_prefix(encrypted_name, key_stream):
        chars = []
        for index in range(min(len(encrypted_name), len(key_stream))):
            if index not in key_stream:
                break
            chars.append(chr(encrypted_name[index] ^ key_stream[index]))
        return "".join(chars)

    @staticmethod
    def _decode_offset_if_possible(raw_entry, key_stream):
        name_length = raw_entry["name_length"]
        if any((name_length + index) not in key_stream for index in range(4)):
            return None
        offset_bytes = bytes(
            raw_entry["encrypted_meta"][index] ^ key_stream[name_length + index]
            for index in range(4)
        )
        return struct.unpack("<I", offset_bytes)[0]

    @staticmethod
    def _decode_meta(raw_entry, key_stream):
        meta_bytes = bytes(
            raw_entry["encrypted_meta"][index] ^ key_stream[raw_entry["name_length"] + index]
            for index in range(8)
        )
        return struct.unpack("<II", meta_bytes)

    @staticmethod
    def _decode_meta_if_possible(raw_entry, key_stream):
        name_length = raw_entry["name_length"]
        if any((name_length + index) not in key_stream for index in range(8)):
            return None
        return MPK._decode_meta(raw_entry, key_stream)

    @staticmethod
    def _validate_entries(entries, index_end, file_size):
        previous_end = None
        for entry in entries:
            if entry.offset + entry.data_size > file_size:
                raise MPKParseError(
                    f"entry {entry.index} points past end of file: offset={entry.offset}, size={entry.data_size}",
                )
            if entry.data_size > 0 and entry.offset < index_end:
                raise MPKParseError(
                    f"entry {entry.index} data overlaps with the index: offset={entry.offset}, "
                    f"index_end={index_end}",
                )
            if previous_end is not None and previous_end != entry.offset:
                raise MPKParseError(
                    f"entry {entry.index} breaks the sequential data layout: "
                    f"expected offset {previous_end}, got {entry.offset}",
                )
            previous_end = entry.offset + entry.data_size

    def set_version(self, version):
        self._version = version

    def insert_file(self, file, index=None):
        insert_at = len(self._files) if index is None else index
        self._files.insert(insert_at, file)

    def data(self, index):
        if index >= len(self._files):
            raise IndexError(index)

        file = self._files[index]
        if file.data is None:
            if file.data_size == 0:
                file.data = b""
            else:
                file.data = IOHelper.read_range(self._io, file.offset, file.data_size)

        return file.data

    def file(self, index):
        if index >= len(self._files):
            raise IndexError(index)

        file = self._files[index]
        return {
            "is_zip": False,
            "index": file.index,
            "offset": file.offset,
            "data_size": file.data_size,
            "name": file.name,
        }

    @property
    def files(self):
        return [i for i in range(len(self._files))]

    @property
    def package_info(self):
        return {
            "variant": self._package_variant,
            "version": self._version,
            "index_end": self._index_end,
            "header_metadata": self._header_metadata,
        }
