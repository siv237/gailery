---
title: Двухконтурная архитектура
category: concepts
updated: 2026-07-09
sources: 1
tags: [gpu, ollama, local]
---

# Двухконтурная архитектура (dual-circuit)

Все GPU-задачи (кроме describe/faces) работают в двух режимах, переключаемых в `config.py`:

```python
OLLAMA_MODE = "local"          # "local" | "ollama"
OLLAMA_BASE_URL = "http://192.168.237.158:11434"
OLLAMA_EMBED_MODEL = "qwen3-embedding:0.6b"
```

| Режим | Бэкенд | Характер |
|---|---|---|
| **local** (по умолчанию) | transformers / llama-cpp-python | Прямой GPU, без внешних зависимостей |
| **ollama** | Ollama HTTP API | Использует запущенный сервер Ollama (локальный или сетевой) |

## Реализация в каждом воркере

```python
if config.OLLAMA_MODE == "ollama":
    result = ollama_request("POST", "/api/embed", body)
else:
    result = local_engine.encode(texts)
```

## Что реализовано двухконтурно
- [x] **embed** — семантическая индексация
- [x] **semantic_search** — через EmbedEngine
- [x] **describe** — VLM (llama-server vs Ollama/VLM)
- [ ] **enrich_description** — обогащение описаний (llama.cpp vs Ollama) — в работе
- [ ] **exif** — не требует GPU, всегда локально

## Не двухконтурно (всегда локально)
- **faces** — InsightFace GPU

## Преимущества
По умолчанию работает автономно (local). При наличии Ollama — использует её оптимизированный
llama.cpp. Ollama может быть на другой машине (сетевой доступ).

## Связанные страницы
- [GPU arbitration](gpu-arbitration.md) — как временные задачи вклиниваются в фоновые
- [Глоссарий](../glossary.md) — OLLAMA_MODE
