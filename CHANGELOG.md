# Changelog

Each version has its own section. When `version` in `custom_components/openesl/manifest.json` changes on `main`, the release workflow tags `v<version>` and makes the GitHub release with that section as its text, so HACS offers it. A section always says how to upgrade.

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
