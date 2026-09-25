# LinkTap Local HTTP API for Home Assistant

A custom Home Assistant integration for LinkTap TapLinkers and ValveLinkers using the LinkTap gateway's **local HTTP API**.

The integration provides local control and monitoring of LinkTap devices, including LinkTap-style **Instant Watering**, device status, water/flow sensors, cumulative watering totals, firmware-aware watering pause controls, alerts, and optional Home Assistant-side watering safety limits.

> [!IMPORTANT]
> The LinkTap gateway's **Local HTTP API must be enabled** and the gateway must be reachable directly from Home Assistant on the local network.

## Installation

Install the integration through **HACS** and restart Home Assistant if required.

Then add it from:

**Settings → Devices & services → Add integration → Local HTTP API for LinkTap**

Enter the **IPv4 address of the LinkTap gateway**, for example:

```text
192.168.1.123
```

Do not enter a URL, port, path, hostname or IPv6 address, for example:

```text
http://192.168.1.123
192.168.1.123:80
192.168.1.123/api.shtml
gateway-hostname.local
```

Since v0.8.4, the config flow now validates and normalises the gateway IPv4 address before saving it.

If you have more than one LinkTap gateway, add the integration once for each gateway.

## What the integration creates

A Home Assistant **device** is created for each LinkTap output discovered through the gateway.

For multi-valve TapLinkers or ValveLinkers, a separate Home Assistant device is created for each output.

The integration creates:

- a main **switch** for watering;
- a matching **valve** entity;
- a **Pause Water Plan** switch;
- watering duration, watering volume and pause-duration **number** entities;
- status and alert **binary sensors**;
- water, flow, duration, plan and diagnostic **sensors**.

The main switch and valve are functionally equivalent for normal watering control and should remain in sync.

## Instant Watering

For normal Home Assistant instant watering:

1. Set **Watering Duration**.
2. Optionally set **Watering Volume**.
3. Turn on the main LinkTap switch or open the LinkTap valve.

The integration sends both limits to the LinkTap gateway. Watering **stops when the first applicable limit is reached.**

### Watering Duration

- Unit: **minutes**
- Default: **15 minutes**
- Native integration range: **0–120 minutes**
- Step: **5 minutes**

### Watering Volume

- Unit: the volume unit configured on the LinkTap gateway, normally **L** or **Gal**
- Default: **0**
- Native integration range: **0–2000**
- Step: **10**

A Watering Volume value of `0` means **no volume cutoff**. In that case watering is controlled by duration only.

> [!NOTE]
> These Home Assistant duration/volume helpers are used for watering started through the integration's normal switch/valve control path. Watering started from the LinkTap app, the physical device button, MQTT, or another external mechanism is controlled by LinkTap itself and does not use these Home Assistant helper values.

## Optional instant-watering safety limits

Since **v0.8.3**, optional per-device Home Assistant safety ceilings can be configured for instant watering.

Open:

**Settings → Devices & services → LinkTap → Configure**

For each LinkTap device you may independently set:

- **Maximum watering duration:** 5–120 minutes
- **Maximum watering volume:** 10–2000 in the gateway's configured volume unit

Either limit may be left unset.

These are **Home Assistant-side safety controls only**. They do not modify the LinkTap gateway, firmware, watering plans or native LinkTap limits.

When configured, the selected maximum:

- reduces the maximum allowed value of the corresponding Home Assistant number entity;
- clamps a restored/default helper value into the permitted range;
- is enforced again immediately before the normal switch watering command is sent;
- is exposed as a state attribute for diagnostic visibility.

`0` retains its existing special meaning for Watering Volume: **no volume cutoff**.

> [!CAUTION]
> The `valve.start_watering` entity service accepts its own duration in seconds and currently sends that request directly to the LinkTap API. It does not use the Watering Duration / Watering Volume number helpers, so do not assume the optional helper safety ceilings apply to that service call.

## Pause controls

The LinkTap CMD 18 pause/resume behaviour depends on gateway firmware. The integration reads the gateway firmware version reported by CMD 16 and selects the compatible behaviour automatically.

For gateways using the newer CMD 18 protocol, Home Assistant exposes:

- **Pause Watering**
- **Pause Duration**

