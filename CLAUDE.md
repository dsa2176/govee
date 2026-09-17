# Govee Home Control — working notes

Flask wall-panel for Govee devices on a Raspberry Pi (`pi5-livingroom`). One
`app.py` serves two skins; `VIEW` picks the template.

## Layout

```
app.py                     all backend logic, no blueprints
templates/pipboy.html      Fallout Pip-Boy skin   (VIEW=pipboy, port 8082)
templates/lcars.html       Star Trek LCARS skin   (VIEW=lcars,  port 8081)
systemd/*.service          copied to /etc/systemd/system/
device_state.json          runtime state, gitignored
.env                       GOVEE_API_KEY, gitignored
```

Each template is self-contained — inline CSS and JS, no static/ dir, no build
step. The two skins share no code, so **a UI change must be made twice**. They
do share every endpoint.

## Running and testing

Never test by editing and reloading: the services run `debug=off`, so a code
change does nothing until restarted, and **restart needs sudo, which requires a
password — the user has to run it**:

```bash
sudo systemctl restart govee-pipboy.service govee-lcars.service
```

To test a change without touching the live dashboards, run a throwaway process
on a spare port:

```bash
cd ~/govee-home-control
VIEW=lcars PORT=8099 .venv/bin/python app.py
```

Kill it by PID when done. Watch for stale listeners on the test port — a
leftover process will serve the *old* view and produce a confusing result.

There is **no `node`** on this Pi, so template JS cannot be parsed. Validate it
structurally (bracket balance over the `<script>` block, presence of the
functions and endpoints) and say plainly that runtime behaviour is unverified.

## Govee API notes

Base: `https://openapi.api.govee.com/router/api/v1`, key in the
`Govee-API-Key` header.

- Errors come back as **`msg`**, not `message`, with **HTTP 200** and a `code`
  of 400 in the body. Reading the wrong field hides the real reason.
- `/device/state` returns **stale values** — a successful control call does not
  move the reported `powerSwitch`. Only `online` looks trustworthy. This is why
  the UI shows what was *sent*, not what the device *is*; do not try to "fix"
  this by reading live state.
- Devices drop off Wi-Fi in power-save and then reject commands with
  `Device is offline. Please check the Wi-Fi connection.` That is the device
  sleeping, not a bug.

Capabilities used:

| Feature | type | instance | value |
|---|---|---|---|
| Power | `devices.capabilities.on_off` | `powerSwitch` | `0` / `1` |
| Colour | `devices.capabilities.color_setting` | `colorRgb` | int `0`–`16777215` |
| Brightness | `devices.capabilities.range` | `brightness` | int `1`–`100` |

All three go through `send_capability()`. `/api/devices` reports a per-device
`color` / `brightness` boolean so a control only renders where the device can
act on it — keep that pattern when adding capabilities.

## Device visibility

Only names in `VISIBLE_DEVICE_NAMES` are shown. Matching is on
`normalize_name()` — lowercased, non-alphanumerics stripped — so
`ceiling living 1` matches `ceilingliving1`. The account has more devices than
the dashboard shows; that is deliberate. Two of them (`Gaming Wall Light` and
`Gaming Wall Light evag`) normalise to strings where one is a prefix of the
other, so match exactly, never by prefix.

## State file

`device_state.json` maps `device_id -> {color, brightness}`. Written atomically
(temp file + `os.replace`) because both services write it. An older flat
`{id: "#colour"}` format is migrated on read. Any read failure degrades to
defaults rather than erroring — keep it that way, it is a convenience, not a
source of truth.

## Conventions

- Endpoints validate input and return `{ok: false, error: "..."}` with 400 for
  bad input, 502 for a Govee HTTP failure, 500 otherwise. Mirror this shape.
- Both skins surface errors in the card's existing status line.
- Verify against the real API before claiming something works; it is a live
  house, so say which lamp was changed and to what.
