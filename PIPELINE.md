# Gailery — Пайплайн обработки фото

## Принцип

Пайплайн — бесконечный цикл последовательных шагов. Каждый шаг — subprocess (воркер). Pipeline блокируется на время работы воркера (subprocess.run), между шагами закрывает БД.

**Нет фоновых процессов. Нет параллельных воркеров. Один GPU — один процесс.**

---

## Шаги пайплайна (порядок)

```
1. НАПОЛНЕНИЕ  — скан директорий + хеширование + ingest в photos
2. EXIF        — чтение метаданных (CPU, не GPU)
3. ОПИСАНИЕ    — VLM описывает фото (GPU)
4. ЛИЦА        — InsightFace детекция + кластеризация (GPU)
5. ИНДЕКСАЦИЯ  — семантические эмбеддинги (GPU)
```

---

## Шаг 1: Наполнение (scan_catalog.py)

### Фаза A: Быстрый скан директорий
- Обход `catalog_roots` (enabled=1)
- Сравнение `dir.mtime` с `catalog_roots.scanned_at` — пропускаем неизменённые
- Новые файлы → INSERT в `catalog_files` с `content_hash=NULL`
- Изменённые (mtime/size) → пересчитать хеш, при изменении — сбросить зависимые флаги
- Удалённые с диска → `deleted=1, deleted_type='auto_missing'`
- Вернувшиеся → `deleted=0`, проверить хеш

**Результат скана**: все пути файлов в `catalog_files`, но `content_hash=NULL` для новых. Это нормально — хеши ещё не посчитаны.

### Фаза B: Хеширование батчами
- Выбирает файлы с `content_hash=NULL AND size>0 AND deleted=0`
- **Лимит батча** (параметр `hash_limit`, дефолт 500): обрабатывает N файлов за раз
- Для каждого файла: `compute_file_hash(abs_path)` → xxh128
- Пишет хеш в `catalog_files.content_hash` (батч INSERT каждые 500)
- **Лог каждые 200 файлов**: `Hashing 1200/180000 (45.2s, 26/s)`

### Фаза C: Dedup + Ingest (после хеширования)
- `mark_canonical_duplicates()`: группирует по `content_hash`, помечает дубли `is_canonical=0`
  - Предпочитает уже-описанные, потом кратчайший путь
- `_ingest_new_canonical()`: canonical с `content_hash≠NULL` и `ingested=0` → INSERT в `photos`
  - **NOT EXISTS** проверка — не добавлять если фото уже в photos
- `_cleanup_noncanonical_photos()`: помечает `deleted=1` дубли в photos + удаляет записи с повторяющимся path

### Счётчик Наполнение
- **Найдено**: COUNT(catalog_files WHERE deleted=0) — все файлы на диске
- **Уникальных**: COUNT(catalog_files WHERE is_canonical=1 AND content_hash IS NOT NULL AND deleted=0)
- **В photos**: COUNT(photos WHERE deleted=0)
- **Прогресс**: уникальных / найденных (уменьшается по мере нахождения дублей)

### Важно
- Файлы без хеша — нормальные записи, просто не обработаны
- Воркеры downstream (exif, describe, faces, embed) работают ТОЛЬКО с canonical + content_hash≠NULL
- Счётчики downstream считают от canonical+hashed, не от общего числа

---

## Шаг 2: EXIF (exif.py)

- **Не GPU**, можно запускать пока GPU свободен
- Ищет: `photos WHERE exif_checked=0 AND canonical AND content_hash≠NULL AND deleted=0`
- Читает EXIF: дата, GPS, камера
- Ставит `exif_checked=1` даже если EXIF нет (не повторяет)
- **Лимит**: `--limit N` (0=все, дефолт из UI)

---

## Шаг 3: Описание (describe.py / vision_describe.py)

- **GPU**: llama-server + Qwen3.5-4B VLM
- Перед запуском: `kill_orphan_llama_servers()`
- Ищет: `photos WHERE description IS NULL AND canonical AND content_hash≠NULL AND deleted=0`
- Видеофайлы: описание = `'[видео]'` (миграция, не VLM)
- VLM генерирует описание + ставит `faces_present=True/False`
- **Лимит**: `--limit N` (дефолт 60), `--batch-size` (дефолт 6)
- После: закрывает llama-server

---

## Шаг 4: Лица (faces.py)

- **GPU**: InsightFace
- Перед запуском: `kill_orphan_llama_servers()`
- Ищет: `photos WHERE faces_present=1 AND canonical AND content_hash≠NULL AND deleted=0`
  - И НЕТ записей в `faces` по этому `content_hash`
- InsightFace: детекция, векторные представления
- DBSCAN кластеризация → personas
- Запись в `faces` с `content_hash`
- **Лимит**: `--limit N` (0=все)

---

## Шаг 5: Индексация (embed.py)

