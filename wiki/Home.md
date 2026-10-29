# OpenESL for Home Assistant

The OpenESL integration puts an [OpenESL](https://github.com/mathiasbk/openESL) access point (AP) and its tags into Home Assistant. Every tag becomes a device with its battery, signal and last check-in, and the action `openesl.send` puts text on it from an automation.

This wiki is the how-to guide: setting it up, and automations ready to copy. The [README](https://github.com/mathiasbk/openesl-homeassistant/blob/main/README.md) lists every entity and every field of the actions.

## Start here

1. [Getting started](Getting-started): install with HACS, add the AP, and send the first text from Developer tools.
2. [Sending text](Sending-text): layouts, fields, the text limit, and how to keep the tags' batteries happy.

## Examples

| Example | Shows | Layout |
|---|---|---|
| [Calendar on a tag](Calendar) | Today's appointments, or a meeting room's "now" and "next" | `text`, `meeting-room` |
| [Bin collection](Bin-collection) | The next pickup day and what is collected, from a waste calendar | `bin-collection` |
| [Weather](Weather) | Temperature, a weather symbol, today's low and high, wind and rain (needs the next OpenESL release) | `weather` |
| [Room climate](Room-climate) | A room's temperature and humidity | `room-climate` |
| [Low battery alerts](Low-battery-alerts) | A notification when a tag's battery runs low or it goes silent | none |

Every example is a whole automation: paste it in an automation's **Edit in YAML**, then change the entities and pick the tag.

The OpenESL wiki has the rest of the system: [the AP](https://github.com/mathiasbk/openESL/wiki), [the label designer](https://github.com/mathiasbk/openESL/wiki/Label-designer) and [its templates](https://github.com/mathiasbk/openESL/wiki/Label-templates).
