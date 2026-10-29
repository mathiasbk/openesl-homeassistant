# Bin collection

The next pickup day and what is collected, with the pickup after it. It reads a waste collection calendar, such as the one from [Waste Collection Schedule](https://github.com/mampfes/hacs_waste_collection_schedule) or a Local calendar you fill in yourself, where each pickup is an all-day event named after what is collected.

The layout `bin-collection` comes from the designer's template library: **+ From template → Home → Bin collection**, then **Send to your AP**.

```yaml
alias: Bin collection on a tag
triggers:
  - trigger: time
    at: "00:05:00"
  - trigger: homeassistant
    event: start
actions:
  - action: calendar.get_events
    target:
      entity_id: calendar.waste
    data:
      duration:
        days: 30
    response_variable: cal
  - variables:
      pickups: "{{ cal['calendar.waste'].events | sort(attribute='start') }}"
  - action: openesl.send
    data:
      device_id: 4f0c6a...   # the tag
      layout: bin-collection
      fields: >-
        {%- macro day(e) -%}
          {%- set d = strptime(e.start[:10], '%Y-%m-%d').date() -%}
          {%- set n = (d - now().date()).days -%}
          {{- 'Today' if n == 0 else 'Tomorrow' if n == 1 else d.strftime('%A %d %b') -}}
        {%- endmacro -%}
        {%- if pickups -%}
          {%- set first = pickups[0].start[:10] -%}
          {%- set same = pickups | selectattr('start', 'search', '^' ~ first) | map(attribute='summary') | list -%}
          {%- set after = pickups | rejectattr('start', 'search', '^' ~ first) | list -%}
          {{ ['Next pickup', day(pickups[0]), (same | join(', '))[:24],
              ('Then: ' ~ day(after[0]) ~ ', ' ~ after[0].summary)[:40] if after else ''] }}
        {%- else -%}
          {{ ['Next pickup', 'None in 30 days', '', ''] }}
        {%- endif -%}
```

The tag shows, for example, **Next pickup**, **Tomorrow**, **Paper, Plastic** and **Then: Friday 07 Nov, Food waste**. Pickups on the same day are put together.

It runs just after midnight, so "Tomorrow" becomes "Today" on the day. `strftime('%A')` gives English day names; for another language, use a list:

```
{%- set days = ['Mandag', 'Tirsdag', 'Onsdag', 'Torsdag', 'Fredag', 'Lørdag', 'Søndag'] -%}
... days[d.weekday()] ~ ' ' ~ d.day ~ '.' ...
```