A positive pause request pauses the active watering process/schedule for the configured number of hours. A resume request uses CMD 18 with `duration: 0`. The integration deliberately omits the CMD 18 `option` field when resuming; pre-release gateway testing showed that `duration: 0` with `option: 1` could return success without restarting watering, while omitting `option` resumed correctly.

For older gateway firmware, the existing behaviour and terminology are retained:

- **Pause Water Plan**
- **Pause Duration Water Plan**

The legacy CMD 18 path pauses/unpauses the watering plan rather than using the newer watering-process semantics.

### Pause duration

- Unit: **hours**
- Default: **24 hours**
- Range: **1–240 hours**
- Step: **1 hour**

The newer CMD 18 protocol supports additional pause semantics through its `option` field. The integration currently uses the default option for positive pause requests and does not expose an option selector in Home Assistant.

### Firmware compatibility

The production implementation enables the newer CMD 18 behaviour only when the parsed firmware version is greater than `60951`. The exact LinkTap firmware-version parsing convention and threshold are being confirmed with LinkTap before release; the integration falls back to legacy behaviour when the version cannot be parsed safely.

### Repeated-pause protection

The integration retains its repeated-positive-pause guard for both firmware paths. Before sending a positive pause request, it refreshes gateway state and rejects the request when `is_paused` is already true. This preserves backward compatibility with older firmware where a repeated positive CMD 18 request has been observed to deactivate the underlying watering plan.

Newer firmware tested during development safely rejected a repeated positive pause itself, but the Home Assistant-side guard remains so a second CMD 18 is not deliberately sent.

Unpause/resume while already unpaused is treated as an idempotent no-op. To apply a different pause duration while a pause is active, resume/unpause first and then apply a new pause.

## Entity naming and renaming

Since **v0.8.0**, internal relationships between LinkTap entities are resolved through Home Assistant's **Entity Registry and stable unique IDs**, rather than by reconstructing entity IDs from the LinkTap device name.

This fixes a long-standing failure mode where newer Home Assistant entity-ID formats, recreated entities, area/device naming, or user-renamed entity IDs could cause the integration to miss the Watering Duration/Volume helper and silently fall back to the default duration.

You may now rename LinkTap entity IDs in Home Assistant without breaking the integration's internal relationships.

Existing entity IDs and unique IDs were intentionally preserved during this change, so upgrading does not force an entity migration.

Example IDs for newly created/recreated entities may look like:

```text
switch.linktap_g2s01
valve.linktap_g2s01
switch.linktap_g2s01_pause
number.linktap_g2s01_watering_duration
number.linktap_g2s01_watering_volume
number.linktap_g2s01_pause_duration
sensor.linktap_g2s01_battery
sensor.linktap_g2s01_signal
```

These are examples only; Home Assistant controls generated entity IDs.

## Binary sensors

| Binary sensor | Description |
|---|---|
| **Connected** | Whether the TapLinker is linked to the gateway |
| **Detected Fall** | Fall alert reported by the device |
| **Detected Water Cutoff** | Water-cutoff / failed-shutoff alert |
| **Detected Leak** | Leak condition reported by the device |
| **Detected Clog** | Clogged condition reported by the device |
| **Detected Device Fault** | Other broken/fault condition reported by the device |
| **Manual Watering** | Device has been triggered manually (if device supports this) |
| **Watering Paused** | LinkTap reports the watering/plan pause state |
| **Watering** | Device is currently watering |

Since v0.8.0, the fault-oriented entities — fall, cutoff, leaking, clogged and broken — are categorised as Home Assistant **diagnostic** entities. Operational states remain normal device entities.

## Sensors

| Sensor | Description |
|---|---|
| **Signal Strength** | Signal strength between the LinkTap device and gateway |
| **Battery Charge** | Device battery level |
| **Session Duration** | Current LinkTap watering-session duration, reported in seconds |
| **Remaining Duration** | Remaining duration for the current watering session, in seconds |
| **Total Watering Time** | Home Assistant-maintained cumulative watering time |
| **Flow Rate** | Current water flow rate |
| **Session Volume** | Water volume reported for the current watering session |
| **Volume Limit** | Current LinkTap volume limit |
| **Total Water Volume** | Home Assistant-maintained cumulative water volume |
| **Failsafe Duration** | LinkTap failsafe duration reported by the gateway, in seconds; currently read-only |
| **Plan Mode Code** | Numeric LinkTap watering-plan mode |
| **Plan Mode** | Human-readable translation of the plan mode |
| **Plan Serial Number** | LinkTap watering-plan serial number |

