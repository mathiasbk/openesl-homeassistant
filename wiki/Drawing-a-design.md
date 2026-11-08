# Drawing a design

`openesl.draw` puts a design made for the moment on one or more tags: boxes, circles, lines, icons, codes and text, without uploading a layout file to the AP first. The AP checks the design against the tag's screen, draws it once and keeps the picture, as it does for `openesl.send_image`. `openesl.draw` needs openESL AP firmware 0.11.0 or newer; an older AP answers with a message that names the firmware it needs.

Use `openesl.send` with a layout file for content that changes often or should follow the date, and `openesl.draw` for a one-off: a sign for an event, a test of a new design, or a picture built from sensor values now and then.

## A first design

A meeting room sign on a 2.9" tag (296 x 128 pixels): a black band with the room name, a circle and the next meeting.

```yaml
action: openesl.draw
data:
  device_id: 4f0c6a...
  layout:
    fields: [room, next]
    elements:
      - { type: rect, x: 0, y: 0, w: 296, h: 30, color: black }
      - { type: text, field: room, x: 4, y: 0, w: 288, h: 30, fonts: [medium], valign: middle, color: white }
      - { type: ellipse, x: 8, y: 40, w: 60, h: 60, border: 3 }
      - { type: text, field: next, x: 80, y: 40, w: 210, h: 60, fonts: [medium, small], lines: 2 }
  fields:
    room: Meeting room 2
    next: "Free until {{ states('sensor.room_2_next_meeting') }}"
```

The design is one layout as in an openESL layout file: `fields` names the texts, and `elements` says where each one goes. The element types are `text`, `rect`, `line`, `ellipse`, `polygon`, `icon`, `barcode` and `qr`; the openESL wiki page [Layout elements and limits](https://github.com/mathiasbk/openESL/wiki/Layout-elements-and-limits) lists what each one takes. The easiest way to make one is the openESL designer: draw it there, then copy the layout's `fields` and `elements` into the action. A design with icons of your own also needs the file's `icons`, which the designer keeps next to the layouts: copy them into the action's `icons`.

`fields` can be a list in the layout's order or, as above, a mapping by name.

## Good to know

- **Each call is a new picture** on the AP (about 5 KB of its storage per tag), and the tag fetches it at its next poll. The AP sees when the picture is the same as the one the tag has, and then sends nothing, but call it only when what it shows has changed.
- **Dates are filled in once**, when it is drawn: `{date}` in a fixed text is not updated the next day. For that, use a layout file and `openesl.send`.
- **It must fit the tag.** A design for the 2.9" does not fit the 1.54" (200 x 200). A text that is too long for its box takes the next font in `fonts`, wraps up to `lines` and is then cut with "…". A barcode or QR code that is too long, or a formatted number (`decimals`) that does not fit even in its smallest font, makes the AP refuse the design, and the action fails with the AP's reason.
- **Size limits.** A design can have at most 1024 JSON values (the AP answers that it is too big), and the action fails when the AP has no room left for another picture.
- Content sent to the tag later (`openesl.send` or `openesl.send_image`) replaces the design.

## Seeing what a tag shows

Every tag has a **Screen** image entity: a picture of what the tag shows, drawn by the AP, like the **Screen** column in the openESL dashboard. Put it in a **Picture entity** card (or **Picture glance**) to check what an automation sent without walking to the tag. Next to it, the tag's **Update pending** says whether the tag shows it yet.

Here for a tag renamed to "Meeting room 2":

```yaml
type: picture-entity
entity: image.meeting_room_2_screen
show_state: false
```

The AP draws the image only while something shows it, and only again after the tag's content changed, so it costs the AP nothing between changes. It is empty before the tag has any content, or when the AP cannot draw it (the tag's **Problem** is on, with "content error" in `problems`). While the AP is busy, the card keeps the last image. The Screen entity works with every openESL AP from firmware 0.5.0.
