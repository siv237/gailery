---
title: Index
category: index
updated: 2026-07-09
sources: 0
tags: [index]
---

# Wiki Index

Каталог всех страниц вики Gailery. Обновляется при каждом ingest/query.
Формат: `- [Страница](путь) — однострочное описание (источников: N, обновлено: ДДДД-ММ-ДД)`.

## Источники (raw sources — только для чтения)

- [AGENTS.md](../AGENTS.md) — контекст проекта, критические правила, GPU-арбитраж, пайплайн
- [PIPELINE.md](../PIPELINE.md) — полная спецификация шагов пайплайна, счётчиков, инвалидации
- [FLIR.md](../FLIR.md) — тепловая карта FLIR, формат и конвертация
- [MODULES.md](../MODULES.md) — автосгенерированное описание модулей
- [ROADMAP.md](../ROADMAP.md) — план развития
- [STYLE.md](../STYLE.md) — стиль кода
- `src/` — исходный код (истина в последней инстанции)

## Глоссарий

- [Глоссарий](glossary.md) — ключевые термины проекта

## Концепты

- [GPU arbitration](concepts/gpu-arbitration.md) — мьютекс GPU, watchdog, режимы local/ollama
- [Двухконтурная архитектура](concepts/dual-circuit.md) — local vs ollama бэкенды

## Сущности (подсистемы)

- [Pipeline](entities/pipeline.md) — оркестратор этапов наполнения и AI-батчей (pipeline.py) (источников: 1, обновлено: 2026-07-09)
- [Альбомы](entities/albums.md) — ручные/авто альбомы, семечки, живая ссылка catalog (источников: 3, обновлено: 2026-07-31)

## Гайды

- [Troubleshooting](guides/troubleshooting.md) — известные грабли и как их обходить

## Решения

- [Лог решений](decisions/decision-log.md) — архитектурные решения и их обоснование
