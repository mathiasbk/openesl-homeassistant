# OpenESL for Home Assistant

The OpenESL integration puts the access point (AP) of [OpenESL](https://github.com/mathiasbk/openESL), open firmware for electronic shelf labels, and every tag into Home Assistant: each tag is a device with its battery, signal and last check-in, and the actions `openesl.send` and `openesl.send_image` put text and pictures on them, without YAML for the API or a token in `secrets.yaml`. It only uses the AP's HTTP API ([openapi.yaml](https://github.com/mathiasbk/openESL/blob/master/docs/openapi.yaml)): nothing on the AP needs to change.

**[The wiki](https://github.com/mathiasbk/openesl-homeassistant/wiki)** is the step-by-step guide, with automations ready to copy: today's calendar, a meeting room sign, bin collection, weather, room climate and low battery alerts. This README is the reference.

![Today's calendar on a 2.9" tag](https://raw.githubusercontent.com/mathiasbk/openesl-homeassistant/main/images/calendar-tag.jpg)

Without the integration, a `rest_command` does the same for text: [home-assistant.md](https://github.com/mathiasbk/openESL/blob/master/docs/home-assistant.md).

## Install

With [HACS](https://hacs.xyz):

1. HACS → the menu (⋮) → **Custom repositories**: `https://github.com/mathiasbk/openesl-homeassistant`, type **Integration**.
2. Find **OpenESL** in HACS, **Download**, and restart Home Assistant.

By hand: copy the folder `custom_components/openesl` from this repository into `config/custom_components/` on the Home Assistant machine, and restart Home Assistant.

## Set it up

Settings → Devices & services. An AP on the same network shows up by itself as **Discovered** (it is found by its name, `openesl-xxxx`): press **Add** and give it the API token. Otherwise **Add integration** → **OpenESL**, with the AP's address (`openesl-xxxx.local`, or its IP) and the token. The token is the one set on the AP's setup page ([WiFi and API token](https://github.com/mathiasbk/openESL/wiki/WiFi-and-API-token)).

When the AP gets a new token, Home Assistant asks for it (a **Reauthenticate** card under Settings → Devices & services). Five wrong tokens in a row lock the AP's API for 60 s, and the integration stops asking the AP until it has the new token, so the dashboard is not locked out by it. A new address: the AP's menu (⋮) → **Reconfigure**.

Each AP is known by its name. An AP set up with firmware 0.6.0 or older is named `openesl`, like every other AP of that age, so it is known by its address instead: add it with the address it keeps (a DHCP reservation), and give it its own name on its setup page if you can. An AP that is renamed after it was added (`openesl-xxxx` to `shop`) is not found by its name any more and is a new AP to Home Assistant: delete it under Settings → Devices & services and add it again with its new name. The tags keep their entities.

**Options** (the AP's ⚙): how often the AP is read, every 120 s unless you change it (30 s to an hour). `GET /api/tags` is about 600 bytes a tag, so with 200 tags each read is about 120 KB that the AP sends over WiFi between the tags' polls; with many tags or weak WiFi, read it less often. The tags' battery and signal change slowly, and with a poll interval of 10 minutes on the tags nothing new comes sooner.

## What it shows

Every 120 s (the options) it reads `GET /api/tags`, `GET /api/health` and `GET /api/wifi` from the AP. A new tag becomes a device as soon as the AP lists it, named after the first 8 digits of the number under its barcode (`Tag 02066346`); rename it to where it hangs.

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
| AP | Firmware, Started, WiFi signal, Radio channel | diagnostic; WiFi signal is the AP's own (the first thing to look at when it answers slowly) |
| AP | Radio, Radio 1-3 | connectivity, diagnostic: the AP has contact with its radio. Only on an ESP32-S3 AP, whose radio is an ESP32-C6 on the cable (openESL firmware after 0.9.2) or over WiFi; Radio 1-3 when it has several radios over WiFi. Attributes `via` (`uart`: on the cable, `wifi`), `lost`, `lost_s`, `id`, `channel` |

**Lost radio:** when the S3 has had no contact with a C6 for 30 s (`radio_problems` in `/api/health`, openESL firmware after 0.9.2), a repair shows under Settings → System → Repairs: "openesl-xxxx: radio is not answering", with what to check. Until it answers again its tags hear nothing from the AP. The repair goes away by itself when the radio is back. To be told on your phone, automate on the Radio entity turning off, for example for 1 minute.

A tag the AP no longer lists turns unavailable; delete its device from its page (⋮ → Delete) when it is gone for good. A tag moved to another AP stays in the old AP's table for a while: with both APs in Home Assistant it has one device, which shows what the AP that heard it last says, and the actions send to that AP.

## Actions

### `openesl.send`

Text in a layout: the built-in `text` (four lines) or `price`, or a layout in the AP's layout file (the designer's templates, such as `3d-printer`). The same as `PUT /api/tags`, so the AP's rules hold: the fields share about 90 characters (about 250 on AP firmware newer than 0.9.2), a layout must be in the file for the tag's model, and the same content again does not redraw the tag.

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
| `fields` | the text: a list in the layout's field order, or a mapping by field name (see below); numbers are sent as text |
| `price_highlight`, `frame` | as in the API |
| `at` | a time to show it from instead of now (the AP keeps it; it needs to know the time) |
| `config_entry_id` | with more than one AP: where a MAC no AP lists yet goes |

With AP firmware newer than 0.9.2, `fields` can name the fields instead. The automation then keeps working when the layout's field order changes, or when the tag gets another layout with the same field names. A field left out is empty. The built-in layouts' names are `line1`-`line4` for `text` and `name`, `price`, `subtitle` for `price`; the designer shows a layout's names.

```yaml
action: openesl.send
data:
  device_id: 4f0c6a...
  layout: price
  fields:
    name: "Butter"
    price: "{{ states('input_number.butter_price') }}"
```

A name the layout does not have makes the AP refuse the content, with the name in the message. An AP with 0.9.2 or older takes a list only: the action then fails with a message that says so, and the tags keep what they show.

Many tags in one call go to the AP in batches of 50. The action answers with the AP's reply per tag (`content_id`, `changed`, `pending`), for `response_variable`. When the AP refuses the content (text too long, an unknown layout) the action fails with the AP's message, and the tags keep what they show. The AP takes or refuses each batch of 50 as a whole, so with more than 50 tags the batches before the refused one have already gone; the message says how many tags got the content.

Any `rest_command.esl_tag_text` in the automations of [home-assistant.md](https://github.com/mathiasbk/openESL/blob/master/docs/home-assistant.md) becomes `openesl.send` with the same `layout` and `fields`, and the tag instead of `mac`. A whole automation that shows a sensor on a tag every 10 minutes:

```yaml
alias: Outdoor temperature on a tag
triggers:
  - trigger: time_pattern
    minutes: /10
actions:
  - action: openesl.send
    data:
      device_id: 4f0c6a...           # the tag: pick it in the UI
      layout: text
      fields:
        - "Outside"
        - "{{ states('sensor.outdoor_temperature') | float(0) | round(0) }} °C"
```

Rounding the temperature keeps the text the same when little has changed, so the tag is not redrawn for it (a clock on the tag would redraw it every time).

### `openesl.send_image`

A PNG of exactly the tag's screen size (296 x 128 for the 2.9" and the experimental 2.9" red, 200 x 200 for the 1.54"), as `PUT /api/tags/{mac}/image`; `dither: true` for photos. The file must be in a folder Home Assistant may read: `/config/www` is, others go in `allowlist_external_dirs`.

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

The tests are in `tests/` (Home Assistant's test harness, Python 3.13): `pip install -r requirements_test.txt`, then `pytest`. The last test runs against the OpenESL simulator through the esl-client bridge, from an openESL checkout next to this one (or in `OPENESL_REPO`): `make -C ../openESL/sim build/29/esl-sim`, then `OPENESL_LIVE_URL=sim pytest`. CI does the same, with Home Assistant's `hassfest` and HACS's checks. CI builds the simulator from openESL's `development` branch, so a change there can turn this repository's CI red.

## Icon

The icon is in `custom_components/openesl/brand/` (the tag from the OpenESL web page). Home Assistant 2026.3 and newer shows it; older versions show a placeholder.

## Releases

A release is made by itself when `version` in `custom_components/openesl/manifest.json` changes on `main` (`.github/workflows/release.yml`). Its text is that version's section in [CHANGELOG.md](CHANGELOG.md), which must say how to upgrade (CI checks it). So a release is one pull request: the new version in the manifest and its section in the changelog.

## License

MIT, like OpenESL.
