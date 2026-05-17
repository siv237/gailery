# Gailery — Контекст проекта

## Что это
Фото-галерея, Python/FastAPI/SQLite+LanceDB, веб-фронтенд. GPU NVIDIA (проверено на P104-100, Pascal SM 6.1, 8GB VRAM).

## Спецификация пайплайна
**См. [PIPELINE.md](PIPELINE.md)** — полная документация логики, шагов, батчей, MQTT, счётчиков.

---

## FUNDAMENTAL: Двухконтурная архитектура (dual-circuit)

### Принцип
Все GPU-задачи (кроме describe/faces) должны работать в двух режимах:

| Режим | Бэкенд | Характер |
|---|---|---|
| **local** (по умолчанию) | transformers / llama-cpp-python | Прямой GPU, без зависимостей |
| **ollama** | Ollama HTTP API | Использует запущенный сервер Ollama (локальный или сетевой) |

### Конфигурация в `config.py`
```python
OLLAMA_MODE = "local"          # "local" | "ollama"
OLLAMA_BASE_URL = "http://192.168.237.158:11434"  # или http://localhost:11434
OLLAMA_EMBED_MODEL = "qwen3-embedding:0.6b"
```

### Реализация в каждом воркере
```python
if config.OLLAMA_MODE == "ollama":
    result = ollama_request("POST", "/api/embed", body)
else:
    result = local_engine.encode(texts)
```

### Что реализовано двухконтурно
- [x] **embed** — семантическая индексация (transformers/llama-cpp-python vs Ollama)
- [x] **semantic_search** — поиск (через EmbedEngine, оба режима)
- [ ] **enrich_description** — обогащение описаний (llama.cpp vs Ollama)
- [x] **describe** — описание фото (llama-server vs Ollama/VLM)
- [ ] **exif** — не требует GPU, всегда локально

### Что НЕ двухконтурно (всегда локально)
- faces — InsightFace GPU

### Преимущества
- По умолчанию работает без Ollama (автономно)
- При наличии Ollama — использует её оптимизированный llama.cpp
- Ollama может быть на другой машине (сетевой доступ)

---

## FUNDAMENTAL: Идентификация файлов и счётчики

### Принцип идентификации
**Идентификация файлов — через `content_hash` (xxh128), НЕ через пути.** Пути хранятся справочно, могут меняться (маунты, переезды, форматы относительный/абсолютный). `content_hash` — единственный надёжный идентификатор. Все привязки результатов обработки (faces, embeddings, описания) — через `content_hash`.

### Счётчики прогресса
**Все счётчики — по уникальным файлам** (`catalog_files.is_canonical=1`, `deleted=0`). Дубли (`is_canonical=0`) хранятся в `catalog_files` только справочно для путей и контроля дублей, **никогда не обрабатываются** и не участвуют в подсчёте прогресса.

Каждая карточка прогресса = `сделано / всего` по canonical:
- Наполнение: canonical в photos (deleted=0) / canonical в catalog
- Описание: canonical с description / canonical всего
- Лица: canonical с faces_present=1 И есть записи в faces (по content_hash) / canonical с faces_present=1
- EXIF: canonical с exif_checked=1 / canonical всего
- Семантическая индексация: canonical с embedded=1 / canonical всего

### Таблицы и связи
```
catalog_files: file_id, root_id, rel_path, abs_path, content_hash(xxh128), is_canonical, ingested, described, exif_done, faces_done, embedded, deleted, deleted_type
catalog_roots: root_id, root_path, alias, enabled, scanned_at
photos: photo_id(UUID), path(=catalog_files.abs_path), description, faces_present, exif_checked, embedded, deleted, root_id
faces: face_id, photo_id(ПУТЬ — legacy, НЕ ИСПОЛЬЗОВАТЬ ДЛЯ JOIN), content_hash(НОВОЕ), persona_id, bbox_x1/y1/x2/y2, confidence
personas: persona_id, display_name, comment
```

