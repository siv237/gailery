---
title: Pipeline
category: entities
updated: 2026-07-09
sources: 1
tags: [pipeline, orchestrator, subsystem]
---

# Pipeline (оркестратор)

**Сущность:** `pipeline.py` — бесконечный цикл, управляющий всеми этапами обработки галереи.
Это та самая «петля», за которой следит [watchdog](../concepts/gpu-arbitration.md#watchdog-пёс).
Спит при флаге `no_restart` (кнопка «Стоп»).

## Роль
Последовательно (блокирующий `subprocess.run`) прогоняет этапы, чтобы на GPU всегда был
ровно один процесс (см. [GPU arbitration](../concepts/gpu-arbitration.md)).

## Этап 1 — Наполнение (цикл)
`СКАН` (пути) → пока `unhashed > 0`: `{ ХЕШ(200) → ДЕДУП+INGEST → EXIF(all) }`.
Наполнение 100% только когда `unhashed = 0`.

## Этап 2 — AI батч-цикл
`faces(60) → describe(60, батч 6) → embed(60)` → повтор пока всё не 100%.
Перед каждым GPU-шагом — `kill_orphan_llama_servers()` (уборка осиротевших серверов).

## Счётчики
Прогресс каждого шага — только по canonical-файлам (`is_canonical=1`, `deleted=0`, уникальные).
См. [Глоссарий](../glossary.md) (canonical, embedded, faces_done).

## Связи
- Управляется: [watchdog](../concepts/gpu-arbitration.md) (пёс)
- Использует: [dual-circuit](../concepts/dual-circuit.md) (режимы local/ollama для describe/embed)
- Подробно: [PIPELINE.md](../../PIPELINE.md) (raw source)
