# Calendar on a tag

Any calendar in Home Assistant (Google, CalDAV, Local calendar, a work calendar over iCal) can be shown on a tag. The automation gets the day's events with `calendar.get_events` and sends them with `openesl.send`. Nothing extra is needed on the AP or in the integration.

Replace `calendar.family` with your calendar, and pick your tag in the visual editor (the `device_id` line).

## Today's appointments (layout `text`)

The heading and the next three events of the day (the one going on now included), on four lines. It works on every AP, since `text` is built in.

```yaml
alias: Calendar on a tag
mode: queued
max: 2
triggers:
  # When an event starts or ends, and just after midnight for the new day
  - trigger: calendar
    event: start
    entity_id: calendar.family
  - trigger: calendar
    event: end
    entity_id: calendar.family
  - trigger: time
    at: "00:05:00"
  - trigger: homeassistant
    event: start
actions:
  - action: calendar.get_events
    target:
      entity_id: calendar.family
    data:
      start_date_time: "{{ now() }}"
      end_date_time: "{{ today_at() + timedelta(days=1) }}"
    response_variable: cal
  - variables:
      events: "{{ cal['calendar.family'].events | sort(attribute='start') }}"
  - action: openesl.send
    data:
      device_id: 4f0c6a...   # the tag
      layout: text
      fields: >-
        {%- set ns = namespace(lines=[]) -%}
        {%- for e in events[:3] -%}
          {%- set time = (as_datetime(e.start) | as_local).strftime('%H:%M') if 'T' in e.start else 'All day' -%}
          {%- set ns.lines = ns.lines + [time ~ ' ' ~ e.summary[:15]] -%}
        {%- endfor -%}
        {{ ['Today ' ~ now().strftime('%d.%m')] + (ns.lines if ns.lines else ['No appointments']) }}
```

The tag shows, for example:

```
Today 30.10
All day Birthday Ola No
08:30 Dentist
18:00 Football training
```

Events that are over drop off the list, so each start and end trigger moves it on. All-day events come first. Titles are cut to 15 characters to stay inside the [text limit](Sending-text#the-text-limit).

## Meeting room: now and next (layout `meeting-room`)

A sign for a meeting room door, or for "what is on now" at home: the room's name, **BUSY** or **FREE** in large inverted letters, the event that is on now, and the next one.

The layout comes from the designer's template library: in the designer, pick the tag's model, then **+ From template → Signs → Meeting room**, and **Send to your AP**.

Use the same triggers and the same `calendar.get_events` as above, and this `openesl.send`:

```yaml
  - action: openesl.send
    data:
      device_id: 4f0c6a...
      layout: meeting-room
      fields: >-
        {%- set timed = events | selectattr('start', 'search', 'T') | list -%}
        {%- set now_on = timed | selectattr('start', 'le', now().isoformat()) | selectattr('end', 'gt', now().isoformat()) | list -%}
        {%- set later = timed | selectattr('start', 'gt', now().isoformat()) | list -%}
        {{ ['Office',
            'BUSY' if now_on else 'FREE',
            ('Now: ' ~ now_on[0].summary[:18]) if now_on else '',
            ('Next: ' ~ (as_datetime(later[0].start) | as_local).strftime('%H:%M') ~ ' ' ~ later[0].summary[:12]) if later else 'Nothing more today'] }}
```

All-day events are left out here (`search 'T'` keeps only events with a time), so a birthday does not make the room busy.

The calendar gives the times as text with a time zone, and the comparison with `now().isoformat()` works when the calendar and Home Assistant are in the same time zone, which is the usual case.

## Battery

The tag only gets a new picture when the text changes. These triggers send when an event starts or ends, once a night and when Home Assistant starts, so the tag is redrawn a few times a day. Do not add a trigger every minute with a clock in the text: that redraws the tag every minute.
