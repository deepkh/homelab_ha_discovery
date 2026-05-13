---
name: docker-frigate
description: Use when changing Docker container metrics, Frigate metrics, Docker socket access, Frigate API parsing, detector/camera/storage/GPU metrics, or related docs.
---

# Docker and Frigate metrics

## Docker metrics

Docker collector changes should preserve clear separation between:

- container identity
- state/health
- restart count
- CPU usage
- memory usage
- network usage

Do not stop, restart, or remove containers unless explicitly asked.

## Frigate metrics

Frigate metrics may include:

- system metrics
- camera metrics
- detector metrics
- GPU metrics
- storage metrics

Keep parsing tolerant of missing fields because Frigate versions and configurations differ.

## Validation

Prefer using sample JSON fixtures when possible.

Check that missing optional fields do not crash the publisher.

## Documentation

Update docs when new metrics or config options are exposed.
