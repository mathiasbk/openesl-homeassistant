# SoluM remote

A SoluM ESL remote (SLT-RC004) is a small three-button remote: **W**, **left** and **right**, plus an on/off switch. With openESL it becomes a wireless button for Home Assistant automations: toggle a light, start a scene, flip to the next page of a tag.

![SoluM ESL remote, front](https://raw.githubusercontent.com/mathiasbk/openESL/master/docs/images/solum-remote-front.jpg)

## What you need

- An openESL AP whose own radio is an ESP32-C6 or C5, with openESL firmware after 0.11.0.
- The openESL integration 0.6.0 or newer.
- The AP must hear 802.15.4 **channel 11**, the remote's channel. Either:
  - run the AP on channel 11, which costs nothing, or
  - turn on the switch **Listen on channel 11** on the remote's device. The AP's radio then visits channel 11 for a moment many times a second while it keeps its own channel. That costs the tags some battery, since some of their checks need a second try.
- The AP must reach Home Assistant over plain HTTP. The integration gives the AP its internal URL (or its IP when that is a `.local` name). A Home Assistant that answers only over HTTPS cannot get the presses.

Once the AP supports the remote, the integration adds a device **SoluM remote** under the AP. Nothing needs to be paired: the AP hears any SoluM remote in range.

## What you get

| Entity or trigger | What it does |
|---|---|
| **Button** (event entity) | Its `event_type` is `w`, `left` or `right` at each press |
| **Listen on channel 11** (switch) | The AP visits channel 11 while it runs on another one |
| Device triggers | "W pressed", "Left pressed" and "Right pressed" under Automation → Device → SoluM remote |
| Event `openesl_remote_button` | Fired at each press with `button` (`w`, `left`, `right`), `device_id`, `ap` and `id` |

The integration registers a webhook in Home Assistant and gives its address to the AP, so each press arrives at once, with nothing polling. An AP that already posts its presses to another address keeps it. When you remove the integration, it takes its address off the AP again.

## Automations

The easiest way is a device trigger: Settings → Automations → Create → Device → **SoluM remote** → "W pressed".

In YAML, use the event:

```yaml
alias: Hallway light from the remote
triggers:
  - trigger: event
    event_type: openesl_remote_button
    event_data:
      button: w
actions:
  - action: light.toggle
    target:
      entity_id: light.hallway
```

One automation for all three buttons:

```yaml
alias: Living room scenes from the remote
triggers:
  - trigger: event
    event_type: openesl_remote_button
actions:
  - choose:
      - conditions: "{{ trigger.event.data.button == 'left' }}"
        sequence:
          - action: scene.turn_on
            target:
              entity_id: scene.living_room_evening
      - conditions: "{{ trigger.event.data.button == 'right' }}"
        sequence:
          - action: scene.turn_on
            target:
              entity_id: scene.living_room_bright
      - conditions: "{{ trigger.event.data.button == 'w' }}"
        sequence:
          - action: light.turn_off
            target:
              area_id: living_room
```

With more than one AP, `ap` in the event data tells which AP heard the press.

## Limits

- **All SoluM remotes look the same.** A remote has no address of its own, so two remotes in range trigger the same automations.
- **The frames are not encrypted.** Anyone with a radio on channel 11 can send a press. Use the remote for lights and scenes, not for locks, alarms or doors.
- With **Listen on channel 11**, the tags' batteries last somewhat shorter. Running the AP on channel 11 avoids that.
- An AP whose radio is on a cable or over WiFi from an ESP32-S3 does not hear the remote yet.

More about the remote and the AP side in [openESL's wiki](https://github.com/mathiasbk/openESL/wiki/SoluM-remote).
