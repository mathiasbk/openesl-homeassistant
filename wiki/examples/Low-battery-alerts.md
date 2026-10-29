# Low battery alerts

The integration gives each tag a **Battery** sensor (on when the AP says the battery is low, below 2.5 V) and a **Problem** sensor (on when the tag is silent, has not been seen, failed to draw, or its content had an error). This automation sends a notification when either turns on, so a tag does not quietly go blank.

```yaml
alias: OpenESL tag needs attention
triggers:
  - trigger: state
    entity_id:
      - binary_sensor.kitchen_battery       # each tag's Battery sensor
      - binary_sensor.kitchen_problem       # and its Problem sensor
      - binary_sensor.office_door_battery
      - binary_sensor.office_door_problem
    from: "off"
    to: "on"
    for:
      minutes: 30
actions:
  - action: notify.notify
    data:
      title: "{{ trigger.to_state.name }}"
      message: >-
        {%- if trigger.entity_id.endswith('_battery') -%}
          Battery low ({{ states(trigger.entity_id | replace('binary_sensor.', 'sensor.') ~ '_voltage') }} V)
        {%- else -%}
          {{ state_attr(trigger.entity_id, 'problems') | join(', ') }}
        {%- endif -%}
```

The entity IDs follow the tag's name: `Tag 02066346` has `binary_sensor.tag_02066346_battery`, `binary_sensor.tag_02066346_problem` and `sensor.tag_02066346_battery_voltage`. When you rename the tag to `Kitchen` and let Home Assistant rename its entities too, they become `binary_sensor.kitchen_battery` and so on, as above. Pick them in the visual editor instead of typing them. `for: 30 minutes` skips a tag that misses one check-in and is back at the next.

**Every tag, without listing them:** the AP's own **Tags with problems** sensor counts them. A trigger on it going up covers new tags as well:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.openesl_1a2b_tags_with_problems   # the AP's Tags with problems sensor
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.state | int(0) > trigger.from_state.state | int(0) }}"
actions:
  - action: notify.notify
    data:
      message: "{{ trigger.to_state.state }} OpenESL tags need attention. See the AP's dashboard."
```

The AP can also call a Home Assistant webhook by itself when a tag goes silent or its battery runs low, see [Health and webhook](https://github.com/mathiasbk/openESL/wiki/Health-and-webhook) in the OpenESL wiki.
