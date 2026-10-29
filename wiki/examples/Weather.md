# Weather

The weather from any weather entity in Home Assistant (Met.no, OpenWeatherMap, ...): a symbol that follows the weather, the temperature, the weather in words, today's low and high, wind and rain.

The layout `weather` comes from the designer's template library: **+ From template → Home → Weather**, then **Send to your AP**.

An ESP32-S3 AP can also fetch the weather from MET Norway by itself, without Home Assistant (the AP's data sources). Use this automation when the weather is already in Home Assistant, or the AP is an ESP32-C6.

```yaml
alias: Weather on a tag
triggers:
  # Once an hour; the tag is only redrawn when the text has changed
  - trigger: time_pattern
    minutes: 5
  - trigger: state
    entity_id: weather.home
actions:
  - action: weather.get_forecasts
    target:
      entity_id: weather.home
    data:
      type: daily
    response_variable: fc
  - variables:
      w: weather.home
      day: "{{ fc['weather.home'].forecast[0] }}"
  - action: openesl.send
    data:
      device_id: 4f0c6a...   # the tag
      layout: weather
      fields: >-
        {%- set cond = states(w) -%}
        {%- set night = is_state('sun.sun', 'below_horizon') -%}
        {%- set symbol = {
              'sunny': 'sun', 'clear-night': 'moon',
              'partlycloudy': 'partmoon' if night else 'partsun',
              'cloudy': 'cloud', 'fog': 'fog', 'rainy': 'rain', 'pouring': 'rain',
              'snowy': 'snow', 'snowy-rainy': 'sleet', 'hail': 'sleet',
              'lightning': 'thunder', 'lightning-rainy': 'thunder'}.get(cond, 'cloud') -%}
        {%- set words = {
              'sunny': 'Sunny', 'clear-night': 'Clear', 'partlycloudy': 'Partly cloudy',
              'cloudy': 'Cloudy', 'fog': 'Fog', 'rainy': 'Rain', 'pouring': 'Heavy rain',
              'snowy': 'Snow', 'snowy-rainy': 'Sleet', 'hail': 'Hail', 'windy': 'Windy',
              'lightning': 'Thunder', 'lightning-rainy': 'Thunder'}.get(cond, cond) -%}
        {%- set wind = state_attr(w, 'wind_speed') | float(0) -%}
        {%- set wind = wind / 3.6 if state_attr(w, 'wind_speed_unit') == 'km/h' else wind -%}
        {%- set rain = (day.get('precipitation', 0) | float(0) | round(1) | string).replace('.', ',') -%}
        {{ ['Home',
            state_attr(w, 'temperature') | float(0) | round(0) | int,
            symbol,
            words,
            (day.get('templow', day.temperature) | float(0) | round(0) | int) ~ '° / ' ~ (day.temperature | float(0) | round(0) | int) ~ '°',
            (wind | round(0) | int) ~ ' m/s  ' ~ rain ~ ' mm'] }}
```

Replace `weather.home` (four places) with your weather entity and `Home` with the place's name. The tag shows, for example, a cloud with the sun, **7**°, **Partly cloudy**, **3° / 9°** and **4 m/s  0,6 mm**.

The symbol must be one of the template's icon names (`sun`, `moon`, `partsun`, `partmoon`, `cloud`, `fog`, `rain`, `sleet`, `snow`, `thunder`). Change the words in `words` to your own language.
