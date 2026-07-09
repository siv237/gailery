# Wiki Log

Хронологическая запись событий вики. Append-only.
Формат префикса: `## [YYYY-MM-DD] <ingest|query|lint> | <заголовок>`.
Последние 5 записей: `grep "^## \[" wiki/log.md | tail -5`

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
