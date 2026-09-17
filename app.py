import os
import re
import uuid
from typing import Any

import requests
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

API_BASE = "https://openapi.api.govee.com/router/api/v1"
API_KEY = os.getenv("GOVEE_API_KEY", "").strip()
REQUEST_TIMEOUT = 10
AVAILABLE_VIEWS = ("pipboy", "lcars")
VIEW = os.getenv("VIEW", "pipboy").strip().casefold()
VISIBLE_DEVICE_NAMES = {
    "ceilingliving1",
    "sleepingroom",
    "tvslaapkamer",
}


def headers() -> dict[str, str]:
    if not API_KEY:
        raise RuntimeError("GOVEE_API_KEY is not configured")
    return {
        "Content-Type": "application/json",
        "Govee-API-Key": API_KEY,
    }


def govee_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    response = requests.request(
        method,
        f"{API_BASE}{path}",
        headers=headers(),
        timeout=REQUEST_TIMEOUT,
        **kwargs,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("code") not in (None, 200):
        raise RuntimeError(
            data.get("msg")
            or data.get("message")
            or "Govee API returned an error"
        )
    return data


def get_devices() -> list[dict[str, Any]]:
    data = govee_request("GET", "/user/devices")
    return data.get("data", [])


def supports_power(device: dict[str, Any]) -> bool:
    return any(
        capability.get("type") == "devices.capabilities.on_off"
        and capability.get("instance") == "powerSwitch"
        for capability in device.get("capabilities", [])
    )


def supports_color(device: dict[str, Any]) -> bool:
    return any(
        capability.get("type") == "devices.capabilities.color_setting"
        and capability.get("instance") == "colorRgb"
        for capability in device.get("capabilities", [])
    )


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def compatible_devices() -> list[dict[str, Any]]:
    return [device for device in get_devices() if supports_power(device)]


def dashboard_devices() -> list[dict[str, Any]]:
    devices = [
        device
        for device in compatible_devices()
        if normalize_name(str(device.get("deviceName", ""))) in VISIBLE_DEVICE_NAMES
    ]
    order = {"ceilingliving1": 0, "sleepingroom": 1, "tvslaapkamer": 2}
    return sorted(
        devices,
        key=lambda device: order.get(normalize_name(str(device.get("deviceName", ""))), 99),
    )


def find_device(device_id: str, sku: str) -> dict[str, Any]:
    for device in dashboard_devices():
        if device.get("device") == device_id and device.get("sku") == sku:
            return device
    raise RuntimeError("The selected device was not found in the LCARS dashboard")


def send_capability(
    device_id: str, sku: str, capability_type: str, instance: str, value: Any
) -> dict[str, Any]:
    device = find_device(device_id, sku)
    payload = {
        "requestId": str(uuid.uuid4()),
        "payload": {
            "sku": device["sku"],
            "device": device["device"],
            "capability": {
                "type": capability_type,
                "instance": instance,
                "value": value,
            },
        },
    }
    result = govee_request("POST", "/device/control", json=payload)
    return {"device": device, "result": result}


def set_power(device_id: str, sku: str, value: int) -> dict[str, Any]:
    return send_capability(
        device_id, sku, "devices.capabilities.on_off", "powerSwitch", value
    )


def set_color(device_id: str, sku: str, value: int) -> dict[str, Any]:
    device = find_device(device_id, sku)
    if not supports_color(device):
        raise RuntimeError(
            f"{device.get('deviceName', 'This device')} does not support colour"
        )
    return send_capability(
        device_id, sku, "devices.capabilities.color_setting", "colorRgb", value
    )


def parse_hex_colour(value: str) -> int:
    """Turn '#rrggbb' into the single integer Govee expects (0-16777215)."""
    match = re.fullmatch(r"#?([0-9a-fA-F]{6})", value.strip())
    if not match:
        raise ValueError("colour must be a hex value such as #33ff66")
    return int(match.group(1), 16)


@app.after_request
def disable_browser_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/")
def index():
    if VIEW not in AVAILABLE_VIEWS:
        return (
            f"Unknown VIEW {VIEW!r}. Expected one of: {', '.join(AVAILABLE_VIEWS)}",
            500,
        )
    return render_template(f"{VIEW}.html")


@app.get("/api/devices")
def device_info():
    try:
        devices = dashboard_devices()
        return jsonify(
            ok=True,
            devices=[
                {
                    "name": device.get("deviceName", device.get("sku", "Govee device")),
                    "sku": device.get("sku"),
                    "id": device.get("device"),
                    "color": supports_color(device),
                }
                for device in devices
            ],
        )
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 500


@app.post("/api/power")
def power():
    body = request.get_json(silent=True) or {}
    state = body.get("state")
    device_id = str(body.get("device", "")).strip()
    sku = str(body.get("sku", "")).strip()

    if state not in ("on", "off"):
        return jsonify(ok=False, error="state must be 'on' or 'off'"), 400
    if not device_id or not sku:
        return jsonify(ok=False, error="device and sku are required"), 400

    try:
        result = set_power(device_id, sku, 1 if state == "on" else 0)
        return jsonify(ok=True, state=state, device=result["device"].get("deviceName"))
    except requests.HTTPError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        return jsonify(ok=False, error=f"Govee API request failed: {detail}"), 502
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 500


@app.post("/api/color")
def color():
    body = request.get_json(silent=True) or {}
    device_id = str(body.get("device", "")).strip()
    sku = str(body.get("sku", "")).strip()

    if not device_id or not sku:
        return jsonify(ok=False, error="device and sku are required"), 400
    try:
        value = parse_hex_colour(str(body.get("color", "")))
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400

    try:
        result = set_color(device_id, sku, value)
        return jsonify(
            ok=True,
            color=f"#{value:06x}",
            device=result["device"].get("deviceName"),
        )
    except requests.HTTPError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        return jsonify(ok=False, error=f"Govee API request failed: {detail}"), 502
    except Exception as exc:
        return jsonify(ok=False, error=str(exc)), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8082"))
    print(f"Serving the {VIEW} view on port {port}", flush=True)
    app.run(host="0.0.0.0", port=port)
