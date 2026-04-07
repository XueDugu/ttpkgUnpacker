import argparse
import hashlib
import os
import sys
from collections import Counter
from pathlib import Path

from ttpkgUnpacker.model.mpk import MPK, MPKParseError
from ttpkgUnpacker.postprocess import recover_miniapp_configs
from ttpkgUnpacker.report import write_report

SUPPORTED_PACKAGE_SUFFIXES = (".ttpkg.js", ".ttpkg", ".pkg")


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

        with open(package_path, "rb") as package_io:
            mpk = MPK.load(package_io)
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