Связь faces → photos: `faces.content_hash` → `catalog_files.content_hash` (is_canonical=1) → `catalog_files.abs_path` = `photos.path`

### Хеширование файлов
`compute_file_hash()` в `scan_catalog.py`: xxhash.xxh128, 128-bit хеш содержимого файла. Вызывается при сканировании, записывается в `catalog_files.content_hash`.

---

## FUNDAMENTAL: GPU ARBITRATION — ВСЕГДА ЧИТАТЬ ПЕРЕД ЛЮБЫМИ ИЗМЕНЕНИЯМИ GPU-КОДА

### Железо
1 видеокарта P104-100, 8GB VRAM. Одновременно на GPU может быть ТОЛЬКО ОДИН процесс. Никаких исключений.

### Два класса задач

| Класс | Примеры | Характер | Приоритет |
|---|---|---|---|
| **Фоновые** | describe (VLM), faces (InsightFace), embed (llama-server) | Длительные, запускаются pipeline.py последовательно через subprocess.run | Высокий — работают пока не закончат или пока не остановят вручную |
| **Временные** | semantic_search (embedding server), enrich (text LLM) | Короткие, запускаются по запросу пользователя из API | Низкий — должны вклиниться, НЕ крашить фоновые, НЕ занимать GPU вторым процессом |

### Правила — НАРУШЕНИЕ ЛЮБОГО = БАГ

1. **NEVER два GPU-процесса одновременно.** Ни при каких обстоятельствах. Если на GPU уже кто-то — второй ЖДЁТ или ОТКАЗЫВАЕТ, но никогда не лезет поверх.

2. **Фоновые задачи взаимно исключают друг друга через pipeline.** Pipeline запускает describe→faces→embed ПОСЛЕДОВАТЕЛЬНО (subprocess.run, блокирующий). Между шагами pipeline убивает orphan llama-server. Два фоновых воркера никогда не работают параллельно.

3. **Временные задачи используют MQTT GPU lock.** Перед запуском llama-server/API-воркера:
   - `request_gpu_gentle()` для поиска — ждёт до 120с, отказывает если GPU занят, НЕ убивает ничьи процессы
   - `request_gpu_for_api()` для enrich — жёсткий захват (пользователь ждёт кнопку), pause + pkill если не отдали за 3с
   - После завершения — `release_gpu_from_api()`, send_resume

4. **Фоновые воркеры используют `acquire_gpu()` (WorkerMQTT).** Это реальный мьютекс: читает MQTT lock topic, проверяет holder, если занят — ждёт, если holder мёртв (PID не существует) — чистит stale lock. Только после успешного acquire — `gpu_held=True`. При завершении — `release_gpu()`.

5. **Сироты llama-server — УБИВАТЬ.** Если describe крашнется — llama-server остаётся с ppid=1. Pipeline убивает orphan llama-server перед каждым GPU-шагом. Watchdog тоже детектит сирот.

6. **Никогда не запускать второй pipeline.** Кнопка "chain" в UI убивает старый pipeline перед запуском нового. Watchdog убивает дубликаты.

7. **GPU lock topic** — `{MQTT_PREFIX}/gpu/lock` (retained MQTT): `{"holder":"faces","since":"...","pid":12345}`. Пустой = свободен. Все проверки идут через него.

### Watchdog (сторожевой пёс) — область ответственности

**Пёс отвечает ТОЛЬКО за пайплайн (бесконечный цикл pipeline.py). Ничего больше.**

**СПЯЩИЙ ПЁС СПИТ. Спящий пёс НЕ ДЕЛАЕТ НИЧЕГО — ни проверок, ни убийств, ни рестартов. Разбудить его можно ТОЛЬКО кнопкой «Цепочка» в интерфейсе. Всё что происходит пока пёс спит — ему похуй.**

