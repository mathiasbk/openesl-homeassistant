# Changelog

Each version has its own section. When `version` in `custom_components/openesl/manifest.json` changes on `main`, the release workflow tags `v<version>` and makes the GitHub release with that section as its text, so HACS offers it. A section always says how to upgrade.

## 0.4.0

- **Fields by name:** `fields` in `openesl.send` can be a mapping by the layout's field names (`price: "44.90"`) as well as a list in the layout's order (openESL #182). An automation then keeps showing the right text in the right place when the layout's field order changes or the tag gets another layout with the same names. A field left out is empty.
- An AP with 0.9.2 or older takes a list only. Fields by name to such an AP fail with a message that says which AP firmware is needed, instead of the AP's bare `422`. Lists work as before on every AP.

### Upgrading

Update in HACS and restart Home Assistant; nothing to set up, and automations with a list keep working. Fields by name need openESL AP firmware newer than 0.9.2 (the first release after 0.9.2). Order: the AP first, then the integration, and only then change automations to fields by name.

## 0.3.0

- **Lost radio:** an ESP32-S3 AP that loses contact with its ESP32-C6 radio (on the cable or over WiFi) shows it: the **Radio** entity turns off, and after 30 s a repair says which AP and radio, and what to check. It goes away by itself when the radio is back. Until then the tags that radio serves hear nothing from the AP.
- **Radio** now also for the C6 on the cable, with the attributes `via`, `lost` and `lost_s`; an AP with several radios over WiFi gets **Radio 1**-**3** too, also for a C6 that joins later.
- An AP with older firmware sends none of this: nothing changes there.

### Upgrading

Update in HACS and restart Home Assistant; nothing to set up. The repair and the Radio entity for the C6 on the cable need openESL AP firmware with `radio_problems` in `GET /api/health` (the first release after 0.9.2). Order: either first, they work together both ways.

## 0.2.0

- **Less traffic on the AP:** each update asks the AP for only the tags that changed since the last one (`GET /api/tags?since=`, openESL #270), instead of the whole list. With 200 tags on a 600 s poll interval that is about a fifth of the list every 120 s, and nothing when no tag polled. Tags that did not change keep their states, and their last check-in stays put.
- An AP without this (openESL firmware released before it) ignores the parameter and sends the whole list, as before, so nothing breaks.

### Upgrading

Update in HACS and restart Home Assistant; nothing to set up. The smaller reads need AP firmware with `GET /api/tags?since=` (the first openESL release with it). Order: either first, they work together both ways.

## 0.1.0

The first version. It uses only the OpenESL AP's HTTP API, so nothing on the AP needs to change. Needs Home Assistant 2025.3 or newer (2026.3 or newer for the icon).

- **Setup:** the AP is found on the network (`openesl-xxxx`), or added with its address and API token. A new token or address is asked for when needed.
- **Devices:** each tag is a device with battery voltage, signal, last check-in, problems, update pending and firmware. The AP is a device with tags, tags with problems, firmware, WiFi signal and radio channel. A tag that moves to another AP follows it.
- **Actions:** `openesl.send` puts text in a layout on tags (optionally at a later time), `openesl.send_image` shows a PNG, and `openesl.refresh` reads the AP at once.
- **Options:** the update interval, 120 s by default.
- English and Norwegian.

### Upgrading

Nothing to upgrade from. Install: HACS → Custom repositories → `https://github.com/mathiasbk/openesl-homeassistant`, type Integration, download **OpenESL** and restart Home Assistant. If you used the `rest_command` from openESL's `docs/home-assistant.md`, it keeps working next to the integration; replace `rest_command.esl_tag_text` with `openesl.send` (same `layout` and `fields`, the tag instead of `mac`) when you like.
