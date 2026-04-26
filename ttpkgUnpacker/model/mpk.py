import hashlib
import json
import os
import re
import shutil
import string
import struct
import subprocess
from dataclasses import dataclass
from io import SEEK_END, BytesIO
from typing import Dict, List, Optional, Sequence, Tuple

from ttpkgUnpacker.util.io_helper import IOHelper

MPK_MAGIC = b"TPKG"
SPKG_MAGIC = b"SPKG"
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

TTKS_GAMEASSETS_HINT_SEQUENCE = (
    "gameAssets/asset/config/gameLevData.json",
    "gameAssets/asset/config/gameLevReward.json",
    "gameAssets/asset/config/netConfig.json",
    "gameAssets/asset/config/prefabResConfigPath.json",
    "gameAssets/asset/config/trollLevData.json",
    "gameAssets/asset/config/trollSkillData.json",
    "gameAssets/asset/data/config.json",
    "gameAssets/asset/data/equipmentData.json",
    "gameAssets/asset/data/mapsData.json",
    "gameAssets/asset/devil1.ani",
    "gameAssets/asset/diceAni.ani",
    "gameAssets/asset/diceAni2.ani",
    "gameAssets/asset/diceAni3.ani",
    "gameAssets/asset/diceAni4.ani",
)

TTKS_ALLOWED_NAME_BYTES = set((string.ascii_letters + string.digits + "/_.-").encode("ascii"))
TTKS_KNOWN_EXTENSIONS = {
    "js",
    "json",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "atlas",
    "ani",
    "skel",
    "plist",
    "ttf",
    "fnt",
    "mp3",
    "wav",
    "ogg",
    "txt",
    "dat",
    "bin",
    "pvr",
    "ktx",
    "astc",
    "pmg",
    "awlbs",
}

