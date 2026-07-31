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
- Дополнение: фикс share-списка альбомов (`s_list_albums` собирался SQL по album_photos —
  живые альбомы пропадали); фикс UI `openManualAlbum` (альбом без подальбомов открывался
  пустым); серверный батчинг сетки альбома `photos_page` (44с → ~1с на 4750 фото);
  F5-состояние в URL; спиннер открытия; скрытие «Удалить фото из альбома» в share-режиме;
  страница `entities/albums.md` уточнена.

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