| Событие | Реакция пса |
|---|---|
| Кнопка "Цепочка" (chain) | **Просыпается**: убирает `no_restart`, enable pipeline, начинает следить |
| Кнопка "Стоп" | **Засыпает**: ставит `no_restart`, disable pipeline, больше ничего не делает |
| Кнопка индивидуального шага (embed, faces и т.д.) | **ИГНОРИРУЕТ** — пёс продолжает спать |
| Pipeline упал сам (пёс активен) | Перезапускает |
| Сироты, память, дубликаты (пёс активен) | Проверяет и чистит |
| Сироты, память, дубликаты (пёс спит) | **ИГНОРИРУЕТ** — спящий пёс ничего не делает |

**Пёс НЕ должен:**
- Следить за индивидуальными воркерами (embed, faces, describe, exif, ingest)
- Просыпаться от того что индивидуальный шаг запустился или завершился
- Запускать pipeline когда работает индивидуальный шаг
- Менять `no_restart` флаг при индивидуальном запуске
- Ре-энаблить pipeline (ensure_pipeline_enabled) — если disabled, значит disabled
- Делать ЛЮБЫЕ проверки когда спит (no_restart стоит)

**Пёс ДОЛЖЕН (только когда активен):**
- Убивать дубликаты pipeline.py
- Убивать сирот llama-server (ppid=1, не от кнопки)
- Следить за памятью
- Перезапускать упавший pipeline

**Логика сна/пробуждения:**
- `no_restart` флаг существует → пёс спит, цикл делает только heartbeat и sleep
- `no_restart` флаг убран → пёс просыпается, начинает активный цикл
- Pipeline disabled → пёс НЕ пытается его ре-энаблить, НЕ запускает
- Только кнопка Цепочка убирает `no_restart` и enable pipeline

### Что уже сделано для арбитража
- `acquire_gpu()` в WorkerMQTT — реальный мьютекс с verify после записи
- `release_gpu()` — проверяет что мы holder перед очисткой
- `request_gpu_gentle()` в ApiMQTT — мягкий захват, timeout=120s, отказ если занят
- `request_gpu_for_api()` в ApiMQTT — жёсткий захват (enrich)
- `kill_orphan_llama_servers()` в pipeline.py — перед каждым GPU-шагом
- `check_duplicate_pipelines()` / `check_orphan_workers()` / `check_memory_pressure()` в watchdog.py
- faces.py, embed.py, vision_describe.py используют `acquire_gpu()` перед работой
- semantic_search использует `request_gpu_gentle()`
- enrich использует `request_gpu_for_api()`

---

## Логика пайплайна — полная спецификация

### Корневые пути сканирования
Пути берутся из таблицы `catalog_roots` (где `enabled=1`). Регистрируются вручную через `scan_catalog.py --add <путь>`. Каждый root имеет `root_id`, `root_path`, `alias`, `scanned_at`.

### Шаг 1: Скан + Наполнение (scan + ingest = один процесс)

Это единый процесс. Не два отдельных.

1. **Читаем `catalog_roots`** (enabled=1), для каждого root:
   - **Быстрый обход директорий**: сравниваем `dir.mtime` с `catalog_roots.scanned_at`
   - Если `mtime < scanned_at` — пропускаем директорию целиком (ничего не изменилось)
   - Если `mtime >= scanned_at` — заходим внутрь, сканируем файлы

2. **Обработка файлов**:
   - **Новый файл** (rel_path не в catalog_files): вычисляем xxh128, добавляем в `catalog_files`, после скана — `mark_canonical_duplicates()` определяет `is_canonical`
   - **Существующий файл, mtime/size изменились**: пересчитываем xxh128, обновляем запись. Если `content_hash` изменился — помечаем все зависимые шаги как устаревшие (см. раздел "Устаревание результатов")
   - **Существующий файл, не изменился**: пропускаем

