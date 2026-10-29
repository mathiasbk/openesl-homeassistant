# OpenESL for Home Assistant

The OpenESL integration puts the access point (AP) of [OpenESL](https://github.com/mathiasbk/openESL), open firmware for electronic shelf labels, and every tag into Home Assistant: each tag is a device with its battery, signal and last check-in, and the actions `openesl.send` and `openesl.send_image` put text and pictures on them, without YAML for the API or a token in `secrets.yaml`. It only uses the AP's HTTP API ([openapi.yaml](https://github.com/mathiasbk/openESL/blob/master/docs/openapi.yaml)): nothing on the AP needs to change.

Without the integration, a `rest_command` does the same for text: [home-assistant.md](https://github.com/mathiasbk/openESL/blob/master/docs/home-assistant.md).

## Install

With [HACS](https://hacs.xyz):

1. HACS → the menu (⋮) → **Custom repositories**: `https://github.com/mathiasbk/openesl-homeassistant`, type **Integration**.
2. Find **OpenESL** in HACS, **Download**, and restart Home Assistant.

By hand: copy the folder `custom_components/openesl` from this repository into `config/custom_components/` on the Home Assistant machine, and restart Home Assistant.

## Set it up

Settings → Devices & services. An AP on the same network shows up by itself as **Discovered** (it is found by its name, `openesl-xxxx`): press **Add** and give it the API token. Otherwise **Add integration** → **OpenESL**, with the AP's address (`openesl-xxxx.local`, or its IP) and the token. The token is the one set on the AP's setup page ([WiFi and API token](https://github.com/mathiasbk/openESL/wiki/WiFi-and-API-token)).

When the AP gets a new token, Home Assistant asks for it (a **Reauthenticate** card under Settings → Devices & services). Five wrong tokens in a row lock the AP's API for 60 s, and the integration stops asking the AP until it has the new token, so the dashboard is not locked out by it. A new address: the AP's menu (⋮) → **Reconfigure**.

## What it shows

Every minute it reads `GET /api/tags` and `GET /api/health` from the AP. A new tag becomes a device as soon as the AP lists it, named after the first 8 digits of the number under its barcode (`Tag 02066346`); rename it to where it hangs.

| Device | Entity | From the AP |
|---|---|---|
| Tag | Battery voltage | `battery_mv` (unknown on the 1.54", which cannot measure it) |
| Tag | Signal | `rssi` of its last poll, dBm |
| Tag | Last check-in | when it last polled |
| Tag | Problem | on when `/api/health` lists it: silent, unseen, draw failed, low battery or content error; which ones in the attribute `problems` |
| Tag | Battery | on (low) when `/api/health` says `low_battery` (below 2.5 V) |
| Tag | Update pending, Firmware | diagnostic: the tag does not show its content yet; its firmware |
| Tag | Poll interval, Lost polls | diagnostic, off until you turn them on |
| AP | Tags, Tags with problems | how many tags the AP knows, and how many `/api/health` lists |
| AP | Firmware, Started, Radio channel, Radio | diagnostic; Radio only on an AP with a network radio (an ESP32-C6 over WiFi) |

A tag the AP no longer lists turns unavailable; delete its device from its page (⋮ → Delete) when it is gone for good.

## Actions

### `openesl.send`

Text in a layout: the built-in `text` (four lines) or `price`, or a layout in the AP's layout file (the designer's templates, such as `3d-printer`). The same as `PUT /api/tags`, so the AP's rules hold: the fields share about 90 characters, a layout must be in the file for the tag's model, and the same content again does not redraw the tag.

```yaml
action: openesl.send
data:
  device_id: 4f0c6a...            # the tag's device: pick it in the UI
  layout: text
  fields:
    - "Bins out tonight"
    - "{{ states('sensor.next_collection') }}"
  frame: true
```

| Field | |
|---|---|
| `device_id` | one or more tags (devices); or `mac` with 16-digit MACs, which also works for a tag the AP does not know yet |
| `layout` | `text`, `price` or a layout's name |
| `fields` | the text, in the layout's field order; numbers are sent as text |
| `price_highlight`, `frame` | as in the API |
| `at` | a time to show it from instead of now (the AP keeps it; it needs to know the time) |
| `config_entry_id` | with more than one AP: where a MAC no AP lists yet goes |

Many tags in one call go to the AP in batches of 50. The action answers with the AP's reply per tag (`content_id`, `changed`, `pending`), for `response_variable`. When the AP refuses the content (text too long, an unknown layout) the action fails with the AP's message, and the tags keep what they show.

The 3D printer automation in [home-assistant.md](https://github.com/mathiasbk/openESL/blob/master/docs/home-assistant.md) becomes:

```yaml
  - action: openesl.send
    data:
      device_id: 4f0c6a...
      layout: 3d-printer
      fields: >-
        {{ [printer, '', pct | string, 'Left ' ~ ..., 'Done at ' ~ ..., ' ' * (pct | int * 31 // 100)] }}
```

### `openesl.send_image`

A PNG of exactly the tag's screen size (296 x 128 for the 2.9", 200 x 200 for the 1.54"), as `PUT /api/tags/{mac}/image`; `dither: true` for photos. The file must be in a folder Home Assistant may read: `/config/www` is, others go in `allowlist_external_dirs`.

```yaml
action: openesl.send_image
data:
  device_id: 4f0c6a...
  path: /config/www/tag.png
  dither: true
```

### `openesl.refresh`

Reads the tags now instead of at the next minute.

## Battery

Everything in [home-assistant.md, "Limits and timing"](https://github.com/mathiasbk/openESL/blob/master/docs/home-assistant.md#limits-and-timing) holds: every new screen costs the tag power, so send when something has changed and round numbers, and do not lower the poll interval. Reading the sensors costs the tags nothing: the integration only asks the AP.

## For developers

The tests are in `tests/` (Home Assistant's test harness, Python 3.13): `pip install -r requirements_test.txt`, then `pytest`. The last test runs against the OpenESL simulator through the esl-client bridge, from an openESL checkout next to this one (or in `OPENESL_REPO`): `make -C ../openESL/sim build/29/esl-sim`, then `OPENESL_LIVE_URL=sim pytest`. CI does the same, with Home Assistant's `hassfest` and HACS's checks.

## License

MIT, like OpenESL.
