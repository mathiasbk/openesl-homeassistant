# Sending text

`openesl.send` puts text in a layout on one or more tags. The AP draws the picture itself, so Home Assistant sends only the text. The [README](https://github.com/mathiasbk/openesl-homeassistant/blob/main/README.md#openeslsend) lists every field of the action.

```yaml
action: openesl.send
data:
  device_id: 4f0c6a...          # one or more tags
  layout: text
  fields:
    - "Outside"
    - "{{ states('sensor.outdoor_temperature') | float(0) | round(0) }} °C"
```

## Layouts

A layout says where each field goes on the screen and in which font. The fields are sent in the layout's order.

- **`text`** is built in: four lines of text, with as many fields as you send (up to four).
- **`price`** is built in: a product name, the price, and a small line under it (`price_highlight: true` makes the price stand out).
- **Every other layout** is made in the [label designer](https://github.com/mathiasbk/openESL/wiki/Label-designer) and sent to the AP from there. The designer's **template library** has ready-made layouts for Home Assistant, such as `meeting-room`, `bin-collection`, `weather` and `room-climate`, which the [examples](Home#examples) use. Open the designer for the tag's model, press **+ From template**, pick one and press **Send to your AP**. See [Label templates](https://github.com/mathiasbk/openESL/wiki/Label-templates) in the OpenESL wiki.

A layout is made for one tag model (2.9", 1.54", or the experimental 2.9" red). Send it to the AP for each model you use it on.

## Fields from templates

`fields` can be a list in YAML, with a template in each line as above. When the text needs a loop or a choice, let one template make the whole list:

```yaml
fields: >-
  {{ ['Today', states('sensor.next_event')] }}
```

Home Assistant turns a template that renders a list into a real list. Numbers are sent as text.

## The text limit

All the fields of one tag share 96 bytes (the AP sends them in one radio packet): one byte per field plus the text, so about 90 characters in all. Letters such as æ, ø, å and ° count as one character each. Emoji and other characters outside Latin-1 cannot be shown and become `?`. Empty fields at the end cost nothing. Cut long text in the template, for example `e.summary[:15]`.

When the text is too long, the AP refuses it, the action fails with the AP's message, and the tag keeps what it shows.

## Battery

Each new picture costs the tag power. The AP only sends a picture when the text has changed, so sending the same text again is free.

- **Send on change**, not on a timer, when you can: when a calendar event starts, when a sensor changes.
- **Round numbers** (`round(0)`) so a small change does not redraw the tag.
- **Leave clocks off the tag.** A time that changes every minute redraws the tag every minute.
- **Leave the poll interval alone.** A shorter interval makes changes show sooner but costs battery all the time.

## Later content

`at` sends content that the AP shows from a given time, for example tomorrow's menu at midnight. The AP keeps it and needs to know the time (it gets it from NTP).

```yaml
action: openesl.send
data:
  device_id: 4f0c6a...
  layout: text
  fields: ["Closed today"]
  at: "2026-12-24 00:00:00"
```

## Pictures

`openesl.send_image` shows a PNG of exactly the tag's screen size (296 x 128 for the 2.9" and the experimental 2.9" red, 200 x 200 for the 1.54"). See the [README](https://github.com/mathiasbk/openesl-homeassistant/blob/main/README.md#actions).
