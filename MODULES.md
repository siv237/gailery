# MODULES.md — карта модулей проекта

> Сгенерировано `generate_modules.py` (манифест §2.3: --map режим).
> Не редактировать вручную — перегенерировать: `./run_tests.sh --map`

Всего Python файлов: 83
Всего строк кода: 26341

## Структура по директориям

### `/ (корень)` (9102 строк, 26 файлов)

| Файл | Строк | Классы | Функции | Импорты |
|------|-------|--------|---------|---------|
| vision_describe.py | 948 | 0 | 23 | 20 |
| enrich_description.py | 774 | 0 | 18 | 15 |
| pipeline.py | 704 | 0 | 26 | 14 |
| embed.py | 611 | 1 | 19 | 17 |
| scan_catalog.py | 510 | 0 | 16 | 11 |
| exif.py | 479 | 0 | 12 | 16 |
| describe.py | 448 | 0 | 15 | 17 |
| faces.py | 389 | 0 | 16 | 17 |
| watchdog.py | 371 | 0 | 12 | 10 |
| run_chrome.py | 350 | 1 | 5 | 8 |
| bench_vlm.py | 323 | 0 | 3 | 11 |
| benchmark_vision.py | 296 | 0 | 10 | 8 |
| migrate_lance_to_sqlite.py | 296 | 0 | 9 | 9 |
| ingest.py | 279 | 0 | 9 | 13 |
| check_gpu.py | 269 | 0 | 6 | 6 |
| vision_agent.py | 262 | 0 | 6 | 9 |
| bench_monitor.py | 242 | 0 | 7 | 8 |
| bench_torchao.py | 195 | 0 | 7 | 9 |
| test_batch_image.py | 194 | 0 | 4 | 6 |
| generate_thumbnails.py | 181 | 0 | 5 | 11 |
| test_batch_real_images.py | 175 | 0 | 4 | 6 |
| reprocess_photo.py | 170 | 0 | 4 | 8 |
| test_batch.py | 169 | 0 | 3 | 5 |
| bench_vlm_parallel.py | 162 | 0 | 4 | 9 |
| face_pipeline.py | 156 | 0 | 3 | 10 |
| generate_modules.py | 149 | 0 | 3 | 4 |

### `src` (7192 строк, 33 файлов)

| Файл | Строк | Классы | Функции | Импорты |
|------|-------|--------|---------|---------|
| database.py | 1398 | 1 | 3 | 11 |
| main.py | 1320 | 2 | 67 | 32 |
| mqtt_client.py | 546 | 4 | 14 | 10 |
| cluster_personas.py | 429 | 0 | 13 | 12 |
| system_helpers.py | 407 | 0 | 9 | 9 |
| thumbnails.py | 380 | 1 | 10 | 13 |
| persona.py | 273 | 3 | 1 | 5 |
| flir_parser.py | 231 | 0 | 9 | 5 |
| exif.py | 227 | 4 | 1 | 7 |
| system_monitor.py | 213 | 0 | 11 | 8 |
| face_embeddings.py | 210 | 2 | 1 | 10 |
| face_detection.py | 190 | 2 | 1 | 7 |
| process_photos.py | 185 | 0 | 2 | 13 |
| describe_photo.py | 142 | 0 | 1 | 5 |
| match_personas.py | 118 | 0 | 2 | 4 |
| config.py | 111 | 0 | 2 | 3 |
| scanner.py | 107 | 2 | 1 | 4 |
| vlm_log.py | 100 | 0 | 2 | 4 |
| describe_photo_ollama.py | 85 | 0 | 2 | 6 |
| analyze_personas.py | 80 | 0 | 0 | 7 |
| video_metadata.py | 72 | 0 | 3 | 4 |
| test_retinaface_3.py | 67 | 0 | 3 | 3 |
| analyze_group_c.py | 42 | 0 | 0 | 7 |
| recreate_faces_table.py | 39 | 0 | 0 | 5 |
| clear_persona_ids.py | 33 | 0 | 0 | 4 |
| test_retinaface.py | 32 | 0 | 0 | 5 |
| test_search.py | 31 | 0 | 0 | 4 |
| check_clustering.py | 30 | 0 | 0 | 4 |
| clear_all_faces.py | 23 | 0 | 0 | 4 |
| list_photos.py | 23 | 0 | 0 | 4 |
| test_yolo.py | 23 | 0 | 0 | 3 |
| clear_2020_faces.py | 22 | 0 | 0 | 4 |
| __init__.py | 3 | 0 | 0 | 0 |

### `src/api` (3494 строк, 9 файлов)

| Файл | Строк | Классы | Функции | Импорты |
|------|-------|--------|---------|---------|
| photos.py | 1476 | 0 | 32 | 24 |
| catalog.py | 536 | 1 | 17 | 13 |
| persons.py | 368 | 2 | 13 | 5 |
| video.py | 321 | 0 | 10 | 9 |
| models.py | 282 | 0 | 8 | 10 |
| flir.py | 231 | 0 | 9 | 16 |
| search.py | 196 | 0 | 5 | 12 |
| validators.py | 82 | 0 | 4 | 0 |
| __init__.py | 2 | 0 | 0 | 0 |

### `tests` (6553 строк, 15 файлов)

| Файл | Строк | Классы | Функции | Импорты |
|------|-------|--------|---------|---------|
| test_api.py | 1145 | 27 | 0 | 3 |
| test_code_quality.py | 891 | 0 | 40 | 9 |
| test_user_flows.py | 728 | 14 | 10 | 6 |
| test_database.py | 646 | 17 | 0 | 2 |
| test_performance.py | 532 | 5 | 3 | 7 |
| test_mqtt_unit.py | 472 | 5 | 0 | 7 |
| test_environment.py | 410 | 0 | 25 | 13 |
| test_gallery_ui.py | 351 | 8 | 2 | 7 |
| test_pipeline_control.py | 350 | 8 | 0 | 13 |
| test_security.py | 279 | 0 | 8 | 6 |
| conftest.py | 243 | 0 | 6 | 8 |
| test_system_helpers.py | 227 | 7 | 0 | 6 |
| test_mqtt.py | 184 | 4 | 0 | 9 |
| test_middleware.py | 94 | 4 | 0 | 2 |
| __init__.py | 1 | 0 | 0 | 0 |

## God Objects (классы с >20 методов)

| Методов | Файл | Класс | Строка |
|---------|------|-------|--------|
| 85 | src/database.py | DatabaseManager | 52 |
| 26 | tests/test_mqtt_unit.py | TestApiMQTT | 235 |

## Топ-10 файлов по размеру

| Строк | Файл |
|-------|------|
| 1476 | src/api/photos.py |
| 1398 | src/database.py |
| 1320 | src/main.py |
| 1145 | tests/test_api.py |
| 948 | vision_describe.py |
| 891 | tests/test_code_quality.py |
| 774 | enrich_description.py |
| 728 | tests/test_user_flows.py |
| 704 | pipeline.py |
| 646 | tests/test_database.py |
