---
title: GPU arbitration
category: concepts
updated: 2026-07-09
sources: 2
tags: [gpu, pipeline, mqtt, watchdog]
---

# GPU arbitration (арбитраж GPU)

Железо: **одна** видеокарта P104-100, 8GB VRAM. Одновременно на GPU — **только один**
процесс. Любое нарушение этого правила = баг.

## Два класса задач

| Класс | Примеры | Характер | Приоритет |
|---|---|---|---|
| Фоновые | describe (VLM), faces (InsightFace), embed (llama-server) | Длительные, pipeline запускает последовательно через `subprocess.run` | Высокий |
| Временные | semantic_search (embedding), enrich (text LLM) | Короткие, по запросу из API | Низкий — вклиниваются, не крашат фоновые |

## Механизмы захвата

- **`acquire_gpu()`** (WorkerMQTT) — реальный мьютекс для фоновых воркеров. Читает MQTT lock topic,
  проверяет holder; если занят — ждёт; если holder мёртв (PID нет) — чистит stale lock. После успеха
  `gpu_held=True`, при завершении — `release_gpu()`.
- **`request_gpu_gentle()`** (ApiMQTT) — мягкий захват для поиска: ждёт до 120с, **отказывает** если
  GPU занят, никого не убивает.
- **`request_gpu_for_api()`** (ApiMQTT) — жёсткий захват для enrich: pause + pkill если не отдали за 3с.
  После — `release_gpu_from_api()` + `send_resume`.
- **`kill_orphan_llama_servers()`** (pipeline.py) — перед каждым GPU-шагом убивает осиротевшие
  llama-server (ppid=1, не от кнопки).

## Watchdog (пёс)

Следит **только за пайплайном**. Спящий пёс (`no_restart` стоит) НЕ делает ничего. Просыпается
только кнопкой «Цепочка». Активный пёс: убивает дубли pipeline.py, сирот llama-server, следит за
памятью, перезапускает упавший pipeline. **Игнорирует** индивидуальные шаги (embed/faces/describe по
отдельности).

## Связанные страницы
- [Глоссарий](../glossary.md) — определения GPU lock, no_restart, orphan llama-server
- [Двухконтурная архитектура](dual-circuit.md) — local vs ollama