3. **Удалённые файлы**:
   - Файл пропал с диска → **НЕ удаляем** из `catalog_files`
   - Ставим `catalog_files.deleted = 1`, `deleted_type = 'auto_missing'`
   - Если фото было в `photos` → `photos.deleted = 1`
   - **Файл вернулся**: если файл снова на месте:
     - xxh128 совпадает с `content_hash` в БД → снимаем `deleted=0`, `deleted_type=NULL`, **флаги обработки НЕ сбрасываем** (результаты актуальны)
     - xxh128 НЕ совпадает → новый `content_hash`, помечаем все зависимые шаги как устаревшие

4. **Добавление новых canonical в photos**:
   - После скана: все `catalog_files` с `is_canonical=1, ingested=0, deleted=0` → добавить в `photos`
   - Пометить `ingested=1`

5. **Очистка дублей в photos**:
   - `photos` записи где `catalog_files.is_canonical=0` → `photos.deleted=1`
   - Эти дубли не должны были попасть в photos, но могли попасть раньше

6. Обновить `catalog_roots.scanned_at`

### Шаг 2: Описание (describe)

1. Найти canonical photos с `description IS NULL` и `deleted=0`
2. VLM (llama-server + Qwen3.5-4B-Q4_K_M.gguf + mmproj) генерирует описание + ставит `faces_present=True/False`
3. Счётчик: canonical photos с `description IS NOT NULL` / все canonical photos (deleted=0)

### Шаг 3: Лица (faces)

1. Найти canonical photos с `faces_present=1, deleted=0` у которых **нет записей в faces по `content_hash`**
2. InsightFace GPU: детекция, векторные представления, кластеризация в персоны (DBSCAN на GPU)
3. Запись в `faces` — **обязательно с `content_hash`** из `catalog_files`
4. Счётчик: canonical photos с `faces_present=1` И есть записи в faces (по content_hash) / canonical photos с `faces_present=1`

### Шаг 4: EXIF

1. Найти canonical photos с `exif_checked=0` и `deleted=0`
2. Читаем EXIF, записываем дату/GPS/камеру
3. Счётчик: canonical photos с `exif_checked=1` / все canonical photos (deleted=0)

### Шаг 5: Семантическая индексация (embed)

1. Найти canonical photos с `embedded=0, deleted=0` (только с `description IS NOT NULL`)
2. Собираем текст из описания + имена лиц + папка + дата
3. Генерируем семантические индексы (llama-server + Qwen3-Embedding-0.6B-F16.gguf), храним в LanceDB
4. Счётчик: canonical photos с `embedded=1` / все canonical photos (deleted=0)
5. Важно: НЕ использовать delete_photo_embedding() — только embedded=0 в SQLite

### Цикл pipeline

1. Запускается шаг 1 (scan+ingest)
2. Считаем прогресс каждого шага (только по canonical unique файлам, deleted=0)
3. Запускаем незавершённые шаги по порядку: describe → faces → exif → embed
4. Каждый шаг проверяет `content_hash` для привязки результатов
5. Все 100% → засыпаем, watchdog разбудит при изменениях

### Устаревание результатов (content_hash изменился)

Если у canonical файла изменился `content_hash` (файл перезаписан):
- `description` → сбросить (NULL), `faces_present=0`
- Записи в `faces` с этим `content_hash` → удалить
- `embedded=0`, семантическую индексацию из LanceDB удалить
- `exif_checked=0`

Это гарантирует что результаты всегда соответствуют актуальному содержимому файла.

### Миграция: faces.photo_id → faces.content_hash

1. Добавить колонку `faces.content_hash TEXT`
2. Создать индекс `idx_faces_content_hash`
3. Заполнить: `faces.photo_id` → `catalog_files` (по rel_path ИЛИ abs_path) → `content_hash`
4. Для записей где photo_id не нашёлся в catalog — content_hash=NULL (orphan, игнорируем)
5. Дальше все проверки и JOIN — через `content_hash`

---

## Текущая задача: enrich_description — обогащение описаний

### Проблема
VLM описание: "женщина в синей куртке стоит слева, мужчина в чёрной куртке в центре"
Реальность: Иванова Анна (x=723, слева), Петров Алексей (x=1033, центр), (без имени) (x=2200, справа)
Папка: "Петровы и Друзья"

