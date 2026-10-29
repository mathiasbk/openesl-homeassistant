# Getting started

From nothing to text on a tag in about ten minutes. You need an OpenESL AP on the same network as Home Assistant, at least one tag that has checked in with it, and the AP's API token.

## 1. Install the integration

The integration is installed with [HACS](https://hacs.xyz):

1. HACS → the menu (⋮) → **Custom repositories**. Add `https://github.com/mathiasbk/openesl-homeassistant` with the type **Integration**.
2. Search for **OpenESL** in HACS, press **Download**, and restart Home Assistant.

It needs Home Assistant 2025.3 or newer.

## 2. Add the AP

Go to Settings → Devices & services.

- **The AP shows up as Discovered** (Home Assistant finds it by its name, `openesl-xxxx`): press **Add** and give it the API token.
- **It does not show up:** **Add integration** → **OpenESL**, and give it the AP's address (`openesl-xxxx.local` or its IP address) and the token.

The token is the one you set on the AP's setup page, see [WiFi and API token](https://github.com/mathiasbk/openESL/wiki/WiFi-and-API-token) in the OpenESL wiki.

The AP and every tag it knows become devices. A tag is named after the first 8 digits under its barcode (`Tag 02066346`). Rename it to where it hangs (`Kitchen`, `Office door`), which makes it easier to pick in automations.

## 3. Send the first text

Developer tools → **Actions**. Pick **OpenESL: Send text**, switch to YAML mode and paste:

```yaml
action: openesl.send
data:
  device_id: 4f0c6a...      # remove this line, then pick the tag under "Tags" in UI mode
  layout: text
  fields:
    - "Hello"
    - "from Home Assistant"
```

Press **Perform action**. The answer below shows what the AP said for each tag (`changed: true` means it got new content). The tag shows the text at its next check-in, which is within about a minute with the default poll interval.

Two things go wrong most often:

- **An unknown layout**: the layout is not on the AP for that tag's model. `text` and `price` are always there; the others come from the designer, see [Sending text](Sending-text#layouts).
- **Text that is too long**: all the fields together are limited to about 90 characters. Shorten the text, see [Sending text](Sending-text#the-text-limit).

## 4. Put it in an automation

Settings → Automations & scenes → **Create automation** → **Create new automation**, then the menu (⋮) → **Edit in YAML**. Paste one of the [examples](Home#examples), change the entities to your own, and pick your tag in the visual editor (the `device_id` line).

Before you save it, try the template part on its own in Developer tools → **Template**. It shows exactly the list of fields that will be sent.