### Remaining Duration

Since v0.8.0, **Remaining Duration** is normalised to `0` when watering has stopped.

Some LinkTap responses retain a stale final non-zero remaining-duration value after watering ends. The integration therefore reports the gateway value while watering or paused, and `0` otherwise.

## Water flow and Home Assistant statistics

Since **v0.8.0**, the **Flow Rate** sensor exposes Home Assistant's proper `volume_flow_rate` device class and `measurement` state class, using canonical units:

- `L/min`
- `gal/min`

This now allows the sensor to participate correctly in Home Assistant statistics and compatible water/energy dashboard features.

## Volume and watering totals

### Volume

`Volume` is the LinkTap gateway's raw/current-session water-volume value and is expected to reset when a new watering session begins.

### Total Water Volume

`Total Water Volume` is maintained by this Home Assistant integration because the local API does not provide the same cumulative total directly.

It is:

- persistent across Home Assistant restarts;
- `state_class: total_increasing`;
- suitable for Home Assistant long-term statistics;
- suitable for `utility_meter` helpers;
- suitable as a cumulative water source where Home Assistant accepts a water `total_increasing` sensor.

The integration compensates for the gateway retaining the previous session's raw `volume` after watering finishes so that a Home Assistant restart does not count the same completed session again.

### Protection against corrupt raw volume readings

Since **v0.8.1**, `Total Water Volume` includes defensive protection against persistent corruption from grossly implausible raw volume samples.

Before a raw sample can affect the persistent accumulator, the integration rejects:

- non-numeric values;
- non-finite values such as `NaN` or infinity;
- negative values;
- grossly implausible session-volume values.

Where LinkTap reports a non-zero `volume_limit`, that is also used as a stronger contextual plausibility bound with generous tolerance.

Rejected values are **dropped rather than clamped**, so they do not replace the last known-good accumulator sample. A warning is logged when a sample is rejected.

This is a defensive Home Assistant safeguard. It does **not** claim to fix the underlying LinkTap telemetry source if the gateway/firmware/API itself emits a bad value.

### Total Watering Time

`Total Watering Time` is maintained by Home Assistant, persists across restarts, reports cumulative watering time in seconds and uses `state_class: total_increasing`.

## Number entities

| Number entity | Default | Range | Unit | Purpose |
|---|---:|---:|---|---|
| **Watering Duration** | 15 | 0–120 | min | Requested instant-watering duration |
| **Watering Volume** | 0 | 0–2000 | L or Gal | Optional volume cutoff; `0` disables it |
| **Pause Duration** / **Pause Duration Water Plan** | 24 | 1–240 | h | Firmware-aware pause duration |

Optional per-device safety limits reduce the effective maximum of Watering Duration and/or Watering Volume.

## Switch and valve

Each LinkTap output has both a main **switch** and a **valve** entity.

For normal operation:

- switch on / valve open → start instant watering using the configured Home Assistant duration/volume values;
- switch off / valve close → stop watering.

Since v0.8.0, the valve resolves its backing switch through the Entity Registry and stable unique ID, so user-renamed entity IDs are supported.

## Entity services

### `linktap.pause`

Pause or unpause a LinkTap watering plan through a LinkTap switch entity.

| Field | Required | Description |
|---|---|---|
| `entity_id` | yes | LinkTap switch entity |
| `hours` | no | Pause duration in hours; default `1`; `0` unpauses |

### `linktap.pause_valve`

Pause or unpause through a LinkTap valve entity.

| Field | Required | Description |
|---|---|---|
| `entity_id` | yes | LinkTap valve entity |
| `hours` | no | Pause duration in hours; default `1`; `0` unpauses |

### `valve.start_watering`

Start watering through a LinkTap valve entity for an explicit duration in seconds.

| Field | Required | Description |
|---|---|---|
| `entity_id` | yes | LinkTap valve entity |
| `seconds` | no | Watering duration in seconds; registered default `9000` |

This service is **separate from the normal Watering Duration/Watering Volume** helper path.

### Alert dismissal

The binary-sensor platform also exposes entity services for dismissing one alert or all applicable alerts.

## Watering plans and scheduling

The integration can report LinkTap plan information and can **pause/unpause the existing water plan**, but it does not currently provide Home Assistant controls for creating or editing LinkTap watering schedules.

