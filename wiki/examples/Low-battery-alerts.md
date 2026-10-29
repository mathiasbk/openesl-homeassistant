# Low battery alerts

The integration gives each tag a **Problem** sensor. It turns on when the AP lists the tag in its health check: the tag is silent, has not been seen, failed to draw, had a content error, or its battery is low (below 2.5 V). The **Battery** sensor is the low battery part of it on its own. This automation sends a notification when a tag's Problem sensor turns on, so a tag does not quietly go blank.

```yaml
alias: OpenESL tag needs attention
triggers:
  - trigger: state
    entity_id:
      - binary_sensor.kitchen_problem        # each tag's Problem sensor
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
        {%- set words = {
              'silent': 'has stopped checking in',
              'unseen': 'has not been seen since the AP started',
              'draw_failed': 'could not draw its screen',
              'content_error': 'got content it cannot show',
              'low_battery': 'has a low battery'} -%}
        {%- set problems = state_attr(trigger.entity_id, 'problems') or [] -%}
        {%- set volts = states(trigger.entity_id | replace('binary_sensor.', 'sensor.') | replace('_problem', '_battery_voltage')) -%}
        {%- set ns = namespace(said=[]) -%}
        {%- for p in problems -%}{%- set ns.said = ns.said + [words.get(p, p)] -%}{%- endfor -%}
        The tag {{ ns.said | join(' and ') }}
        {%- if 'low_battery' in problems %} ({{ volts }} V){% endif %}.
```

The entity IDs follow the tag's name: `Tag 02066346` has `binary_sensor.tag_02066346_problem` and `sensor.tag_02066346_battery_voltage`. When you rename the tag to `Kitchen` and let Home Assistant rename its entities too, they become `binary_sensor.kitchen_problem` and so on, as above. Pick them in the visual editor instead of typing them. `for: 30 minutes` skips a tag that misses one check-in and is back at the next.

Use the **Battery** sensors instead of Problem when you only want to hear about batteries. The 1.54" tag cannot measure its battery, so it never reports a low battery: it shows up as silent when the battery is gone.

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