Нужно: LLM берёт базовое описание + данные лиц + папку + дату → пишет обогащённое описание с именами.

### Что уже сделано
1. ✅ `rich_description` колонка в photos таблице SQLite
2. ✅ `enrich_description.py` — воркер, llama-server on-demand (порт 8103), POST /v1/chat/completions
3. ✅ API endpoint `POST /api/photos/{photo_id}/enrich` в src/api/photos.py
4. ✅ `rich_description` в ответе фото API
5. ✅ Кнопка "Обогатить описание" + отображение в detail-панели gallery.html
6. ✅ Первый рабочий тест — модель подставила имя вместо описания одежды

### Текущий промт (надо улучшать)
SYSTEM: правила замены имён, позиций, обрезания длинных списков
USER: базовое описание + папка + дата + список лиц с bbox

### Проблемы текущего промта
- Иванова Анна НЕ была подставлена (VLM написал "её лицо не видно" — модель не сопоставила)
- Папка "Петровы и Друзья" не использована в контексте
- Модель не имеет доступа к дополнительным данным в режиме размышлений

### Следующий шаг (по указанию пользователя)
Дать модели **инструменты извлечения данных** — чтобы в режиме размышлений (thinking) она могла:
- Запросить подробности о конкретном лице (сколько фото с этим persona, comment)
- Запросить контекст папки (сколько фото, какие ещё люди там)
- Посмотреть соседние фото по дате
- Использовать всё это для более точного обогащения

Это значит: модель работает в **tool-calling** режиме — llama-server поддерживает `tools` в chat/completions API.

### Архитектура решения
1. Определить набор tools (get_persona_info, get_folder_context, get_nearby_photos)
2. В enrich_description.py: отправлять промт с tools, парсить tool_calls, выполнять их через БД, возвращать результаты
3. Цикл: model → tool_call → execute → result → model (повторять пока не даст финальный ответ)
4. llama-server Qwen3.5-4B поддерживает function calling через chat template

### Ключевые файлы
- `enrich_description.py` — воркер обогащения (llama-server порт 8103, SYSTEM_PROMPT, format_faces, run_llm через API)
- `src/api/photos.py` — API endpoint enrich + rich_description в ответе
- `web/gallery.html` — кнопка + отображение rich_description (dp-desc с золотым бордером)
- `src/database.py` — DatabaseManager, все методы работы с БД
- `models/gguf/Qwen3.5-4B-Q4_K_M.gguf` — текстовый LLM 2.7GB

### Формат промта для tool-calling
Qwen3.5-4B поддерживает функции через chat template. Формат:
```json
{"messages": [...], "tools": [{"type": "function", "function": {"name": "...", "parameters": {...}}}]}
```
Модель вернёт tool_call в ответе, нужно выполнить и вернуть tool result.

---

### GPU ограничения
- P104-100 Pascal SM 6.1, cuDNN 9.x НЕ работает
- onnxruntime-gpu 1.18.0 + cuDNN 8.x — работает (ldconfig настроен)
- llama.cpp — работает через custom CUDA kernels (без cuDNN)

---

## Тестирование

### Запуск
```bash
./run_tests.sh                  # все тесты
./run_tests.sh tests/test_database.py   # только база
./run_tests.sh tests/test_api.py        # только API
./run_tests.sh tests/test_environment.py # проверка окружения
```

Или напрямую:
```bash
/opt/gailery/venv/bin/python3 -m pytest tests/ -v
```

### FUNDAMENTAL: Политика тестирования — НЕНАРУШИМО

**Категорически запрещены любые тесты изменяющие реальную БД или состояние системы.**

Три уровня тестов и где они работают:

