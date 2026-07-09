---
title: Глоссарий
category: glossary
updated: 2026-07-09
sources: 2
tags: [glossary, terms]
---

# Глоссарий Gailery

Ключевые термины проекта. Подробности — в соответствующих концептах/raw sources.

- **content_hash** — xxh128-хеш содержимого файла. Единственный надёжный идентификатор файла
  (пути могут меняться). Все привязки результатов обработки (faces, embeddings, описания) —
  через `content_hash`. См. [GPU arbitration](concepts/gpu-arbitration.md) для контекста идентификации.
- **canonical / is_canonical** — для дублей файлов (один content_hash, много путей) один помечается
  canonical, остальные — справочно. Счётчики прогресса и обработка — только по canonical.
- **dual-circuit (двухконтурная архитектура)** — GPU-задачи работают в режиме `local`
  (transformers/llama.cpp) или `ollama` (Ollama HTTP API). См. [Двухконтурная архитектура](concepts/dual-circuit.md).
- **OLLAMA_MODE** — переключатель `local`/`ollama` в `config.py`.
- **embedded** — флаг: для фото сгенерирован семантический индекс (LanceDB).
- **faces_done** — флаг: InsightFace отработал для фото (лица найдены или их нет).
- **described / rich_description** — базовое VLM-описание и обогащённое LLM-описание (enrich).
- **no_restart** — флаг «спящий пёс»: pipeline остановлен, watchdog ничего не делает.
- **GPU lock topic** — MQTT-топик `{MQTT_PREFIX}/gpu/lock` (retained): кто держит GPU сейчас.
- **watchdog (пёс)** — процесс, следящий ТОЛЬКО за пайплайном. Спит при `no_restart`.
- **LanceDB** — векторное хранилище семантических эмбеддингов.
- **orphan llama-server** — осиротевший процесс llama-server (ppid=1) после падения воркера.
