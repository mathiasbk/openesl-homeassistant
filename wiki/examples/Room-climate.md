# Room climate

A room's name, its temperature in large digits, the humidity, and when it changed. It fits a tag on the wall next to a thermostat, or one per room.

The layout `room-climate` comes from the designer's template library: **+ From template → Home → Room climate**, then **Send to your AP**.

```yaml
alias: Living room climate on a tag
mode: queued
max: 2
triggers:
  - trigger: state
    entity_id:
      - sensor.living_room_temperature
      - sensor.living_room_humidity
conditions:
  # Only when the rounded value changes: half degrees and whole 5 %
  - condition: template
    value_template: >-
      {%- set step = 0.5 if 'temperature' in trigger.entity_id else 5 -%}
      {%- set old = trigger.from_state.state | float(none) if trigger.from_state else none -%}
      {%- set new = trigger.to_state.state | float(none) -%}
      {{ new is not none and (old is none or (old / step) | round(0) != (new / step) | round(0)) }}
actions:
  - action: openesl.send
    data:
      device_id: 4f0c6a...   # the tag
      layout: room-climate
      fields: >-
        {%- set t = states('sensor.living_room_temperature') | float(0) -%}
        {%- set h = states('sensor.living_room_humidity') | float(0) -%}
        {{ ['Living room',
            ('%g' | format(((t * 2) | round(0)) / 2)) | replace('.', ','),
            ((h / 5) | round(0) * 5) | int,
            'Since ' ~ now().strftime('%H:%M')] }}
```

The tag shows, for example, **Living room**, **21,5** °C (or **22** for a whole degree), **45** % and **Since 14:05**.

The condition is what keeps the battery going: a temperature sensor reports every few tenths of a degree, and without it the tag would be redrawn for each one. With half degrees and 5 % steps it is redrawn a few times a day. The time in the last field only changes when a value does, so it says when the room last changed, not when the tag was last drawn.