| Уровень | Тип | Где работает | Пример |
|---|---|---|---|
| **PRIMARY (read-only)** | Проверка что живая галерея отвечает валидным JSON и данные корректны | **Реальная БД** — read-only GET запросы к живой галерее | `test_environment.py` — все тесты |
| **SECONDARY (write tests)** | CRUD, мутации, операции изменения данных | **Миникопия реальной БД** — копия структуры + ограниченный набор строк из реальной БД | `test_user_flows.py` — операции с фото |
| **TERTIARY (unit)** | Изолированные юнит-тесты | **Временная БД** — `tmp_path`, пустая БД с тестовыми данными | `test_database.py`, `test_api.py` |

**Правила:**
- Read-only тесты выполняются всегда (`-k "not gpu and not ai"`)
- Write-тесты делают копию структуры реальной БД + первые N строк данных, работают на копии, удаляют после
- **Никогда не скипать write-тесты** — переписать на миникопию
- Деструктивные тесты (control/start, control/stop) — только на изолированном окружении, не на продакшене
- Миникопия БД для write-тестов: `sqlite3 production.db ".dump" | sqlite3 test_copy.db`

### Что покрывают

| Файл | Что тестирует | Тип |
|---|---|---|
| `test_environment.py` | Зависимости, сервисы systemd, процессы, API JSON-валидность, консистентность режимов | PRIMARY — живая БД, read-only |
| `test_database.py` | CRUD фото/лиц/персон/каталога, поиск, гистограммы, обновления, миграции | TERTIARY — временная БД |
| `test_middleware.py` | BFCACHE-fix middleware, SPA fallback, HEAD→GET, редиректы ошибок, маршруты страниц | TERTIARY — временная БД |
| `test_api.py` | /api/photos/search, dates, GPS, delete, persons, catalog, health, log, changes | TERTIARY — временная БД |
| `test_mqtt.py` | MQTT worker lifecycle, API статус, GPU арбитраж, fallback на флаги | TERTIARY — MQTT-only, БД не трогает |
| `test_gallery_ui.py` | UI API эндпоинты с content_hash, фильтры, карта, статус, персоны | TERTIARY — mock-данные |
| `test_user_flows.py` | E2E user flows (галерея, поиск, персоны, фото-операции) | SECONDARY — миникопия БД |
| `test_performance.py` | Производительность БД и API с бюджетами времени | PRIMARY — живая БД, read-only |
| `test_pipeline_control.py` | Control API, watchdog mode, Ollama embed/describe settings | MIXED — часть на временной БД |

### Как это работает
- PRIMARY тесты подключаются к `localhost:8000` и проверяют что живая система отвечает
- SECONDARY тесты создают копию реальной БД через `sqlite3` dump, работают на копии
- TERTIARY тесты создают **временную БД** в `tmp_path` (pytest cleanup)
- Фикстуры патчат `config` и `database` модули, чтобы указывать на временные пути
- `app_client` — Starlette TestClient, делает HTTP-запросы к FastAPI app без запуска сервера

### Когда запускать
- После любых изменений в `src/database.py`, `src/main.py`, `src/api/`
- Перед коммитом — убедиться что ничего не сломано
- При обновлении зависимостей (LanceDB, FastAPI и т.д.)

## Правила
- Все изменения фиксировать в git локально
- **ЗАПРЕЩЕНЫ любые git commit/push без прямого распоряжения пользователя**
- Сервис перезапускается через `systemctl restart gailery.service`
- **Перед ЛЮБЫМ действием описывать словами что и зачем делаешь.** Никаких немых правок.
- Работать на русском языке
- **НИКОГДА не обрезать вывод команд.** Пользователь должен видеть полный вывод в реальном времени, иначе он думает что процесс завис. Никаких `tail`, `head`, `2>&1 | tail -30`, `| head` или других ограничителей вывода. Если вывод слишком длинный — Bash-инструмент сам запишет его в файл, но не добавляй искусственных ограничителей.
- Не downgrade пакеты без согласия
- Останавливать pipeline только кнопкой стоп (флаг no_restart), не kill процессов вручную
