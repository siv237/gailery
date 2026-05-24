# Gailery — Пайплайн обработки фото

Pipeline — бесконечный цикл последовательных шагов.
Каждый шаг запускает одного воркера через subprocess и ждёт его завершения.
Один GPU — один процесс. Никакого параллелизма.

## Порядок шагов

```
НАПОЛНЕНИЕ:  СКАН → ХЕШ(батч) → ДЕДУП+INGEST
     ↓
    EXIF (без GPU)
     ↓
    FACES (GPU, InsightFace)
     ↓
    DESCRIBE (GPU, llama-server, получает контекст лиц)
     ↓
    EMBED (GPU, семантическая индексация в LanceDB)
     ↓
    Оптимизация LanceDB → повтор пока не 100%
```

AI-шаги батчевые: faces(600) → describe(60) → embed(60) → повтор.

---

## Шаг 1: НАПОЛНЕНИЕ

### Фаза A: Сбор путей (`scan_catalog.py --scan`)
- Обход корневых каталогов из `catalog_roots` (enabled=1)
- Каталоги где mtime < scanned_at — пропускаем целиком
- Новые файлы → добавляем без хеша
- Файл изменился (mtime/size) → пересчитываем xxh128, каскад устаревания
- Файл пропал → deleted=1, deleted_type='auto_missing'
- Файл вернулся с тем же хешем → deleted=0, флаги НЕ сбрасываем
- После скана: canonical с ingested=0 → photos, ingested=1

### Фаза B: Хеширование (`scan_catalog.py --hash --limit N`)
- Canonical файлы без content_hash → xxh128 батчами (по умолчанию 200)
- ~8 файлов/с, упирается в диск

### Фаза C: Дедуп+Ingest (`scan_catalog.py --dedup-ingest`)
- Группировка по content_hash, is_canonical=1 для одного, остальные дубли
- Canonical с ingested=0 → photos

### Цикл наполнения
```
Пока unhashed > 0 или exif < 100%:
  СКАН
  Если unhashed > 0: ХЕШ → ДЕДУП+INGEST
  Если exif < 100%: EXIF
```

---

## Шаг 2: EXIF (`exif.py --all`)
- Только фото (у видео свой механизм через ffprobe)
- Читаем: дата, GPS, камера (exifread)
- Помечаем `exif_checked=1` — даже если EXIF нет
- Всегда `--all`
- Не требует GPU

---

## Шаг 3: ЛИЦА (`faces.py --limit 600`)
- Находим canonical фото (не видео) с `faces_done=0`
- InsightFace: детекция → векторы → DBSCAN кластеризация
- `faces_done=1` для всех обработанных
- `faces_present=1` если лица есть, `faces_present=0` если нет
- Лимит 600 (x10 от describe, опережение)

---

## Шаг 4: ОПИСАНИЕ (`describe.py --limit 60 --batch-size 6`)
- Выполняет `vision_describe.py` как subprocess (local режим, llama-server)
- В Ollama-режиме — собственная реализация через Ollama API

### Контекст (agent-style)
Перед описанием каждого фото собираются все известные данные и передаются VLM:

- **Имена и позиции** персон из faces (слева/центр/справа)
- **Комментарии** персон (родственные связи)
- **Возраст** детей до 18 лет (вычисляется из даты рождения и даты съёмки)
- **Семейные факты** из settings (family_facts)
- **Алиас папки** из catalog_roots
- **Дата съёмки**

VLM получает это как текстовый контекст в user message.
Системный промт минимальный: описать фактами, подставлять имена вместо «девушка/женщина», указать родственные связи.

### Логика
- `faces_done` НЕ ставится — это только InsightFace
- `faces_present` — если `faces_done=1`: от InsightFace; если `faces_done=0`: от VLM (фоллбэк)
- Видео → «[видео]» без VLM

---

## Шаг 5: ИНДЕКСАЦИЯ (`embed.py --limit 60`)
- canonical фото с описанием, без эмбеддинга
- Текст для индекса: имена лиц + описание VLM + путь + дата + камера + GPS
- Qwen3-Embedding-0.6B (llama-cpp-python) или Ollama
- Хранится в LanceDB (photo_embeddings)

---

## Параметры pipeline.py

| Параметр | По умолчанию | Описание |
|---|---|---|
| --batch | 60 | Размер батча AI-шагов |
| --describe | 0 | Переопределить батч описания |
| --batch-size | 6 | Параллельных запросов VLM |
| --hash-limit | 200 | Файлов хешировать за раз |
| --root | "" | Только один root_id |

---

## Устаревание результатов

### Файл перезаписан (content_hash изменился)
- `description = NULL`, `faces_present = 0`, `exif_checked = 0`
- Записи лиц удаляются
- Эмбеддинг удаляется из LanceDB, `embedded = 0`

### Персона изменена (rename/merge/delete)
- `catalog_files.described = 0`, `photos.embedded = 0`
- Эмбеддинги удаляются из LanceDB
- **Описание НЕ удаляется** — pipeline переописал при следующем проходе
- `faces_done` не сбрасывается

---

## Счётчики прогресса

Только по canonical (is_canonical=1, deleted=0):

| Шаг | Сделано | Из скольких |
|---|---|---|
| Наполнение | canonical в photos | canonical всего |
| Хеши | canonical с content_hash | canonical всего |
| EXIF | canonical с exif_checked=1 | canonical+c хешем |
| Лица | faces_done=1 | canonical (не видео) |
| Описание | described=1 | canonical (не видео) |
| Индексация | embedded=1 | canonical (не видео) с описанием |

---

## Промты

Настраиваются через UI (страница «Промты» в разделе AI-бэкенды).
Хранятся в settings БД. Фоллбэк на дефолт из Python-модуля.
VLM и Enrich промты редактируются отдельно.

---

## GPU арбитраж (MQTT)

Топик `{prefix}/gpu/lock` (retained): `{"holder":"describe","since":"...","pid":12345}`

- **Фоновые воркеры** (faces, describe, embed): `acquire_gpu()` — мьютекс, ждёт если занят
- **Временные задачи** (semantic_search): `request_gpu_gentle()` — ждёт до 120с, отказывает если не дождался
- **Enrich**: `request_gpu_for_api()` — жёсткий захват (pause + pkill)
- При завершении: `release_gpu()`, pipeline получает `send_resume`

---

## Pipeline ↔ API

- Pipeline подписан на `{prefix}/db/cmd` — выполняет команды от API
- API отправляет: update_photo, set_gps, control_reset, update_persona, merge_personas и т.д.
- Ответ: `{prefix}/db/result/{request_id}`

---

## Watchdog

Спящий пёс не делает ничего. Просыпается от кнопки «Цепочка».

| Событие | Реакция |
|---|---|
| Кнопка «Цепочка» | Убирает no_restart, включает pipeline |
| Кнопка «Стоп» | Ставит no_restart, отключает pipeline |
| Pipeline упал (пёс активен) | Перезапускает |
| Сироты llama-server (пёс активен) | Убивает |
| Пёс спит | Ничего не делает |

---

## Логирование

Все воркеры пишут в `logs/pipeline.log`.
Формат: `[дата-время] [ТЕГ] сообщение`.
Теги: CATALOG, DESCRIBE, FACES, EXIF, EMBED, PIPELINE, ENRICH, WATCHDOG, CONTROL, VLM.