- **GPU**: llama-server + Qwen3-Embedding
- Перед запуском: `kill_orphan_llama_servers()`
- Ищет: `photos WHERE embedded=0 AND description IS NOT NULL AND canonical AND content_hash≠NULL AND deleted=0`
- Собирает текст: описание + имена лиц + папка + дата
- Генерирует эмбеддинги, хранит в LanceDB
- **Лимит**: `--limit N` (0=все)

---

## Цикл pipeline.py

```
while not stopped():
    1. process_db_cmds()    — MQTT команды от API
    2. collect_metrics()    — системные метрики
    3. get_progress()       — считать прогресс всех шагов
    4. QUICK SCAN           — subprocess: scan_catalog.py --scan
    5. Если pending_hash > 0:
         HASH              — subprocess: scan_catalog.py --hash --hash-limit N
    6. EXIF                — subprocess: exif.py --limit N
    7. DESCRIBE            — subprocess: describe.py --limit N --batch-size M
    8. FACES               — subprocess: faces.py --limit N
    9. EMBED               — subprocess: embed.py --limit N
    10. DEDUP+COMPACT       — LanceDB оптимизация
    11. Если прогресса нет — спать 30с, ждать wake_flag
    12. Если все 100%      — спать 30с, ждать новых фото
```

### Параметры pipeline.py

| Параметр | Дефолт | Описание |
|---|---|---|
| `--batch` | 60 | Размер батча для ingest/describe |
| `--ingest` | 0 | Override ingest batch (0=--batch) |
| `--describe` | 0 | Override describe batch (0=--batch) |
| `--batch-size` | 6 | Батч VLM |
| `--hash-limit` | 500 | Файлов хешировать за раз (0=все) |
| `--root` | "" | Ограничить по root_id |

### Индивидуальные задачи (UI кнопки)

Каждый шаг можно запустить отдельно с собственными параметрами:

| Шаг | Параметр | Дефолт | Воркер |
|---|---|---|---|
| Наполнение | ingest_limit | 500 | ingest.py |
| Хеширование | hash_limit | 500 | scan_catalog.py --hash |
| EXIF | exif_limit | 500 | exif.py --limit |
| Описание | desc_limit | 60 | describe.py |
| Описание | batch_size | 6 | describe.py |
| Лица | faces_limit | 0 | faces.py |
| Индексация | embed_limit | 0 | embed.py |

---

## MQTT

### GPU арбитраж
- `{prefix}/gpu/lock` (retained): `{"holder":"faces","since":"...","pid":12345}`
- Фоновые воркеры: `acquire_gpu()` — мьютекс через MQTT lock
- Временные задачи (search, enrich): `request_gpu_gentle/for_api()`

### Pipeline ↔ API
- Pipeline подписан на `{prefix}/db/cmd` — получает команды от API
- Выполняет: update_photo, set_gps, control_reset, merge_personas, и т.д.
- Отвечает на `{prefix}/db/result/{request_id}`

### Статус
- Pipeline публикует текущий шаг в MQTT → API показывает в UI
- Флаг-файлы в `FLAG_DIR`: `pipeline`, `describe`, `faces`, `exif`, `embed`, `hash`, `pipeline_idle`

---

## Watchdog

**Пёс отвечает ТОЛЬКО за pipeline.**

| Событие | Реакция |
|---|---|
| Кнопка "Цепочка" | Просыпается: убирает no_restart, enable pipeline |
| Кнопка "Стоп" | Засыпает: ставит no_restart, disable pipeline |
| Pipeline упал (пёс активен) | Перезапускает |
| Сироты llama-server (пёс активен) | Убивает |
| Спящий пёс | Ничего не делает |

---

## Устаревание результатов (content_hash изменился)

Если у canonical файла изменился content_hash:
- `description → NULL`, `faces_present=0`
- Записи в `faces` с этим content_hash → удалить
- `embedded=0`, LanceDB эмбеддинг удалить
- `exif_checked=0`

---

## Счётчики прогресса (все — по canonical unique)

| Шаг | Числитель | Знаменатель |
|---|---|---|
| Наполнение | canonical+hashed в photos | canonical+hashed всего |
| EXIF | canonical+hashed с exif_checked=1 | canonical+hashed фото |
| Описание | canonical+hashed с description≠NULL | canonical+hashed фото |
| Лица | canonical+hashed с faces по content_hash | canonical+hashed с faces_present=1 |
| Индексация | canonical+hashed с embedded=1 | canonical+hashed фото |

**Примечание**: "canonical+hashed" = `catalog_files WHERE is_canonical=1 AND content_hash IS NOT NULL AND deleted=0`

---

## Логирование

Все воркеры пишут в `logs/pipeline.log` через `log()` (не `print()`).
API читает этот файл для `/api/log`.
Формат: `[ISO8601] [TAG] message`

Теги: `[CATALOG]`, `[DESCRIBE]`, `[FACES]`, `[EXIF]`, `[EMBED]`, `[PIPELINE]`, `[ENRICH]`, `[WATCHDOG]`, `[CONTROL]`

Прогресс хеширования: каждые 200 файлов → `Hashing 1200/180000 (45.2s, 26/s)`
