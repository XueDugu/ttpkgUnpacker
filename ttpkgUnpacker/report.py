import json
from collections import Counter
from pathlib import Path


def write_report(package_path, output_dir, package_info, unpacked_files, recovered_files=None):
    output_dir = Path(output_dir)
    recovered_files = recovered_files or {}
    report = {
        "package_path": str(package_path),
        "output_dir": str(output_dir),
        "package_variant": package_info["variant"],
        "version": package_info["version"],
        "file_count": len(unpacked_files),
        "total_unpacked_size": sum(file_info["data_size"] for file_info in unpacked_files),
        "header_metadata": package_info.get("header_metadata") or {},
        "entry_points": _entry_points(unpacked_files),
        "path_groups": _path_groups(unpacked_files),
        "extensions": _extension_summary(unpacked_files),
        "app_info": _extract_app_info(output_dir, package_info, unpacked_files),
        "recovered_files": _serialize_recovered_files(recovered_files),
        "notes": _build_notes(output_dir, package_info),
        "tree": _render_tree([file_info["name"] for file_info in unpacked_files]),
    }

    json_path = output_dir / "unpack-report.json"
    markdown_path = output_dir / "unpack-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")

    return {
        "json": json_path,
        "markdown": markdown_path,
        "summary": report,
    }


def _entry_points(unpacked_files):
    names = {file_info["name"] for file_info in unpacked_files}
    return [name for name in ("app-config.json", "game.json", "game.js", "main.js", "src/project.js", "src/settings.js") if name in names]


def _path_groups(unpacked_files):
    counts = Counter()
    for file_info in unpacked_files:
        parts = file_info["name"].split("/")
        if len(parts) == 1:
            counts["<root>"] += 1
        else:
            counts[parts[0]] += 1
    return dict(sorted(counts.items()))


def _extension_summary(unpacked_files):
    counts = Counter()
    for file_info in unpacked_files:
        suffix = Path(file_info["name"]).suffix.lower() or "<none>"
        counts[suffix] += 1
    return dict(sorted(counts.items()))


def _extract_app_info(output_dir, package_info, unpacked_files):
    app_config = _read_json_if_possible(output_dir / "app-config.json")
    if app_config is not None:
        page_info = app_config.get("page", {})
        entry_page = app_config.get("entryPagePath")
        entry_window = page_info.get(entry_page, {}).get("window", {}) if entry_page else {}
        app_name = entry_window.get("navigationBarTitleText") or app_config.get("window", {}).get("navigationBarTitleText")
        return {
            "app_name": app_name,
            "app_id": app_config.get("appId"),
            "entry_page": entry_page,
            "page_count": len(app_config.get("pages", [])),
            "subpackage_count": len(app_config.get("subPackages", [])),
            "is_micro_app": app_config.get("isMicroApp"),
        }

    game_config = _read_json_if_possible(output_dir / "game.json")
    if game_config is not None:
        return {
            "app_name": game_config.get("deviceOrientation"),
            "entry_page": None,
            "config_keys": sorted(game_config.keys()),
        }

    names = {file_info["name"] for file_info in unpacked_files}
    return {
        "app_name": None,
        "app_id": None,
        "entry_page": None,
        "page_count": None,
        "subpackage_count": None,
        "is_micro_app": None,
        "entry_scripts": [name for name in ("game.js", "main.js", "src/project.js", "src/settings.js") if name in names],
        "header_metadata": package_info.get("header_metadata") or {},
    }


def _read_json_if_possible(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _build_notes(output_dir, package_info):
    notes = []
    if package_info["variant"] == "ttks-encrypted":
        if _read_json_if_possible(output_dir / "app-config.json") is None:
            notes.append("This package uses a ttks-encrypted index. File names and offsets were decoded, but some payload files may still contain obfuscated data.")
    return notes


def _serialize_recovered_files(recovered_files):
    app_json = recovered_files.get("app_json")
    page_json_paths = recovered_files.get("page_json_paths", [])
    return {
        "app_json": str(app_json) if app_json else None,
        "page_json_count": recovered_files.get("page_json_count", 0),
        "page_json_paths": [str(path) for path in page_json_paths[:20]],
    }


def _render_markdown(report):
    lines = [
        "# Unpack Report",
        "",
        "## Summary",
        "",
        f"- Package: `{report['package_path']}`",
        f"- Output: `{report['output_dir']}`",
        f"- Variant: `{report['package_variant']}`",
        f"- Version: `{report['version']}`",
        f"- Files: `{report['file_count']}`",
        f"- Total unpacked size: `{report['total_unpacked_size']}` bytes",
        "",
        "## App Info",
        "",
    ]

    for key, value in report["app_info"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(
        [
            "",
            "## Entry Points",
            "",
        ],
    )
    for entry in report["entry_points"]:
        lines.append(f"- `{entry}`")

    lines.extend(
        [
            "",
            "## Groups",
            "",
        ],
    )
    for key, value in report["path_groups"].items():
        lines.append(f"- `{key}`: `{value}`")

    lines.extend(
        [
            "",
            "## Extensions",
            "",
        ],
    )
    for key, value in report["extensions"].items():
        lines.append(f"- `{key}`: `{value}`")

    if report["recovered_files"]["app_json"] or report["recovered_files"]["page_json_count"]:
        lines.extend(
            [
                "",
                "## Recovered Configs",
                "",
                f"- app_json: `{report['recovered_files']['app_json']}`",
                f"- page_json_count: `{report['recovered_files']['page_json_count']}`",
            ],
        )

    if report["header_metadata"]:
        lines.extend(
            [
                "",
                "## Header Metadata",
                "",
                "```json",
                json.dumps(report["header_metadata"], ensure_ascii=False, indent=2),
                "```",
            ],
        )

    if report["notes"]:
        lines.extend(
            [
                "",
                "## Notes",
                "",
            ],
        )
        for note in report["notes"]:
            lines.append(f"- {note}")

    lines.extend(
        [
            "",
            "## Tree",
            "",
            "```text",
            report["tree"],
            "```",
        ],
    )

    return "\n".join(lines) + "\n"


def _render_tree(file_names):
    tree = {}
    for file_name in sorted(file_names):
        node = tree
        parts = [part for part in file_name.split("/") if part]
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = None

    lines = []
    _append_tree(lines, tree, "")
    return "\n".join(lines)


def _append_tree(lines, node, prefix):
    items = sorted(node.items())
    for index, (name, child) in enumerate(items):
        connector = "\\-- " if index == len(items) - 1 else "|-- "
        lines.append(f"{prefix}{connector}{name}")
        if child is not None:
            child_prefix = "    " if index == len(items) - 1 else "|   "
            _append_tree(lines, child, prefix + child_prefix)
