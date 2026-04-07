import json
from pathlib import Path


RUNTIME_ONLY_APP_CONFIG_KEYS = {
    "appId",
    "entryPagePath",
    "global",
    "industrySDK",
    "industrySDKPages",
    "isMicroApp",
    "page",
    "usePrivacyCheck",
}


def recover_miniapp_configs(output_dir):
    output_dir = Path(output_dir)
    app_config_path = output_dir / "app-config.json"
    if not app_config_path.exists():
        return {
            "app_json": None,
            "page_json_count": 0,
            "page_json_paths": [],
        }

    try:
        app_config = json.loads(app_config_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {
            "app_json": None,
            "page_json_count": 0,
            "page_json_paths": [],
        }

    recovered_app_json = _build_app_json(app_config)
    app_json_path = output_dir / "app.json"
    if not app_json_path.exists():
        app_json_path.write_text(
            json.dumps(recovered_app_json, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    page_json_paths = []
    for page_path, page_config in sorted(app_config.get("page", {}).items()):
        destination = output_dir / f"{page_path}.json"
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(page_config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        page_json_paths.append(destination)

    return {
        "app_json": app_json_path,
        "page_json_count": len(page_json_paths),
        "page_json_paths": page_json_paths,
    }


def _build_app_json(app_config):
    recovered = dict(app_config)
    global_window = recovered.get("global", {}).get("window")
    if global_window and "window" not in recovered:
        recovered["window"] = global_window

    for key in RUNTIME_ONLY_APP_CONFIG_KEYS:
        recovered.pop(key, None)

    empty_keys = [
        key
        for key, value in recovered.items()
        if value in ("", [], False) or (isinstance(value, dict) and not value)
    ]
    for key in empty_keys:
        recovered.pop(key, None)

    return recovered