_TTKS_KEY_CACHE: Dict[str, List[int]] = {}


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
        if magic == SPKG_MAGIC:
            return MPK._load_spkg(io, file_size)

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
    def _spkg_guess_app_id(io):
        package_name = getattr(io, "name", None)
        if not package_name:
            return None

        base_name = os.path.basename(package_name)
        match = re.match(r"(?:app_)?([0-9A-Za-z]+)\.(?:spkg|pkg)$", base_name)
        if match:
            return match.group(1)

        match = re.search(r"appid_([0-9A-Za-z]+)", package_name)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _spkg_describe_sibling_meta(io):
        package_name = getattr(io, "name", None)
        if not package_name:
            return None

        base_path, _ = os.path.splitext(package_name)
        candidates = [
            base_path + ".meta",
            base_path + ".smeta",
            package_name + ".meta",
        ]

        for candidate in candidates:
            if not os.path.exists(candidate):
                continue
            try:
                with open(candidate, "rb") as meta_io:
                    sample = meta_io.read(256)
            except OSError:
                continue

            if not sample:
                return {
                    "path": candidate,
                    "preview": "<empty>",
                }

            if sample.startswith(b"{"):
                preview = sample[:200].decode("utf-8", errors="replace")
            else:
                preview = sample[:32].hex()

            return {
                "path": candidate,
                "preview": preview,
            }

        return None

    @staticmethod
    def _spkg_zstd_decompress(payload: bytes) -> bytes:
        try:
            import zstandard as zstd
        except ImportError:
            zstd_path = shutil.which("zstd")
            if zstd_path is None:
                raise MPKParseError(
                    "SPKG packages require zstd decompression. "
                    "Install either the 'zstandard' Python package (pip install zstandard) "
                    "or the 'zstd' command line tool."
                )

            try:
                proc = subprocess.run(
                    [zstd_path, "-d", "--stdout"],
                    input=payload,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
            except OSError as exc:
                raise MPKParseError(f"Failed to run {zstd_path!r} for SPKG decompression") from exc

            if proc.returncode != 0:
                stderr = proc.stderr.decode("utf-8", errors="replace").strip()
                raise MPKParseError(f"zstd decompression failed (exit={proc.returncode}): {stderr}")

            return proc.stdout

        reader = zstd.ZstdDecompressor().stream_reader(BytesIO(payload))
        chunks = []
        try:
            while True:
                chunk = reader.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            reader.close()

        return b"".join(chunks)

    @staticmethod
    def _load_spkg(io, file_size):
        # SPKG header reference: Douyin IDE sttpkg (SPKG v1, type=3)
        version = IOHelper.read_struct(io, "<I")[0]
        if version != 1:
            header_preview = IOHelper.read_range(io, 0, min(file_size, 64))
            preview_hex = header_preview[:16].hex()

            details = f"version={version} (u32le after magic), file_size={file_size}, header16={preview_hex}"

            if header_preview.startswith(b"SPKG5") and len(header_preview) >= 44:
                u24_value = int.from_bytes(header_preview[5:8], "little")
                flags = int.from_bytes(header_preview[8:12], "little")
                key1_hex = header_preview[12:28].hex()
                key2_hex = header_preview[28:44].hex()
                details += (
                    f"; magic5='SPKG5', u24={u24_value}, flags={flags}, "
                    f"key1={key1_hex}, key2={key2_hex}"
                )

            meta_info = MPK._spkg_describe_sibling_meta(io)
            if meta_info is not None:
                details += f"; sibling_meta={meta_info['path']}, meta_preview={meta_info['preview']!r}"

            raise MPKParseError(
                "Unsupported SPKG variant. "
                + details
                + ". If this file came from Douyin launchcache, it may require additional metadata (e.g. a .meta file) to decrypt."
            )

        spkg_type = IOHelper.read_struct(io, "<H")[0]
        if spkg_type != 3:
            raise MPKParseError(f"Unsupported SPKG type: {spkg_type}")

        meta_len = IOHelper.read_struct(io, "<H")[0]
        encrypted = meta_len > 0
        timestamp = None

        if encrypted:
            # meta format: u16 string_len, b"SA", ascii timestamp
            string_len = IOHelper.read_struct(io, "<H")[0]
            marker = IOHelper.read_exact(io, 2)
            if marker != b"SA":
                raise MPKParseError(f"Unsupported SPKG metadata marker: {marker!r}")
            ts_raw = IOHelper.read_exact(io, string_len)
            try:
                timestamp = ts_raw.decode("ascii")
            except UnicodeDecodeError as exc:
                raise MPKParseError("SPKG metadata timestamp is not ASCII") from exc

            expected_meta_len = string_len + 4
            if meta_len != expected_meta_len:
                raise MPKParseError(
                    f"SPKG metadata length mismatch: meta_len={meta_len}, expected={expected_meta_len}"
                )

        payload = io.read()
        if not payload:
            raise MPKParseError("SPKG payload is empty")

        if encrypted:
            app_id = MPK._spkg_guess_app_id(io)
            if not app_id:
                raise MPKParseError(
                    "Encrypted SPKG package detected, but appId could not be inferred from the file path. "
                    "Rename the file to app_<appid>.spkg or ensure the path contains appid_<appid>."
                )

            # Derive 32-byte key used by the upstream packer (sha256(appId + timestamp)).
            key = hashlib.sha256((app_id + timestamp).encode("utf-8")).digest()
            raise MPKParseError(
                "Encrypted SPKG packages are not supported yet. "
                f"Derived key sha256(appId+timestamp)={key.hex()} (appId={app_id}, timestamp={timestamp})."
            )

        inner = MPK._spkg_zstd_decompress(payload)
        mpk = MPK.load(BytesIO(inner))
        # annotate wrapper info
        mpk._header_metadata = {
            **getattr(mpk, "_header_metadata", {}),
            "spkg": {
                "version": version,
                "type": spkg_type,
                "encrypted": encrypted,
                "timestamp": timestamp,
            },
        }
        return mpk

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
            if name_length <= 0 or name_length > MAX_ENTRY_NAME_LENGTH:
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
        try:
            key_stream = MPK._derive_ttks_key_stream(raw_entries, file_size, index_end, header["metadata"])
        except MPKParseError:
            if count != 1:
                raise

            raw_entry = raw_entries[0]
            entries = [
                MPKEntry(
                    index=0,
                    offset=index_end,
                    data_size=file_size - index_end,
                    name=f"unknown_{raw_entry['encrypted_name'].hex()}",
                )
            ]
            MPK._validate_entries(entries, index_end, file_size)
            return entries, index_end, header["metadata"]
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
    def _derive_ttks_key_stream_cocos_template(raw_entries):
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
    def _derive_ttks_key_stream(raw_entries, file_size, index_end, metadata):
        ttks = metadata.get("__ttks") if isinstance(metadata, dict) else None
        max_name_length = max(entry["name_length"] for entry in raw_entries)
        key_len = max_name_length + 8

        key_stream = [None] * key_len
        key_source = [None] * key_len

        if ttks and ttks in _TTKS_KEY_CACHE:
            cached = _TTKS_KEY_CACHE[ttks]
            for position, value in enumerate(cached[:key_len]):
                key_stream[position] = value
                key_source[position] = "cache"

        def set_key(position: int, value: int, source: str) -> bool:
            existing = key_stream[position]
            if existing is None:
                key_stream[position] = value
                key_source[position] = source
                return True

            if existing == value:
                if key_source[position] == "heuristic" and source == "meta":
                    key_source[position] = "meta"
                return False

            if key_source[position] == "heuristic" and source == "meta":
                key_stream[position] = value
                key_source[position] = source
                return True

            raise MPKParseError(
                f"Key-stream conflict at position {position}: "
                f"{existing:#x} ({key_source[position]}) vs {value:#x} ({source})",
            )

        def apply_name_hint(encrypted_name: bytes, plain_name: str, source: str) -> None:
            plain_bytes = plain_name.encode("utf-8")
            if len(encrypted_name) != len(plain_bytes):
                raise MPKParseError(
                    f"Encrypted package template mismatch: expected length {len(plain_bytes)}, got {len(encrypted_name)}"
                )
            for position, plain_byte in enumerate(plain_bytes):
                set_key(position, encrypted_name[position] ^ plain_byte, source)

        try:
            MPK._try_apply_gameassets_hints(raw_entries, apply_name_hint)

            # Seed from the classic TTKS template (older Cocos mini-game layouts) when it matches.
            for index, expected_name in TTKS_NAME_HINTS.items():
                if index >= len(raw_entries):
                    break
                raw_entry = raw_entries[index]
                if raw_entry["name_length"] != len(expected_name):
                    break
                apply_name_hint(raw_entry["encrypted_name"], expected_name, "name-hint")

            seeded = any(
                key_stream[position] is not None and key_source[position] in ("cache", "name-hint")
                for position in range(max_name_length)
            )
            if not seeded:
                MPK._fill_ttks_name_key_bytes(raw_entries, max_name_length, key_stream, key_source, set_key)

            MPK._solve_ttks_meta_key_bytes(
                raw_entries,
                file_size,
                index_end,
                key_stream,
                key_source,
                set_key,
            )

            MPK._fill_ttks_missing_name_key_bytes_with_extensions(
                raw_entries,
                max_name_length,
                key_stream,
                key_source,
                set_key,
            )

            missing_positions = [position for position, value in enumerate(key_stream) if value is None]
            if missing_positions:
                raise MPKParseError(f"Key-stream recovery is incomplete: missing {missing_positions}")

            key_bytes = bytes(value for value in key_stream if value is not None)
        except MPKParseError as exc:
            # Fall back to the historical template recovery when the generic solver cannot recover.
            if max_name_length <= 68:
                key_bytes = MPK._derive_ttks_key_stream_cocos_template(raw_entries)
            else:
                raise

        if ttks:
            cached = _TTKS_KEY_CACHE.get(ttks)
            if cached is None or len(cached) < len(key_bytes):
                _TTKS_KEY_CACHE[ttks] = list(key_bytes)
            else:
                for position, value in enumerate(key_bytes):
                    if cached[position] != value:
                        raise MPKParseError(
                            f"Cached key-stream mismatch at position {position}: {cached[position]:#x} vs {value:#x}"
                        )

        return key_bytes

    @staticmethod
    def _try_apply_gameassets_hints(raw_entries: Sequence[dict], apply_name_hint) -> bool:
        sequence = TTKS_GAMEASSETS_HINT_SEQUENCE
        lengths = [len(name) for name in sequence]
        candidate_count = len(sequence)
        if len(raw_entries) < candidate_count:
            return False

        for start in range(len(raw_entries) - candidate_count + 1):
            if any(raw_entries[start + offset]["name_length"] != lengths[offset] for offset in range(candidate_count)):
                continue
            try:
                for offset, plain_name in enumerate(sequence):
                    apply_name_hint(raw_entries[start + offset]["encrypted_name"], plain_name, "name-hint")
            except MPKParseError:
                continue
            return True

        return False

    @staticmethod
    def _fill_ttks_name_key_bytes(raw_entries, max_name_length, key_stream, key_source, set_key):
        for position in range(max_name_length):
            if key_stream[position] is not None:
                continue

            samples = [entry["encrypted_name"][position] for entry in raw_entries if entry["name_length"] > position]
            if not samples:
                continue

            best_key = None
            best_score = -10**9
            for candidate in range(256):
                score = 0
                for cipher_byte in samples:
                    plain_byte = cipher_byte ^ candidate
                    if plain_byte in TTKS_ALLOWED_NAME_BYTES:
                        score += 2
                    elif 0x20 <= plain_byte <= 0x7E:
                        score += 0
                    else:
                        score -= 3
                if score > best_score:
                    best_score = score
                    best_key = candidate

            if best_key is None:
                continue
            set_key(position, best_key, "heuristic")

    @staticmethod
    def _solve_ttks_meta_key_bytes(
        raw_entries: Sequence[dict],
        file_size: int,
        index_end: int,
        key_stream,
        key_source,
        set_key,
    ) -> Tuple[list, list]:
        count = len(raw_entries)
        offsets = [None] * count
        sizes = [None] * count

        def decode_u32(enc_bytes: bytes, start: int) -> Optional[int]:
            if start + 4 > len(key_stream):
                return None
            if any(key_stream[start + i] is None for i in range(4)):
                return None
            raw = bytes(enc_bytes[i] ^ key_stream[start + i] for i in range(4))
            return struct.unpack("<I", raw)[0]

        def apply_u32(enc_bytes: bytes, start: int, plain_value: int) -> bool:
            plain = struct.pack("<I", plain_value)
            changed = False
            for i, plain_byte in enumerate(plain):
                changed |= set_key(start + i, enc_bytes[i] ^ plain_byte, "meta")
            return changed

        def attempt_gap_solve() -> bool:
            changed = False
            for index in range(count - 2):
                if offsets[index] is None or offsets[index + 2] is None or offsets[index + 1] is not None:
                    continue

                start_offset = offsets[index]
                end_offset = offsets[index + 2]
                if end_offset < start_offset:
                    continue

                gap = end_offset - start_offset
                if gap > 1_000_000:
                    continue

                entry_a = raw_entries[index]
                entry_b = raw_entries[index + 1]

                for candidate_offset in range(start_offset, end_offset + 1):
                    size_a = candidate_offset - start_offset
                    size_b = end_offset - candidate_offset

                    if sizes[index] is not None and sizes[index] != size_a:
                        continue
                    if sizes[index + 1] is not None and sizes[index + 1] != size_b:
                        continue

                    staged: Dict[int, int] = {}

                    def stage(enc_bytes: bytes, start: int, plain_value: int) -> bool:
                        plain = struct.pack("<I", plain_value)
                        for i, plain_byte in enumerate(plain):
                            pos = start + i
                            val = enc_bytes[i] ^ plain_byte
                            staged_existing = staged.get(pos)
                            if staged_existing is not None and staged_existing != val:
                                return False
                            existing = key_stream[pos]
                            if existing is not None and existing != val and key_source[pos] != "heuristic":
                                return False
                            staged[pos] = val
                        return True

                    if not stage(entry_a["encrypted_meta"][4:], entry_a["name_length"] + 4, size_a):
                        continue
                    if not stage(entry_b["encrypted_meta"][:4], entry_b["name_length"], candidate_offset):
                        continue
                    if not stage(entry_b["encrypted_meta"][4:], entry_b["name_length"] + 4, size_b):
                        continue

                    for pos, val in staged.items():
                        set_key(pos, val, "meta")

                    offsets[index + 1] = candidate_offset
                    sizes[index] = size_a
                    sizes[index + 1] = size_b
                    changed = True
                    break

            return changed

        for _ in range(200):
            changed = False

            for entry in raw_entries:
                index = entry["index"]
                offset = decode_u32(entry["encrypted_meta"][:4], entry["name_length"])
                if offset is not None and index_end <= offset <= file_size:
                    if offsets[index] != offset:
                        offsets[index] = offset
                        changed = True

                size = decode_u32(entry["encrypted_meta"][4:], entry["name_length"] + 4)
                if size is not None and 0 <= size <= file_size:
                    if offsets[index] is not None and offsets[index] + size > file_size:
                        continue
                    if sizes[index] != size:
                        sizes[index] = size
                        changed = True

            for index in range(count - 1):
                if offsets[index] is not None and sizes[index] is not None:
                    expected_offset = offsets[index] + sizes[index]
                    if expected_offset < index_end or expected_offset > file_size:
                        continue

                    if offsets[index + 1] is None:
                        offsets[index + 1] = expected_offset
                        changed |= apply_u32(
                            raw_entries[index + 1]["encrypted_meta"][:4],
                            raw_entries[index + 1]["name_length"],
                            expected_offset,
                        )
                    elif offsets[index + 1] != expected_offset:
                        expected_size = offsets[index + 1] - offsets[index]
                        if expected_size < 0 or expected_size > file_size:
                            continue
                        sizes[index] = expected_size
                        changed |= apply_u32(
                            raw_entries[index]["encrypted_meta"][4:],
                            raw_entries[index]["name_length"] + 4,
                            expected_size,
                        )

                if offsets[index] is not None and offsets[index + 1] is not None and sizes[index] is None:
                    expected_size = offsets[index + 1] - offsets[index]
                    if expected_size < 0 or expected_size > file_size:
                        continue
                    sizes[index] = expected_size
                    changed |= apply_u32(
                        raw_entries[index]["encrypted_meta"][4:],
                        raw_entries[index]["name_length"] + 4,
                        expected_size,
                    )

            if offsets[-1] is not None and sizes[-1] is None:
                expected_last_size = file_size - offsets[-1]
                if expected_last_size < 0 or expected_last_size > file_size:
                    raise MPKParseError("Derived an invalid last entry size.")
                sizes[-1] = expected_last_size
                changed |= apply_u32(
                    raw_entries[-1]["encrypted_meta"][4:],
                    raw_entries[-1]["name_length"] + 4,
                    expected_last_size,
                )

            if any(value is None for value in offsets) and attempt_gap_solve():
                changed = True

            if not changed:
                break

        return offsets, sizes

    @staticmethod
    def _fill_ttks_missing_name_key_bytes_with_extensions(
        raw_entries,
        max_name_length: int,
        key_stream,
        key_source,
        set_key,
    ) -> None:
        for position in range(max_name_length):
            if key_stream[position] is not None:
                continue

            candidates = [entry for entry in raw_entries if entry["name_length"] > position]
            if not candidates:
                continue

            best_key = None
            best_score = -10**9
            for key_byte in range(256):
                score = 0
                for entry in candidates:
                    plain_byte = entry["encrypted_name"][position] ^ key_byte
                    if plain_byte in TTKS_ALLOWED_NAME_BYTES:
                        score += 2
                    elif 0x20 <= plain_byte <= 0x7E:
                        score += 0
                    else:
                        score -= 5

                    # Extension bonus when this is the last remaining unknown key byte in the name.
                    if any(
                        key_stream[pos] is None and pos != position
                        for pos in range(entry["name_length"])
                    ):
                        continue

                    decoded = bytes(
                        (
                            entry["encrypted_name"][pos]
                            ^ (key_byte if pos == position else key_stream[pos])
                        )
                        for pos in range(entry["name_length"])
                    ).decode("utf-8", errors="replace")

                    dot_index = decoded.rfind(".")
                    if dot_index != -1 and decoded[dot_index + 1 :] in TTKS_KNOWN_EXTENSIONS:
                        score += 50

                if score > best_score:
                    best_score = score
                    best_key = key_byte

            if best_key is None:
                continue

            set_key(position, best_key, "heuristic")

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
