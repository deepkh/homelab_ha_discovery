---
name: asus-router
description: Use when changing ASUS router SSH collectors, parser logic, connected-client metrics, router CPU/temperature/network speed metrics, or related docs.
---

# ASUS router metrics

## Safety

Do not run SSH commands against a real router unless explicitly asked.

Do not store router credentials in the repository.

## Collector expectations

Router collectors may gather:

- CPU usage
- temperature
- network download/upload speed
- connected clients
- wireless signal/interface information

## Parser behavior

Parser code should handle:

- missing fields
- variant firmware output
- unknown interfaces
- clients without names
- clients without RSSI

## Home Assistant behavior

Connected-client data may be better represented as attributes on one sensor,
while numeric metrics should be separate sensors.

## Validation

Use sample command output fixtures when possible.

Do not require a live router for unit tests.
