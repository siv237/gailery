# Wiki Log

Хронологическая запись событий вики. Append-only.
Формат префикса: `## [YYYY-MM-DD] <ingest|query|lint> | <заголовок>`.
Последние 5 записей: `grep "^## \[" wiki/log.md | tail -5`

## [2026-07-31] ingest | Альбомы: семечка catalog (живая ссылка)
Новая фича: добавление каталога (папки со всеми вложениями) в альбом из вкладки Каталог.
- Создана страница `entities/albums.md` (хранилище, семечки, живой резолвер, API, UI,
  план соответствия на перевод всех групповых семечек в динамику + exclude-семечки).
- Добавлено решение `D-2026-07-31` в `decisions/decision-log.md`.
- Обновлён `index.md` (сущность Альбомы).
- Источники: `src/api/albums.py`, `src/database.py`, `web/catalog.html`, `web/albums.html`.

## [2026-07-09] ingest | Инициализация вики
Создан слой LLM Wiki для проекта Gailery по паттерну LLM Wiki.
- Создана схема `wiki/AGENTS.md` (слои raw sources / wiki / schema, воркфлоу ingest/query/lint).
- Созданы `index.md` и `log.md`.
- Семенные страницы: `glossary.md`, `concepts/gpu-arbitration.md`, `concepts/dual-circuit.md`,
  `guides/troubleshooting.md`, `decisions/decision-log.md`.
- Источники: AGENTS.md, PIPELINE.md, FLIR.md, MIGRATION_PLAN.md.

## [2026-07-09] lint | Сверка с паттерном LLM Wiki
Перепроверка реализации против оригинального описания паттерна. Исправления:
- Добавлена перемычка в корневой `AGENTS.md` (раздел «LLM Wiki») — иначе агент в будущих
  сессиях не знал бы о схеме вики и не поддерживал её.
- Введена категория `entities/` (страницы сущностей/подсистем, аналог персонажей в фан-вики) +
  засеяна `entities/pipeline.md`.
- Уточнено разделение `entities/` vs `concepts/` в схеме и индексе.
Форматы `index.md`/`log.md` и воркфлоу ingest/query/lint признаны соответствующими.
