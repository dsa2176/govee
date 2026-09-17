# Govee Home Control

Fullscreen Raspberry Pi wall-panel for a handful of Govee devices, in two
interchangeable skins:

| View | Style | Default port |
|------|-------|--------------|
| `pipboy` | Fallout Pip-Boy, green phosphor | 8082 |
| `lcars`  | Star Trek LCARS | 8081 |

Both views run the same `app.py`; `VIEW` picks the template. Each has a
Personal Log / Notes pane stored in the browser's `localStorage` (never sent
to the server).

## Devices

Only devices whose name matches `VISIBLE_DEVICE_NAMES` in `app.py` are shown.
Names are normalised (lowercased, non-alphanumerics stripped) before matching,
so `ceiling living 1` matches `ceilingliving1`.

## Install

```bash
git clone https://github.com/dsa2176/govee.git govee-home-control
cd govee-home-control
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then add your GOVEE_API_KEY
.venv/bin/python app.py
```

Open `http://<pi-ip>:8082`.

## Running both views as services

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now govee-pipboy.service govee-lcars.service
```

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `GOVEE_API_KEY` | *(required)* | Govee Developer API key |
| `VIEW` | `pipboy` | `pipboy` or `lcars` |
| `PORT` | `8082` | Listen port |
| `STATE_FILE` | `device_state.json` | Where last colour/brightness is stored |

## Notes

- Each device card has power buttons, an intensity bar (1-100%) and a colour
  row (presets plus a custom picker). Controls only appear for devices that
  report the matching capability.
- `device_state.json` remembers the last colour and brightness *sent* to each
  device, so both views agree and the controls survive a restart. It is
  gitignored runtime state; delete it and the controls fall back to defaults.
- `.env` is gitignored. Never commit your API key.
- Some Govee models enter Wi-Fi power-save and drop off the network. The API
  then returns `Device is offline. Please check the Wi-Fi connection.`, which
  the UI surfaces on the device card. This is the device sleeping, not a bug.
- The Govee `/device/state` endpoint reports stale values for some models, so
  the dashboard does not try to show current on/off state.
- `app.py` runs Flask's development server. Fine on a trusted LAN; `gunicorn`
  is in `requirements.txt` if you want to front it properly.
