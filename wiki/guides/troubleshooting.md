---
title: Troubleshooting
category: guides
updated: 2026-07-09
sources: 2
tags: [troubleshooting, gpu, bugs]
---

# Troubleshooting — известные грабли

Сборник граблей и как их обходить. Пополняется по мере обнаружения.

## 1. Осиротевший llama-server
**Симптом:** describe упал, но процесс llama-server висит с `ppid=1`, занимает GPU.
**Решение:** pipeline.py сам убивает orphan перед каждым GPU-шагом (`kill_orphan_llama_servers()`).
Watchdog тоже детектит. Ручное лечение — через кнопку «Стоп», не kill вручную (см. CRITICAL_RULES).
См. [GPU arbitration](../concepts/gpu-arbitration.md).

## 2. Stale GPU lock
**Симптом:** `request_gpu_gentle()`/`acquire_gpu()` вечно ждут, хотя GPU свободен.
**Причина:** в MQTT lock topic висит holder с мёртвым PID.
**Решение:** `acquire_gpu()` чистит stale lock, если PID не существует. Если нет — проверить MQTT
и очистить retained `{MQTT_PREFIX}/gpu/lock`.

## 3. Второй pipeline / дубликат воркера
**Симптом:** два pipeline.py или два воркера лезут на GPU одновременно.
**Решение:** watchdog убивает дубликаты pipeline.py. Кнопка «Цепочка» убивает старый pipeline перед
запуском нового. Никогда не запускать второй pipeline вручную.

## 4. FLIR byte-swap
**Симптом:** тепловая карта FLIR даёт мусор/неправильную температуру.
**Причина:** PNG хранит big-endian, PIL на x-endian x86 читает как little-endian → байты перевёрнуты.
**Решение:** byte swap перед `raw2temp` (полная Planck-формула). См. `FLIR.md`.

## 5. Два GPU-процесса = баг
Любое появление двух процессов на GPU одновременно — нарушение арбитража. См. GPU arbitration.

## 6. Временные задачи крашат фоновые
enrich/search не должны убивать фоновый pipeline. Используют мягкий/жёсткий захват через MQTT,
не kill процессов вручную.