Use the LinkTap app/web interface to manage schedules.

## Multiple gateways

Multiple LinkTap gateways are supported.

Each gateway must:

- have the Local HTTP API enabled;
- be reachable directly by Home Assistant;
- be added as a separate integration config entry using its IPv4 address.

## Device naming changes from LinkTap

When a TapLinker or ValveLinker is newly added or renamed in LinkTap, there can be a delay before the new name appears in the gateway's local API.

If Home Assistant initially discovers a generic name such as `TapLinker`, it waits for the gateway to update and then reload the integration.

Current versions resolve internal relationships by stable unique ID, so renaming Home Assistant entity IDs no longer breaks watering controls.

## G1 devices and flow measurement

If Volume or Speed always remains zero, check the LinkTap hardware model.

Older **G1** devices do not have the integrated flow-meter capability available on models such as the G2S. The integration cannot provide flow or volume data that the hardware does not measure/report.

## Failsafe Duration

The integration currently exposes LinkTap's reported **Failsafe Duration** as a read-only sensor.

This is distinct from the optional Home Assistant instant-watering safety ceilings. The current integration does **not** provide a control for changing `failsafe_duration`.

## Troubleshooting

### Watering always uses 15 minutes

Current releases resolve Watering Duration through the Entity Registry using its stable unique ID rather than guessing an entity ID.

If a current release still falls back to 15 minutes:

1. confirm the Watering Duration number entity exists and is available;
2. check whether it is temporarily `unknown` or `unavailable`;
3. reload the LinkTap integration;
4. check Home Assistant logs;
5. open an issue with the integration version, Home Assistant version and relevant diagnostics.

Temporary invalid helper states are handled safely and cause the normal fallback rather than a numeric-conversion error.

### Gateway address rejected during setup

Enter only the gateway's IPv4 address, for example:

```text
192.168.1.123
```

Do not include a URL scheme, hostname, port or API path.

### Total Water Volume looks incorrect

Compare:

- the raw LinkTap `Volume` for the completed session;
- the increase in `Total Water Volume`;
- the LinkTap app/cloud value separately.

`Total Water Volume` accumulates the volume reported by the **local API**. The LinkTap app/cloud may present a different value, beyond the scope of this integration.

Current releases also contain restart double-count protection and protection against grossly implausible raw-volume spikes.

### Repeated pause is rejected

This is intentional. A second positive LinkTap water-plan pause request has been observed to deactivate the underlying watering plan despite a successful gateway response, so the integration blocks it.

## Recent changes

### v0.8.4

- Validate and normalise the LinkTap gateway IPv4 address during config flow.
- Reject URLs, ports, paths, hostnames and IPv6 with a user-friendly error.

### v0.8.3

- Add optional per-device Home Assistant instant-watering safety ceilings.
- Independently configure maximum duration and/or maximum volume.
- Apply limits to the Home Assistant number controls and enforce them again at the normal switch command boundary.

### v0.8.2

- Protect against destructive repeated water-plan pause requests.
- Refresh state before mutation and verify the resulting state.
- Treat unpause while already unpaused as a no-op.

### v0.8.1

- Protect persistent `Total Water Volume` from grossly implausible raw-volume spikes.
- Reject invalid/non-finite/negative samples before they can affect the accumulator.
- Preserve restart double-count protection.

### v0.8.0

- Resolve sibling LinkTap entities through stable unique IDs and the Home Assistant Entity Registry.
- Support renamed/recreated/current-format Home Assistant entity IDs.
- Modernise device-relative entity naming while preserving existing unique IDs.
- Add correct flow-rate metadata and statistics support.
- Handle unavailable/unknown number helpers safely.
- Reset stale Remaining Duration to zero when watering has stopped.
- Categorise LinkTap fault indicators as diagnostic entities.
- Rename pause controls to **Pause Water Plan** and **Pause Duration Water Plan**.

## Reporting issues

When reporting an issue, please include:

- integration version;
- Home Assistant version;
- LinkTap gateway/device model;
- whether the action originated from Home Assistant, the LinkTap app, MQTT or the physical device;
- relevant logs;
- raw/current entity values involved;
- clear reproduction steps.

For volume-related issues, include both the raw `Session Volume` and the change in `Total Water Volume`.

---

This integration uses LinkTap's local HTTP API and is an independent Home Assistant community integration.
