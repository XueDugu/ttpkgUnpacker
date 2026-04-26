import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

from ttpkgUnpacker.model.mpk import MPK, MPKParseError
from ttpkgUnpacker.postprocess import recover_miniapp_configs
from ttpkgUnpacker.report import write_report

SUPPORTED_PACKAGE_SUFFIXES = (".ttpkg.js", ".sttpkg.js", ".ttpkg", ".pkg", ".spkg")


class Main:
    def __init__(self, argv):
        self._argv = argv

    def run(self):
        parser = argparse.ArgumentParser(
            description="Unpack Douyin mini-app packages from TPKG/ttpkg.js files.",
        )
        parser.add_argument(
            "targets",
            nargs="+",
            help="Package files or directories that contain package files.",
        )
        parser.add_argument(
            "-o",
            "--output-dir",
            help="Base directory used to store unpacked output.",
        )
        args = parser.parse_args(self._argv[1:])

        try:
            package_paths = self._collect_package_paths(args.targets)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        if not package_paths:
            print("No supported package files were found.", file=sys.stderr)
            return 1

        output_dirs = self._build_output_dirs(package_paths, args.output_dir)
        failures = 0
        for package_path in package_paths:
            output_dir = output_dirs[package_path]
            print(f"Loading: {package_path}")
            try:
                result = self.unpack_package(package_path, output_dir)
            except (MPKParseError, OSError, ValueError) as exc:
                failures += 1
                print(f"Failed: {package_path}: {exc}", file=sys.stderr)
                continue

            print(f"Unpacked {result['file_count']} files to: {output_dir}")
            print(f"Report: {result['report_paths']['markdown']}")

        if failures:
            print(f"Finished with {failures} failed package(s).", file=sys.stderr)
            return 1
        return 0

    def unpack_package(self, package_path, output_dir):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if self._looks_like_spkg5(package_path):
            return self._unpack_spkg5_bundle(package_path, output_dir)

        ttks = self._read_ttks_key_if_present(package_path)
        if ttks is not None:
            return self._unpack_ttks_with_node(
                package_path,
                output_dir,
                ttks,
                error=MPKParseError("ttks-encrypted package requested Node decrypt"),
            )

        with open(package_path, "rb") as package_io:
            mpk = MPK.load(package_io)
            unpacked_files = self._extract_mpk(mpk, output_dir)

        recovered_files = recover_miniapp_configs(output_dir)
        report_paths = write_report(
            package_path,
            output_dir,
            mpk.package_info,
            unpacked_files,
            recovered_files=recovered_files,
        )
        return {
            "file_count": len(unpacked_files),
            "report_paths": report_paths,
        }

    def _extract_mpk(self, mpk, output_dir):
        unpacked_files = []
        for index in mpk.files:
            file_info = mpk.file(index)
            file_name = file_info["name"] or f"unknown_{index}"
            destination = self._safe_output_path(output_dir, file_name)

            if file_name.endswith("/"):
                destination.mkdir(parents=True, exist_ok=True)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            with open(destination, "wb") as output_io:
                output_io.write(mpk.data(index))
            unpacked_files.append(file_info)
        return unpacked_files

    @staticmethod
    def _looks_like_spkg5(package_path: Path) -> bool:
        try:
            with open(package_path, "rb") as package_io:
                return package_io.read(5) == b"SPKG5"
        except OSError:
            return False

    @staticmethod
    def _read_ttks_key_if_present(package_path: Path):
        try:
            with open(package_path, "rb") as package_io:
                header = package_io.read(256)
        except OSError:
            return None

        if len(header) < 16 or header[:4] != b"TPKG":
            return None

        meta_len = int.from_bytes(header[12:16], "little")
        if meta_len <= 0 or meta_len > 1024 * 1024:
            return None

        try:
            with open(package_path, "rb") as package_io:
                package_io.seek(16)
                meta_raw = package_io.read(meta_len)
        except OSError:
            return None

        if not meta_raw.startswith(b"JSON{"):
            return None
        try:
            meta = json.loads(meta_raw[4:].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        ttks = meta.get("__ttks")
        if isinstance(ttks, str) and re.fullmatch(r"[0-9a-fA-F]{32}", ttks):
            return ttks
        return None

    def _unpack_ttks_with_node(self, package_path: Path, output_dir: Path, ttks: str, error: Exception):
        node_tools_dir = Path(__file__).resolve().parents[2] / "node_tools"
        script_path = node_tools_dir / "ttks_unpack.js"
        if not script_path.exists():
            raise MPKParseError(f"ttks fallback requested but Node script is missing: {script_path}") from error

        node_path = shutil.which("node")
        if node_path is None:
            raise MPKParseError(
                "This package uses '__ttks' encryption and requires Node.js to unpack. "
                "Install Node.js or provide a plain TPKG package instead."
            ) from error

        try:
            proc = subprocess.run(
                [node_path, str(script_path), str(package_path), str(output_dir)],
                cwd=str(node_tools_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise MPKParseError(f"Failed to run Node ttks unpacker: {exc}") from error

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            stdout = (proc.stdout or "").strip()
            details = stderr or stdout or f"exit={proc.returncode}"
            raise MPKParseError(f"Node ttks unpacker failed: {details}") from error

        unpacked_files = self._scan_output_files(output_dir)
        recovered_files = recover_miniapp_configs(output_dir)
        report_paths = write_report(
            package_path,
            output_dir,
            {
                "variant": "ttks-encrypted",
                "version": 2,
                "index_end": None,
                "header_metadata": {"__ttks": ttks},
            },
            unpacked_files,
            recovered_files=recovered_files,
        )
        return {
            "file_count": len(unpacked_files),
            "report_paths": report_paths,
        }

    @staticmethod
    def _scan_output_files(output_dir: Path):
        unpacked = []
        base = output_dir.resolve()
        index = 0
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(base).as_posix()
            if rel in ("unpack-report.json", "unpack-report.md"):
                continue
            unpacked.append(
                {
                    "is_zip": False,
                    "index": index,
                    "offset": None,
                    "data_size": path.stat().st_size,
                    "name": rel,
                }
            )
            index += 1
        return unpacked

    def _unpack_spkg5_bundle(self, package_path: Path, output_dir: Path):
        base_dir = package_path.with_suffix("")
        meta_path = base_dir / "_.meta"
        if not meta_path.exists():
            meta_path = Path(str(package_path) + ".meta")
        if not meta_path.exists():
            raise MPKParseError(
                "SPKG5 detected, but no meta file was found. "
                f"Expected {base_dir / '_.meta'} or {package_path}.meta"
            )
        if not base_dir.is_dir():
            raise MPKParseError(
                "SPKG5 detected, but the sibling package directory is missing. "
                f"Expected directory: {base_dir}"
            )

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta_data = meta.get("data") if isinstance(meta, dict) else None
        if not isinstance(meta_data, dict):
            raise MPKParseError(f"Invalid meta file format: {meta_path}")

        pkg_files = self._resolve_spkg5_package_files(meta_data, base_dir)
        if not pkg_files:
            raise MPKParseError(f"SPKG5 meta resolved to no .pkg files under: {base_dir}")

        for pkg_path in pkg_files:
            # Merge all packages into a single output tree.
            ttks = self._read_ttks_key_if_present(pkg_path)
            if ttks is not None:
                self._unpack_ttks_with_node(pkg_path, output_dir, ttks, error=MPKParseError("ttks fallback"))
                continue

            with open(pkg_path, "rb") as package_io:
                mpk = MPK.load(package_io)
                self._extract_mpk(mpk, output_dir)

        unpacked_files = self._scan_output_files(output_dir)
        recovered_files = recover_miniapp_configs(output_dir)
        report_paths = write_report(
            package_path,
            output_dir,
            {
                "variant": "spkg5-bundle",
                "version": 5,
                "index_end": None,
                "header_metadata": {
                    "meta_appid": meta_data.get("appid"),
                    "meta_version": meta_data.get("version"),
                    "meta_version_code": meta_data.get("version_code"),
                    "meta_path": str(meta_path),
                    "package_dir": str(base_dir),
                    "pkg_files": [str(p) for p in pkg_files],
                },
            },
            unpacked_files,
            recovered_files=recovered_files,
        )
        return {
            "file_count": len(unpacked_files),
            "report_paths": report_paths,
        }

    @staticmethod
    def _resolve_spkg5_package_files(meta_data: dict, base_dir: Path):
        import hashlib

        candidates = sorted(base_dir.glob("*.pkg"))
        if not candidates:
            return []

        md5_by_path = {}
        for path in candidates:
            digest = hashlib.md5(path.read_bytes()).hexdigest()
            md5_by_path[path] = digest

        resolved = []

        packages = meta_data.get("packages")
        if isinstance(packages, dict):
            for key, info in packages.items():
                if not isinstance(info, dict):
                    continue
                tos_path = info.get("tosPath") or ""
                prefix = tos_path.split(".")[0]
                if len(prefix) < 7:
                    continue
                tail = prefix[-7:].lower()
                matches = [p for p, md5hex in md5_by_path.items() if md5hex.startswith(tail)]
                if matches:
                    resolved.append(matches[0])

        plugins = meta_data.get("plugins")
        if isinstance(plugins, list):
            for plugin in plugins:
                if not isinstance(plugin, dict):
                    continue
                paths = plugin.get("path")
                if not isinstance(paths, list) or not paths:
                    continue
                url = str(paths[0])
                # .../<hex>.sttpkg.js?...
                name = url.split("?")[0].rstrip("/").split("/")[-1]
                hex_prefix = name.split(".")[0]
                if not re.fullmatch(r"[0-9a-fA-F]{16,32}", hex_prefix):
                    continue
                matches = [p for p, md5hex in md5_by_path.items() if md5hex.startswith(hex_prefix.lower())]
                if matches:
                    resolved.append(matches[0])

        # Keep stable order, remove dups.
        seen = set()
        unique = []
        for path in resolved:
            if path in seen:
                continue
            seen.add(path)
            unique.append(path)
        return unique

    def _build_output_dirs(self, package_paths, base_output_dir):
        if not base_output_dir:
            return {package_path: Path(f"{package_path}_unpack") for package_path in package_paths}

        base_output_dir = Path(base_output_dir).expanduser().resolve()
        name_counts = Counter(package_path.name for package_path in package_paths)
        output_dirs = {}

        for package_path in package_paths:
            if name_counts[package_path.name] == 1:
                output_dirs[package_path] = base_output_dir / f"{package_path.name}_unpack"
                continue

            digest = hashlib.sha1(str(package_path.resolve()).encode("utf-8")).hexdigest()[:8]
            parent_label = package_path.parent.name or "root"
            output_dirs[package_path] = base_output_dir / f"{parent_label}_{package_path.name}_unpack_{digest}"

        return output_dirs

    def _collect_package_paths(self, targets):
        discovered = []
        seen = set()

        for target in targets:
            path = Path(target).expanduser()
            if not path.exists():
                raise FileNotFoundError(f"Path does not exist: {path}")

            if path.is_file():
                resolved = path.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    discovered.append(resolved)
                continue

            for candidate in sorted(path.rglob("*")):
                if not candidate.is_file() or not self._is_supported_package(candidate):
                    continue
                resolved = candidate.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                discovered.append(resolved)

        return discovered

    @staticmethod
    def _is_supported_package(path):
        return path.name.endswith(SUPPORTED_PACKAGE_SUFFIXES)

    @staticmethod
    def _safe_output_path(output_dir, file_name):
        normalized_name = file_name.replace("\\", "/")
        parts = [part for part in normalized_name.split("/") if part not in ("", ".")]

        if normalized_name.startswith("/") or any(part == ".." for part in parts):
            raise ValueError(f"Unsafe file path inside package: {file_name}")

        if not parts:
            raise ValueError("Package entry resolved to an empty path.")

        base_path = Path(output_dir).resolve()
        destination = base_path.joinpath(*parts).resolve()

        if os.path.commonpath([str(base_path), str(destination)]) != str(base_path):
            raise ValueError(f"Unsafe file path inside package: {file_name}")

        return destination
