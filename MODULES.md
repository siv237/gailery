# MODULES.md — карта модулей проекта

> Сгенерировано `generate_modules.py` (манифест §2.3: --map режим).
> Не редактировать вручную — перегенерировать: `./run_tests.sh --map`

Всего Python файлов: 83 | Строк: 27140 | Endpoint'ов: 117 | Публичных функций: 400

## Структура по директориям

### `/ (корень)` (9593 строк, 26 файлов, 0 endpoints)

| Файл | Строк | Endpoints | Публ.функций | Хелперов | Классы |
|------|-------|-----------|-------------|----------|--------|
| vision_describe.py | 1037 | 0 | 16 | 25 | — |
| enrich_description.py | 775 | 0 | 12 | 6 | — |
| pipeline.py | 746 | 0 | 9 | 29 | — |
| embed.py | 645 | 0 | 8 | 18 | EmbedEngine |
| exif.py | 563 | 0 | 10 | 20 | — |
| scan_catalog.py | 548 | 0 | 10 | 12 | — |
| describe.py | 448 | 0 | 6 | 9 | — |
| faces.py | 389 | 0 | 7 | 9 | — |
| watchdog.py | 377 | 0 | 10 | 6 | — |
| run_chrome.py | 350 | 0 | 2 | 3 | Handler |
| generate_modules.py | 329 | 0 | 1 | 7 | — |
| bench_vlm.py | 323 | 0 | 3 | 0 | — |
| benchmark_vision.py | 296 | 0 | 10 | 0 | — |
| migrate_lance_to_sqlite.py | 296 | 0 | 3 | 6 | — |
| ingest.py | 279 | 0 | 9 | 0 | — |
| check_gpu.py | 269 | 0 | 6 | 0 | — |
| vision_agent.py | 262 | 0 | 6 | 0 | — |
| bench_monitor.py | 242 | 0 | 7 | 0 | — |
| generate_thumbnails.py | 198 | 0 | 5 | 4 | — |
| bench_torchao.py | 195 | 0 | 7 | 0 | — |
| test_batch_image.py | 194 | 0 | 4 | 0 | — |
| test_batch_real_images.py | 175 | 0 | 4 | 0 | — |
| reprocess_photo.py | 170 | 0 | 4 | 0 | — |
| test_batch.py | 169 | 0 | 3 | 0 | — |
| bench_vlm_parallel.py | 162 | 0 | 4 | 0 | — |
| face_pipeline.py | 156 | 0 | 3 | 0 | — |

#### `vision_describe.py` (1037 строк)
*vision_describe.py - Batch image description with Qwen3.5-4B via llama.cpp.*
`vision_describe.py`

**Зависит от:** `config`, `database`, `mqtt_client`, `vlm_log`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `get_system_prompt` |  |
| `log` |  |
| `start_llama_server` |  |
| `kill_orphan_servers` |  |
| `stop_llama_server` |  |
| `describe_one` |  |
| `prepare_image` |  |
| `describe_batch` |  |
| `strip_md_fences` |  |
| `parse_tool_call` |  |
| `get_db` |  |
| `get_undescribed_photos` |  |
| `save_description` |  |
| `process_single` |  |
| `process_directory` |  |
| `main` |  |

**Внутренние хелперы:** 25 (_-функций)

#### `enrich_description.py` (775 строк)
*enrich_description.py - Generate rich description with named persons using LLM.*
`enrich_description.py`

**Зависит от:** `config`, `database`, `mqtt_client`, `vlm_log`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `get_system_prompt` |  |
| `log` |  |
| `get_photo_data` |  |
| `format_faces` |  |
| `execute_tool` |  |
| `start_server` |  |
| `kill_orphan_servers` |  |
| `stop_server` |  |
| `llm_request` |  |
| `run_llm` |  |
| `enrich_photo` |  |
| `main` |  |

**Внутренние хелперы:** 6 (_-функций)

#### `pipeline.py` (746 строк)
*pipeline.py - Batch worker: loops through chain until 100% or stopped.*
`pipeline.py`

**Зависит от:** `config`, `database`, `mqtt_client`, `system_monitor`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `log` |  |
| `get_db` |  |
| `set_flag` |  |
| `clear_flag` |  |
| `stopped` |  |
| `get_progress` |  |
| `run_step` |  |
| `kill_orphan_llama_servers` |  |
| `main` |  |

**Внутренние хелперы:** 29 (_-функций)

#### `embed.py` (645 строк)
*embed.py - Generate text embeddings for semantic search.*
`embed.py`

**Зависит от:** `config`, `database`, `mqtt_client`, `vlm_log`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `log` |  |
| `set_flag` |  |
| `clear_flag` |  |
| `stopped` |  |
| `build_search_text` |  |
| `compute_meta_hash` |  |
| `get_unembedded_photos_sql` |  |
| `main` |  |

**Внутренние хелперы:** 18 (_-функций)

**Класс `EmbedEngine`** (9 методов: 3 публичных, 6 внутренних)
| Метод | Описание |
|-------|----------|
| `encode` |  |
| `encode_single` |  |
| `cleanup` |  |

#### `exif.py` (563 строк)
*exif.py - Read EXIF metadata for photos not yet checked.*
`exif.py`

**Зависит от:** `config`, `database`, `mqtt_client`, `video_metadata`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `extract_date_from_path` |  |
| `normalize_exif_date` |  |
| `resolve_date` |  |
| `log` |  |
| `set_flag` |  |
| `clear_flag` |  |
| `read_exif_one` |  |
| `read_exif_batch` |  |
| `main` |  |
| `flush_batch` |  |

**Внутренние хелперы:** 20 (_-функций)

#### `scan_catalog.py` (548 строк)
*scan_catalog.py - Scan photo directories and populate the file catalog.*
`scan_catalog.py`

**Зависит от:** `config`, `database`, `mqtt_client`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `compute_file_hash` |  |
| `log` |  |
| `get_db` |  |
| `add_root` |  |
| `scan_root` | Фаза A: Сбор путей — БЫСТРО, без хеширования. |
| `hash_batch` | Фаза B: Хеширование батчами — только N файлов за раз. |
| `dedup_ingest` | Фаза C: Дедупликация + наполнение photos. |
| `show_stats` |  |
| `sync_ingest_flags` |  |
| `main` |  |

**Внутренние хелперы:** 12 (_-функций)

#### `describe.py` (448 строк)
*describe.py - Generate VLM descriptions for photos in DB that lack them.*
`describe.py`

**Зависит от:** `config`, `database`, `mqtt_client`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `log` |  |
| `get_system_prompt` |  |
| `set_flag` |  |
| `clear_flag` |  |
| `count_undescribed` |  |
| `main` |  |

**Внутренние хелперы:** 9 (_-функций)

#### `faces.py` (389 строк)
*faces.py - Detect faces, generate embeddings, cluster into personas.*
`faces.py`

**Зависит от:** `cluster_personas`, `config`, `database`, `mqtt_client`, `vlm_log`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `log` |  |
| `set_flag` |  |
| `clear_flag` |  |
| `get_undetected_photos` |  |
| `run_detection` |  |
| `run_clustering` |  |
| `main` |  |

**Внутренние хелперы:** 9 (_-функций)

#### `watchdog.py` (377 строк)
*watchdog.py - Сторожевой пёс пайплайна Gailray.*
`watchdog.py`

**Зависит от:** `config`, `mqtt_client`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `is_no_restart` |  |
| `is_pipeline_active` |  |
| `is_pipeline_enabled` |  |
| `start_pipeline` |  |
| `log_incident` |  |
| `check_duplicate_pipelines` |  |
| `check_orphan_workers` |  |
| `check_memory_pressure` |  |
| `check_stale_flags` |  |
| `main` |  |

**Внутренние хелперы:** 6 (_-функций)

#### `run_chrome.py` (350 строк)
*run_chrome.py — интерактивный тестовый браузер для Gailery.*
`run_chrome.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `browser_loop` |  |
| `start_api` |  |

**Внутренние хелперы:** 3 (_-функций)

**Класс `Handler`** (8 методов: 4 публичных, 4 внутренних)
| Метод | Описание |
|-------|----------|
| `log_message` |  |
| `do_GET` |  |
| `do_POST` |  |
| `do_OPTIONS` |  |

#### `generate_modules.py` (329 строк)
*generate_modules.py — генерация MODULES.md из исходников.*
`generate_modules.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `generate` |  |

**Внутренние хелперы:** 7 (_-функций)

#### `bench_vlm.py` (323 строк)
*Benchmark: 10x same photo description*
`bench_vlm.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `bench_pytorch` |  |
| `bench_llama_server` |  |
| `main` |  |

#### `benchmark_vision.py` (296 строк)
*benchmark_vision.py - A/B тестирование методов оптимизации инференса Qwen3.5-4B 8-bit на P104 (Pasca*
`benchmark_vision.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `make_dummy_image` |  |
| `build_text_inputs` |  |
| `load_model_bnb` |  |
| `prepare_inputs` |  |
| `count_generated_tokens` |  |
| `run_generate` |  |
| `bench_scenario` |  |
| `cleanup` |  |
| `print_table` |  |
| `main` |  |

#### `migrate_lance_to_sqlite.py` (296 строк)
*migrate_lance_to_sqlite.py - Migrate structured data from LanceDB to SQLite.*
`migrate_lance_to_sqlite.py`

**Зависит от:** `database`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `log` |  |
| `migrate` |  |
| `verify` |  |

**Внутренние хелперы:** 6 (_-функций)

#### `ingest.py` (279 строк)
*ingest.py - Ingest photos from catalog into LanceDB photos table.*
`ingest.py`

**Зависит от:** `database`, `mqtt_client`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `log` |  |
| `set_flag` |  |
| `clear_flag` |  |
| `stopped` |  |
| `read_exif` |  |
| `get_uningested` | Get catalog files not yet ingested, optionally filtered. |
| `mark_ingested_batch` |  |
| `ingest` |  |
| `main` |  |

#### `check_gpu.py` (269 строк)
*check_gpu.py - Проверка совместимости vLLM с NVIDIA P104-100 (Pascal, 8GB VRAM)*
`check_gpu.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `check_nvidia_smi` | Проверка через nvidia-smi. |
| `check_pytorch_cuda` | Проверка CUDA через PyTorch. |
| `estimate_model_memory` | Оценка памяти для модели Qwen 3.5 4B |
| `check_vllm_import` | Проверка импорта vLLM. |
| `get_optimal_params` | Получение оптимальных параметров для Pascal P104-100. |
| `main` | Main функция. |

#### `vision_agent.py` (262 строк)
*vision_agent.py - CLI агент для анализа изображений*
`vision_agent.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `load_model` |  |
| `prepare_image` |  |
| `generate_output` |  |
| `analyze_image` |  |
| `chat_text` |  |
| `main` |  |

#### `bench_monitor.py` (242 строк)
*Monitor GPU/CPU-per-core/MEM/IO during VLM benchmark, sample every 1s.*
`bench_monitor.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `sample_gpu` |  |
| `sample_cpu_cores` |  |
| `sample_cpu_total` |  |
| `sample_mem` |  |
| `sample_io` |  |
| `monitor_loop` |  |
| `print_summary` |  |

#### `generate_thumbnails.py` (198 строк)
*generate_thumbnails.py - Batch thumbnail generation using pyvips*
`generate_thumbnails.py`

**Зависит от:** `database`, `mqtt_client`, `thumbnails`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `log` |  |
| `set_flag` |  |
| `clear_flag` |  |
| `generate_one` |  |
| `main` |  |

**Внутренние хелперы:** 4 (_-функций)

#### `bench_torchao.py` (195 строк)
*bench_torchao.py - A/B тест: BitsAndBytes 8-bit vs TorchAo Int8WeightOnly на P104 (Pascal)*
`bench_torchao.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `make_image` |  |
| `build_text` |  |
| `load_bnb` |  |
| `load_torchao` |  |
| `bench` |  |
| `cleanup` |  |
| `main` |  |

#### `test_batch_image.py` (194 строк)
*test_batch_image.py - Test batched image description with Qwen3.5-4B*
`test_batch_image.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `load_model` |  |
| `prepare_image` |  |
| `run_image_batch_test` |  |
| `main` |  |

#### `test_batch_real_images.py` (175 строк)
*test_batch_real_images.py - Test batched description of 10 DIFFERENT images*
`test_batch_real_images.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `load_model` |  |
| `prepare_image` |  |
| `run_image_batch` |  |
| `main` |  |

#### `reprocess_photo.py` (170 строк)
*reprocess_photo.py - Reprocess single photo: faces → describe → embed.*
`reprocess_photo.py`

**Зависит от:** `database`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `log` |  |
| `reset_photo` |  |
| `run_step` |  |
| `main` |  |

#### `test_batch.py` (169 строк)
*test_batch.py - Batch throughput test for Qwen3.5-4B on P104-100*
`test_batch.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `load_model` |  |
| `run_batch_test` |  |
| `main` |  |

#### `bench_vlm_parallel.py` (162 строк)
*Benchmark: llama-server sequential vs parallel, same photo x10*
`bench_vlm_parallel.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `start_server` |  |
| `send_request` |  |
| `run_bench` |  |
| `main` |  |

#### `face_pipeline.py` (156 строк)
*face_pipeline.py - Process photos with faces_present=True using InsightFace (CPU).*
`face_pipeline.py`

**Зависит от:** `database`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `get_undetected_photos` | Get photos with faces_present=True that have no face records yet. |
| `process_photos` | Process photos: InsightFace detect + embed + save to DB. |
| `main` |  |

### `src` (7282 строк, 33 файлов, 52 endpoints)

| Файл | Строк | Endpoints | Публ.функций | Хелперов | Классы |
|------|-------|-----------|-------------|----------|--------|
| database.py | 1443 | 0 | 1 | 2 | DatabaseManager |
| main.py | 1352 | 52 | 54 | 13 | BfcacheFixMiddleware, BrowserErrorRedirectMiddleware, BodySizeLimitMiddleware |
| mqtt_client.py | 545 | 0 | 13 | 1 | GailrayMQTT, WorkerMQTT, ApiMQTT, _Temp |
| cluster_personas.py | 429 | 0 | 3 | 10 | — |
| system_helpers.py | 423 | 0 | 0 | 12 | — |
| thumbnails.py | 380 | 0 | 2 | 8 | ThumbnailGenerator |
| persona.py | 271 | 0 | 1 | 0 | Persona, FacePersonaMapping, PersonaManager |
| flir_parser.py | 231 | 0 | 4 | 5 | — |
| exif.py | 227 | 0 | 1 | 0 | CameraInfo, GPSInfo, ExifData, ExifExtractor |
| system_monitor.py | 212 | 0 | 2 | 9 | — |
| face_embeddings.py | 210 | 0 | 1 | 0 | FaceEmbedding, FaceEmbeddingGenerator |
| face_detection.py | 190 | 0 | 1 | 0 | FaceDetection, FaceDetector |
| process_photos.py | 185 | 0 | 1 | 1 | — |
| describe_photo.py | 142 | 0 | 1 | 0 | — |
| match_personas.py | 118 | 0 | 2 | 0 | — |
| config.py | 112 | 0 | 0 | 2 | — |
| scanner.py | 107 | 0 | 1 | 0 | PhotoFile, PhotoScanner |
| vlm_log.py | 100 | 0 | 1 | 1 | — |
| describe_photo_ollama.py | 85 | 0 | 2 | 0 | — |
| analyze_personas.py | 80 | 0 | 0 | 0 | — |
| video_metadata.py | 72 | 0 | 2 | 1 | — |
| test_retinaface_3.py | 67 | 0 | 3 | 0 | — |
| analyze_group_c.py | 42 | 0 | 0 | 0 | — |
| recreate_faces_table.py | 39 | 0 | 0 | 0 | — |
| clear_persona_ids.py | 33 | 0 | 0 | 0 | — |
| test_retinaface.py | 32 | 0 | 0 | 0 | — |
| test_search.py | 31 | 0 | 0 | 0 | — |
| check_clustering.py | 30 | 0 | 0 | 0 | — |
| clear_all_faces.py | 23 | 0 | 0 | 0 | — |
| list_photos.py | 23 | 0 | 0 | 0 | — |
| test_yolo.py | 23 | 0 | 0 | 0 | — |
| clear_2020_faces.py | 22 | 0 | 0 | 0 | — |
| __init__.py | 3 | 0 | 0 | 0 | — |

#### `database.py` (1443 строк)
*Database management: SQLite for structured data, LanceDB for vectors*
`src/database.py`

**Зависит от:** `config`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `get_db` |  |

**Внутренние хелперы:** 2 (_-функций)

**Класс `DatabaseManager`** (91 методов: 70 публичных, 21 внутренних)
| Метод | Описание |
|-------|----------|
| `add_photo` |  |
| `add_photos_batch` |  |
| `get_photo` |  |
| `get_photo_by_path` |  |
| `update_photo` |  |
| `delete_photo` |  |
| `count_photos` |  |
| `search_photos` |  |
| `get_all_photos` |  |
| `get_date_histogram` |  |
| `add_face` |  |
| `add_face_sqlite_only` |  |
| `add_face_vectors_batch` |  |
| `get_face` |  |
| `get_faces_for_photo` |  |
| `get_faces_for_persona` |  |
| `update_face_persona` |  |
| `get_face_embedding` |  |
| `get_all_face_embeddings` |  |
| `get_all_faces` |  |
| `count_faces` |  |
| `add_persona` |  |
| `get_persona` |  |
| `get_all_personas` |  |
| `update_persona` |  |
| `delete_persona` |  |
| `merge_personas` |  |
| `face_count_map` |  |
| `persona_face_id_map` |  |
| `get_display_names` |  |
| `get_personas_by_name` |  |
| `search_similar_faces` |  |
| `add_catalog_root` |  |
| `update_catalog_root` |  |
| `get_catalog_roots` |  |
| `get_catalog_root` |  |
| `delete_catalog_root` |  |
| `add_catalog_files_batch` |  |
| `get_catalog_files` |  |
| `count_catalog_files` |  |
| `update_catalog_file` |  |
| `update_catalog_file_by_path` |  |
| `delete_catalog_file` |  |
| `delete_catalog_files_by_root` |  |
| `get_catalog_file_by_path` |  |
| `add_photo_embedding` |  |
| `add_photo_embeddings_batch` |  |
| `delete_photo_embedding` |  |
| `dedup_photo_embeddings` | Remove duplicate photo_embeddings rows, keeping the last occ |
| `compact_photo_embeddings` | Compact LanceDB fragments to reclaim space from soft-deleted |
| `search_photo_embeddings` |  |
| `count_photo_embeddings` |  |
| `get_photo_embedding` |  |
| `invalidate_embeddings_for_photos` |  |
| `invalidate_embeddings_for_persona` |  |
| `invalidate_for_persona` |  |
| `get_status` |  |
| `mark_canonical_duplicates` | For each content_hash group with >1 file, mark one as canoni |
| `get_duplicate_paths` | Get all abs_paths for non-canonical files with the same cont |
| `is_path_canonical` | Check if a file path is the canonical representative for its |
| `invalidate_canonical_cache` | Invalidate the canonical cache after marking duplicates. |
| `get_canonical_status` | Get stats about canonical/duplicate files. |
| `get_edits` |  |
| `add_edit` |  |
| `remove_edit` |  |
| `clear_edits` |  |
| `get_setting` |  |
| `set_setting` |  |
| `insert_system_metric` |  |
| `get_system_metrics` |  |

#### `main.py` (1352 строк)
*FastAPI application for Gailery Photo Gallery*
`src/main.py`

**Зависит от:** `api`, `api.validators`, `config`, `database`, `mqtt_client`, `system_helpers`, `system_monitor`, `vlm_log`

**Endpoint'ы:**
| Method | Path | Handler |
|--------|------|---------|
| GET | `/` | root |
| GET | `/catalog` | catalog_page |
| GET | `/gallery` | gallery_page |
| GET | `/persons` | persons_page |
| GET | `/log` | log_page |
| GET | `/admin` | admin_page |
| GET | `/map` | map_page |
| GET | `/api/log` | get_log |
| GET | `/health` | health |
| GET | `/api/status` | get_status |
| GET | `/api/monitoring` | get_monitoring |
| GET | `/api/system-report` | get_system_report |
| GET | `/api/mqtt/workers` | mqtt_workers |
| GET | `/api/watchdog/crashes` | watchdog_crashes |
| POST | `/api/watchdog/sleep` | watchdog_sleep |
| POST | `/api/watchdog/wake` | watchdog_wake |
| GET | `/api/services` | get_services |
| POST | `/api/services/{name}/restart` | restart_service |
| GET | `/api/proxy/ollama_check` | ollama_check |
| GET | `/api/proxy/ollama_models` | ollama_models |
| POST | `/api/control/start` | control_start |
| POST | `/api/control/stop` | control_stop |
| POST | `/api/control/reset` | control_reset |
| POST | `/api/control/update` | control_update |
| GET | `/api/changes` | get_changes |
| GET | `/api/settings/{key}` | get_setting |
| PUT | `/api/settings/{key}` | set_setting |
| GET | `/api/settings/{key}/top_personas` | top_personas_for_facts |
| GET | `/logo-dark.png` | logo_dark |
| GET | `/logo-light.png` | logo_light |
| GET | `/favicon.ico` | favicon |
| GET | `/favicon.png` | favicon_png |
| GET | `/apple-touch-icon.png` | apple_touch_icon |
| GET | `/favicon-32.png` | favicon_32 |
| GET | `/shared.css` | shared_css |
| GET | `/shared.js` | shared_js |
| GET | `/viewer.css` | viewer_css |
| GET | `/viewer.js` | viewer_js |
| GET | `/face-modal.css` | face_modal_css |
| GET | `/face-modal.js` | face_modal_js |
| GET | `/gallery.js` | gallery_js |
| GET | `/gallery-detail.js` | gallery_detail_js |
| GET | `/gallery-ui.js` | gallery_ui_js |
| GET | `/api/backup/download` | backup_download |
| POST | `/api/backup/upload` | backup_upload |
| GET | `/api/maintenance/stats` | maintenance_stats |
| POST | `/api/maintenance/vacuum` | maintenance_vacuum |
| POST | `/api/maintenance/dedup_embeddings` | maintenance_dedup_embeddings |
| GET | `/api/config` | get_config |
| POST | `/api/config/update` | config_update |
| GET | `/api/ai-log` | ai_log |
| GET | `/{path:path}` | spa_fallback |

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| async `lifespan` |  |
| async `root` |  |
| async `catalog_page` |  |
| async `gallery_page` |  |
| async `persons_page` |  |
| async `log_page` |  |
| async `admin_page` |  |
| async `map_page` |  |
| async `get_log` |  |
| async `health` |  |
| async `get_status` |  |
| async `get_monitoring` |  |
| async `get_system_report` |  |
| async `mqtt_workers` |  |
| async `watchdog_crashes` |  |
| async `watchdog_sleep` |  |
| async `watchdog_wake` |  |
| async `get_services` |  |
| async `restart_service` |  |
| async `ollama_check` |  |
| async `ollama_models` |  |
| async `control_start` |  |
| async `control_stop` |  |
| async `control_reset` |  |
| async `control_update` |  |
| async `get_changes` |  |
| async `get_setting` |  |
| async `set_setting` |  |
| async `top_personas_for_facts` |  |
| async `logo_dark` |  |
| async `logo_light` |  |
| async `favicon` |  |
| async `favicon_png` |  |
| async `apple_touch_icon` |  |
| async `favicon_32` |  |
| async `shared_css` |  |
| async `shared_js` |  |
| async `viewer_css` |  |
| async `viewer_js` |  |
| async `face_modal_css` |  |
| async `face_modal_js` |  |
| async `gallery_js` |  |
| async `gallery_detail_js` |  |
| async `gallery_ui_js` |  |
| async `backup_download` |  |
| async `backup_upload` |  |
| async `maintenance_stats` |  |
| async `maintenance_vacuum` |  |
| async `maintenance_dedup_embeddings` |  |
| async `get_config` |  |
| async `config_update` |  |
| async `ai_log` |  |
| async `spa_fallback` |  |
| `main` |  |

**Внутренние хелперы:** 13 (_-функций)

**Класс `BfcacheFixMiddleware`** (2 методов: 0 публичных, 2 внутренних)

**Класс `BrowserErrorRedirectMiddleware`** (2 методов: 0 публичных, 2 внутренних)

**Класс `BodySizeLimitMiddleware`** (2 методов: 0 публичных, 2 внутренних)
*Лимит размера HTTP тела (манифест §6.15).*

#### `mqtt_client.py` (545 строк)
*mqtt_client.py - Shared MQTT client for Gailray pipeline workers and API.*
`src/mqtt_client.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `worker_status_topic` |  |
| `worker_progress_topic` |  |
| `worker_pid_topic` |  |
| `worker_gpu_held_topic` |  |
| `gpu_lock_topic` |  |
| `control_start_topic` |  |
| `control_stop_topic` |  |
| `control_pause_topic` |  |
| `control_resume_topic` |  |
| `watchdog_mode_topic` |  |
| `db_result_topic` |  |
| `create_worker_mqtt` |  |
| `create_api_mqtt` |  |

**Внутренние хелперы:** 1 (_-функций)

**Класс `GailrayMQTT`** (8 методов: 5 публичных, 3 внутренних)
| Метод | Описание |
|-------|----------|
| `connect` |  |
| `disconnect` |  |
| `publish` |  |
| `subscribe` |  |
| `clear_topic` |  |

**Класс `WorkerMQTT`** (16 методов: 11 публичных, 5 внутренних)
| Метод | Описание |
|-------|----------|
| `connect` |  |
| `stopped` |  |
| `paused` |  |
| `wait_while_paused` |  |
| `publish_status` |  |
| `publish_progress` |  |
| `publish_pid` |  |
| `publish_gpu_held` |  |
| `acquire_gpu` |  |
| `release_gpu` |  |
| `shutdown` |  |

**Класс `ApiMQTT`** (20 методов: 15 публичных, 5 внутренних)
| Метод | Описание |
|-------|----------|
| `connect` |  |
| `is_db_writing` |  |
| `get_watchdog_mode` |  |
| `get_worker_states` |  |
| `is_worker_alive` |  |
| `get_current_step` |  |
| `get_gpu_holder` |  |
| `send_start` |  |
| `send_stop` |  |
| `send_pause` |  |
| `send_resume` |  |
| `request_gpu_for_api` |  |
| `request_gpu_gentle` |  |
| `release_gpu_from_api` |  |
| `db_write` |  |

**Класс `_Temp`** (0 методов: 0 публичных, 0 внутренних)

#### `cluster_personas.py` (429 строк)
*cluster_personas.py - Incremental face clustering into personas.*
`src/cluster_personas.py`

**Зависит от:** `config`, `database`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `compute_centroids` |  |
| `next_persona_id` |  |
| `cluster_faces` |  |

**Внутренние хелперы:** 10 (_-функций)

#### `system_helpers.py` (423 строк)
`src/system_helpers.py`

**Зависит от:** `config`, `database`

**Внутренние хелперы:** 12 (_-функций)

#### `thumbnails.py` (380 строк)
*Thumbnail generation for photos using pyvips, Pillow fallback for RAW, ffmpeg for video*
`src/thumbnails.py`

**Зависит от:** `config`, `database`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `generate_batch` |  |
| `main` |  |

**Внутренние хелперы:** 8 (_-функций)

**Класс `ThumbnailGenerator`** (8 методов: 6 публичных, 2 внутренних)
*Generate thumbnails using pyvips (libvips)*
| Метод | Описание |
|-------|----------|
| `generate` |  |
| `generate_to_buffer` |  |
| `generate_fit_buffer` |  |
| `exists` |  |
| `get_thumbnail_path` |  |
| `needs_regeneration` |  |

#### `persona.py` (271 строк)
*Persona management system for face identification*
`src/persona.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `main` | Main function for testing |

**Класс `Persona`** (1 методов: 1 публичных, 0 внутренних)
*Represents a person entity*
| Метод | Описание |
|-------|----------|
| `to_dict` | Convert to dictionary for serialization |

**Класс `FacePersonaMapping`** (1 методов: 1 публичных, 0 внутренних)
*Mapping between face and persona*
| Метод | Описание |
|-------|----------|
| `to_dict` | Convert to dictionary for serialization |

**Класс `PersonaManager`** (10 методов: 9 публичных, 1 внутренних)
*Manage personas and face-to-persona mappings*
| Метод | Описание |
|-------|----------|
| `create_persona` | Create a new persona with automatic numbering |
| `assign_face_to_persona` | Assign a face to a persona |
| `get_persona_for_face` | Get persona for a face |
| `get_persona` | Get persona by ID |
| `get_all_personas` | Get all personas |
| `update_persona_display_name` | Update display name for persona |
| `merge_personas` | Merge two personas (combine all faces from source into targe |
| `delete_persona` | Delete a persona |
| `suggest_persona_for_face` | Suggest existing persona for a new face based on embedding s |

#### `flir_parser.py` (231 строк)
*FLIR thermal image parser.*
`src/flir_parser.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `is_flir_file` |  |
| `parse_flir` |  |
| `parse_alignment` | Parse FLIR EXIF for orientation and alignment data. |
| `create_overlay` |  |

**Внутренние хелперы:** 5 (_-функций)

#### `exif.py` (227 строк)
*EXIF metadata extraction from photos*
`src/exif.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `main` | Main function for testing |

**Класс `CameraInfo`** (1 методов: 1 публичных, 0 внутренних)
*Camera information from EXIF*
| Метод | Описание |
|-------|----------|
| `to_dict` |  |

**Класс `GPSInfo`** (1 методов: 1 публичных, 0 внутренних)
*GPS coordinates from EXIF*
| Метод | Описание |
|-------|----------|
| `to_dict` |  |

**Класс `ExifData`** (1 методов: 1 публичных, 0 внутренних)
*Complete EXIF data*
| Метод | Описание |
|-------|----------|
| `to_dict` |  |

**Класс `ExifExtractor`** (5 методов: 1 публичных, 4 внутренних)
*EXIF metadata extractor*
| Метод | Описание |
|-------|----------|
| `extract` | Extract EXIF data from image |

#### `system_monitor.py` (212 строк)
*system_monitor.py — сбор системных метрик раз в 60 секунд.*
`src/system_monitor.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `collect_metrics` |  |
| `collect_live` |  |

**Внутренние хелперы:** 9 (_-функций)

#### `face_embeddings.py` (210 строк)
*Face embedding generation for face recognition*
`src/face_embeddings.py`

**Зависит от:** `config`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `main` | Main function for testing |

**Класс `FaceEmbedding`** (1 методов: 1 публичных, 0 внутренних)
*Represents a face embedding vector*
| Метод | Описание |
|-------|----------|
| `to_dict` | Convert to dictionary for serialization |

**Класс `FaceEmbeddingGenerator`** (8 методов: 2 публичных, 6 внутренних)
*Generate face embeddings using InsightFace*
| Метод | Описание |
|-------|----------|
| `generate` | Generate embedding for face in image |
| `generate_batch` | Generate embeddings for multiple faces |

#### `face_detection.py` (190 строк)
*Face detection using RetinaFace and YOLO26-face*
`src/face_detection.py`

**Зависит от:** `config`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `main` | Main function for testing |

**Класс `FaceDetection`** (1 методов: 1 публичных, 0 внутренних)
*Represents a detected face*
| Метод | Описание |
|-------|----------|
| `to_dict` | Convert to dictionary for serialization |

**Класс `FaceDetector`** (8 методов: 2 публичных, 6 внутренних)
*Face detector using RetinaFace or YOLO26*
| Метод | Описание |
|-------|----------|
| `detect` | Detect faces in image |
| `detect_to_dict` | Detect faces and return as list of dictionaries |

#### `process_photos.py` (185 строк)
*Process photos in a directory:*
`src/process_photos.py`

**Зависит от:** `database`, `face_detection`, `face_embeddings`, `scanner`, `thumbnails`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `process_directory` | Process directory, isolating each photo in a separate Python process. |

**Внутренние хелперы:** 1 (_-функций)

#### `describe_photo.py` (142 строк)
*Generate detailed description for a single photo using Florence-2-large*
`src/describe_photo.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `describe_photo` | Generate detailed description for photo |

#### `match_personas.py` (118 строк)
*Incremental persona matching using cosine similarity.*
`src/match_personas.py`

**Зависит от:** `database`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `cosine_similarity` | Calculate cosine similarity between two vectors |
| `match_personas` | Match faces to personas using incremental re-identification |

#### `config.py` (112 строк)
*Configuration for Gailery Photo Gallery*
`src/config.py`

**Зависит от:** `database`

**Внутренние хелперы:** 2 (_-функций)

#### `scanner.py` (107 строк)
*File scanner for photo directory*
`src/scanner.py`

**Зависит от:** `config`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `main` | Main function for testing |

**Класс `PhotoFile`** (1 методов: 1 публичных, 0 внутренних)
*Represents a photo file with metadata*
| Метод | Описание |
|-------|----------|
| `to_dict` | Convert to dictionary for serialization |

**Класс `PhotoScanner`** (3 методов: 2 публичных, 1 внутренних)
*Scanner for photo files in share directory*
| Метод | Описание |
|-------|----------|
| `scan` | Scan directory recursively for photo files |
| `scan_to_dict` | Scan and return results as list of dictionaries |

#### `vlm_log.py` (100 строк)
*vlm_log.py — логирование всех AI-вызовов в отдельную SQLite базу.*
`src/vlm_log.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `log_ai_call` | Записать AI-вызов в лог. Никогда не падает. |

**Внутренние хелперы:** 1 (_-функций)

#### `describe_photo_ollama.py` (85 строк)
*Generate detailed description for a single photo using Ollama API*
`src/describe_photo_ollama.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `encode_image` | Encode image to base64 |
| `describe_photo` | Generate detailed description for photo using Ollama |

#### `analyze_personas.py` (80 строк)
*Analyze faces using DBSCAN clustering to find unique personas*
`src/analyze_personas.py`

**Зависит от:** `config`

#### `video_metadata.py` (72 строк)
*video_metadata.py — извлечение метаданных видео через ffprobe.*
`src/video_metadata.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `extract_metadata` |  |
| `extract_video_date` |  |

**Внутренние хелперы:** 1 (_-функций)

#### `test_retinaface_3.py` (67 строк)
*Run RetinaFace test on 3 photos sequentially (isolated per photo process).*
`src/test_retinaface_3.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `pick_first_images` |  |
| `run_one` |  |
| `main` |  |

#### `analyze_group_c.py` (42 строк)
*Analyze specific group of faces*
`src/analyze_group_c.py`

**Зависит от:** `config`

#### `recreate_faces_table.py` (39 строк)
*Recreate faces table with vector index*
`src/recreate_faces_table.py`

**Зависит от:** `config`

#### `clear_persona_ids.py` (33 строк)
*Clear persona_id from all faces*
`src/clear_persona_ids.py`

**Зависит от:** `config`

#### `test_retinaface.py` (32 строк)
*Test RetinaFace face detection*
`src/test_retinaface.py`

**Зависит от:** `face_detection`

#### `test_search.py` (31 строк)
*Test LanceDB vector search*
`src/test_search.py`

**Зависит от:** `config`

#### `check_clustering.py` (30 строк)
*Check clustering results*
`src/check_clustering.py`

**Зависит от:** `config`

#### `clear_all_faces.py` (23 строк)
*Clear all faces and personas from database*
`src/clear_all_faces.py`

**Зависит от:** `config`

#### `list_photos.py` (23 строк)
*List all photos with faces*
`src/list_photos.py`

**Зависит от:** `config`

#### `test_yolo.py` (23 строк)
*Test YOLO face detection*
`src/test_yolo.py`

**Зависит от:** `face_detection`

#### `clear_2020_faces.py` (22 строк)
*Clear all faces from 2020 directory*
`src/clear_2020_faces.py`

**Зависит от:** `config`

### `src/api` (3621 строк, 9 файлов, 65 endpoints)

| Файл | Строк | Endpoints | Публ.функций | Хелперов | Классы |
|------|-------|-----------|-------------|----------|--------|
| photos.py | 1535 | 26 | 26 | 24 | — |
| catalog.py | 551 | 15 | 15 | 6 | AddRootRequest |
| persons.py | 369 | 10 | 10 | 3 | FaceSearchRequest, PersonaUpdateRequest |
| video.py | 337 | 2 | 2 | 13 | — |
| models.py | 282 | 4 | 5 | 3 | — |
| flir.py | 233 | 7 | 7 | 2 | — |
| search.py | 226 | 1 | 1 | 9 | — |
| validators.py | 86 | 0 | 4 | 0 | — |
| __init__.py | 2 | 0 | 0 | 0 | — |

#### `photos.py` (1535 строк)
*API endpoints for photos*
`src/api/photos.py`

**Зависит от:** `config`, `database`, `main`, `mqtt_client`, `thumbnails`

**Endpoint'ы:**
| Method | Path | Handler |
|--------|------|---------|
| GET | `/` | get_photo |
| GET | `/thumbnail` | get_thumbnail |
| GET | `/face/{face_id}` | get_face_crop |
| GET | `/face_context/{face_id}` | get_face_context |
| GET | `/list` | list_photos |
| GET | `/monitor_feed` | monitor_feed |
| GET | `/description` | get_description |
| GET | `/search` | search_photos |
| POST | `/{photo_id}/enrich` | enrich_description |
| GET | `/reprocess-log` | reprocess_log |
| GET | `/{photo_id}/reprocess` | reprocess_photo |
| PUT | `/{photo_id}/rich_description` | save_rich_description |
| GET | `/dates` | get_date_histogram |
| POST | `/describe` | describe_photos |
| GET | `/map` | get_map_photos |
| GET | `/neighbor` | get_neighbor |
| POST | `/reverse_geocode` | reverse_geocode |
| POST | `/set_gps` | set_gps |
| POST | `/set_date` | set_date |
| POST | `/clear_date` | clear_date |
| POST | `/clear_gps` | clear_gps |
| POST | `/mark_deleted` | mark_deleted |
| POST | `/undelete` | undelete |
| GET | `/edits/{content_hash}` | get_edits |
| POST | `/edits/{content_hash}` | save_edit |
| DELETE | `/edits/{edit_id}` | delete_edit |

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| async `get_photo` |  |
| async `get_thumbnail` |  |
| async `get_face_crop` |  |
| async `get_face_context` |  |
| async `list_photos` |  |
| async `monitor_feed` |  |
| async `get_description` |  |
| async `search_photos` |  |
| async `enrich_description` |  |
| `reprocess_log` |  |
| `reprocess_photo` |  |
| async `save_rich_description` |  |
| async `get_date_histogram` |  |
| async `describe_photos` |  |
| async `get_map_photos` |  |
| async `get_neighbor` |  |
| async `reverse_geocode` |  |
| async `set_gps` |  |
| async `set_date` |  |
| async `clear_date` |  |
| async `clear_gps` |  |
| async `mark_deleted` |  |
| async `undelete` |  |
| async `get_edits` |  |
| async `save_edit` |  |
| async `delete_edit` |  |

**Внутренние хелперы:** 24 (_-функций)

#### `catalog.py` (551 строк)
*API endpoints for file catalog management*
`src/api/catalog.py`

**Зависит от:** `config`, `database`, `mqtt_client`

**Endpoint'ы:**
| Method | Path | Handler |
|--------|------|---------|
| GET | `/roots` | get_roots |
| POST | `/add_root` | add_root |
| POST | `/scan/{root_id}` | scan_root |
| GET | `/stats` | catalog_stats |
| GET | `/tree` | get_tree |
| POST | `/sync` | sync_flags |
| DELETE | `/root/{root_id}` | delete_root |
| POST | `/root/{root_id}/toggle` | toggle_root |
| GET | `/locate` | locate_photo |
| GET | `/browse` | browse_dirs |
| GET | `/hash_status` | hash_status |
| POST | `/hash_backfill` | hash_backfill |
| GET | `/duplicates` | find_duplicates |
| POST | `/hash_backfill_stop` | hash_backfill_stop |
| GET | `/hash_backfill_status` | hash_backfill_status |

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| async `get_roots` |  |
| async `add_root` |  |
| async `scan_root` |  |
| async `catalog_stats` |  |
| async `get_tree` |  |
| async `sync_flags` |  |
| async `delete_root` |  |
| async `toggle_root` |  |
| async `locate_photo` |  |
| async `browse_dirs` |  |
| async `hash_status` |  |
| async `hash_backfill` |  |
| async `find_duplicates` |  |
| async `hash_backfill_stop` |  |
| async `hash_backfill_status` |  |

**Внутренние хелперы:** 6 (_-функций)

**Класс `AddRootRequest`** (0 методов: 0 публичных, 0 внутренних)

#### `persons.py` (369 строк)
*API endpoints for persons*
`src/api/persons.py`

**Зависит от:** `database`, `mqtt_client`

**Endpoint'ы:**
| Method | Path | Handler |
|--------|------|---------|
| GET | `/` | get_all_persons |
| GET | `/names` | get_display_names |
| GET | `/by_name/{display_name}` | get_persons_by_name |
| GET | `/{persona_id}` | get_person |
| GET | `/{persona_id}/faces` | get_person_faces |
| PUT | `/{persona_id}` | update_person |
| PUT | `/batch/by_name` | update_persons_by_name |
| POST | `/merge` | merge_persons |
| DELETE | `/{persona_id}` | delete_person |
| POST | `/search` | search_similar_faces |

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| async `get_all_persons` |  |
| async `get_display_names` |  |
| async `get_persons_by_name` |  |
| async `get_person` |  |
| async `get_person_faces` |  |
| async `update_person` |  |
| async `update_persons_by_name` |  |
| async `merge_persons` |  |
| async `delete_person` |  |
| async `search_similar_faces` |  |

**Внутренние хелперы:** 3 (_-функций)

**Класс `FaceSearchRequest`** (0 методов: 0 публичных, 0 внутренних)

**Класс `PersonaUpdateRequest`** (0 методов: 0 публичных, 0 внутренних)

#### `video.py` (337 строк)
*API endpoints for video streaming*
`src/api/video.py`

**Зависит от:** `config`, `database`

**Endpoint'ы:**
| Method | Path | Handler |
|--------|------|---------|
| GET | `/video_stream` | video_stream |
| GET | `/video_meta` | video_meta |

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| async `video_stream` |  |
| async `video_meta` |  |

**Внутренние хелперы:** 13 (_-функций)

#### `models.py` (282 строк)
*API endpoints for model management*
`src/api/models.py`

**Зависит от:** `api.validators`, `config`, `database`, `mqtt_client`

**Endpoint'ы:**
| Method | Path | Handler |
|--------|------|---------|
| POST | `/download/{model_id}` | download_model |
| GET | `/dir` | get_models_dir |
| PUT | `/dir` | set_models_dir |
| GET | `/check/{model_id}` | check_model |

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| async `list_models` |  |
| async `download_model` |  |
| async `get_models_dir` |  |
| async `set_models_dir` |  |
| async `check_model` |  |

**Внутренние хелперы:** 3 (_-функций)

#### `flir.py` (233 строк)
*FLIR thermal image API endpoints*
`src/api/flir.py`

**Зависит от:** `config`, `database`, `flir_parser`

**Endpoint'ы:**
| Method | Path | Handler |
|--------|------|---------|
| GET | `/flir_visual` | get_flir_visual |
| GET | `/flir_thermal` | get_flir_thermal |
| GET | `/flir_thermal_src` | get_flir_thermal_src |
| GET | `/flir_temperature` | get_flir_temperature |
| GET | `/flir_raw_palette` | get_flir_raw_palette |
| GET | `/flir_overlay` | get_flir_overlay |
| GET | `/flir_info` | get_flir_info |

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| async `get_flir_visual` |  |
| async `get_flir_thermal` |  |
| async `get_flir_thermal_src` |  |
| async `get_flir_temperature` | Temperature at a given pixel in the RawThermalImage. |
| async `get_flir_raw_palette` | Render RawThermalImage with byte-swap + Planck + camera palette. |
| async `get_flir_overlay` |  |
| async `get_flir_info` |  |

**Внутренние хелперы:** 2 (_-функций)

#### `search.py` (226 строк)
*API endpoints for semantic search*
`src/api/search.py`

**Зависит от:** `config`, `database`, `main`

**Endpoint'ы:**
| Method | Path | Handler |
|--------|------|---------|
| GET | `/semantic_search` | semantic_search |

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| async `semantic_search` |  |

**Внутренние хелперы:** 9 (_-функций)

#### `validators.py` (86 строк)
*validators.py — хелперы валидации ввода на сетевой границе.*
`src/api/validators.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| async `json_body` | Безопасно парсит JSON тело запроса как dict. |
| `int_param` | Безопасно парсит query-параметр как int. |
| `float_param` | Безопасно парсит query-параметр как float. |
| `str_param` | Безопасно парсит query-параметр как str (с защитой от не-str). |

### `tests` (6644 строк, 15 файлов, 0 endpoints)

| Файл | Строк | Endpoints | Публ.функций | Хелперов | Классы |
|------|-------|-----------|-------------|----------|--------|
| test_api.py | 1145 | 0 | 0 | 0 | TestPhotosSearchAPI, TestPhotosDateGPSAPI, TestPhotosDeleteAPI, TestPersonsAPI, TestCatalogAPI, TestMapAPI, TestPipelineControlAPI, TestSystemAPI, TestSystemReportAPI, TestCatalogTreeAPI, TestPersonsExtendedAPI, TestSemanticSearchAPI, TestVideoAPI, TestFlirAPI, TestPhotosExtendedAPI, TestPhotosWithDataAPI, TestSettingsAPI, TestConfigAPI, TestBackupAPI, TestProxyAPI, TestAdminAPI, TestServicesAPI, TestMqttWorkersAPI, TestControlExtendedAPI, TestFixOllamaUrl, TestSpaFallback, TestMaintenanceExtendedAPI |
| test_code_quality.py | 963 | 0 | 27 | 15 | — |
| test_user_flows.py | 728 | 0 | 1 | 9 | TestBrowseGallery, TestViewPhotoDetail, TestSearchWithFilters, TestPersonManagement, TestPhotoOperations, TestMapView, TestCatalogPage, TestConfigAndControl, TestPageNavigation, TestEnrichDescription, TestSemanticSearch, TestReverseGeocode, TestBackup, TestSettings |
| test_database.py | 645 | 0 | 0 | 0 | TestDatabaseInit, TestPhotoCRUD, TestPhotoSearch, TestDateHistogram, TestPhotoUpdate, TestFaceCRUD, TestPersonaCRUD, TestCatalogCRUD, TestCatalogExtended, TestEditsCRUD, TestSettings, TestSystemMetrics, TestCanonicalDuplicates, TestGetStatus, TestInvalidateForPersona, TestFaceExtended, TestCosineSimilarity |
| test_performance.py | 531 | 0 | 2 | 1 | TestDatabasePerformance, TestAPIPerformance, TestDatabaseIndexCoverage, TestAntipatternDetection, TestScaleBaseline |
| test_mqtt_unit.py | 471 | 0 | 0 | 0 | TestTopicFunctions, TestPublish, TestWorkerMQTT, TestApiMQTT, TestConstants |
| test_environment.py | 410 | 0 | 22 | 3 | — |
| test_gallery_ui.py | 351 | 0 | 1 | 1 | TestGallerySearchPage, TestGalleryDatesPage, TestGalleryStatusPage, TestGalleryMapPage, TestGalleryNeighbor, TestGalleryPhotoCRUD, TestGalleryPersonPage, TestGalleryCatalogPage |
| test_pipeline_control.py | 348 | 0 | 0 | 0 | TestApiStatus, TestControlStart, TestControlStop, TestGPUArbitrationViaMQTT, TestWatchdogMode, TestControlButtonStates, TestConfigAPI, TestOllamaEmbedAI |
| test_security.py | 299 | 0 | 7 | 2 | — |
| conftest.py | 253 | 0 | 5 | 4 | — |
| test_system_helpers.py | 226 | 0 | 0 | 0 | TestDeterminePipelineStep, TestGetGitInfo, TestReadLogInfo, TestCollectDisks, TestCollectGpuProcesses, TestCollectTopProcs, TestCollectPipelineStats |
| test_mqtt.py | 180 | 0 | 0 | 0 | TestMQTTWorkerLifecycle, TestMQTTApiStatus, TestMQTTGPUArbitration, TestMQTTFlagFallback |
| test_middleware.py | 93 | 0 | 0 | 0 | TestBfcacheFixMiddleware, TestBrowserErrorRedirect, TestSpaFallback, TestPageRoutes |
| __init__.py | 1 | 0 | 0 | 0 | — |

#### `test_api.py` (1145 строк)
`tests/test_api.py`

**Зависит от:** `main`

**Класс `TestPhotosSearchAPI`** (9 методов: 9 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_search_returns_results` | Эндпоинт поиска фото возвращает 200 и содержит ключи total+p |
| `test_search_with_query` | Поиск с текстовым запросом не падает. |
| `test_search_with_faces_filter` | Фильтр has_faces=true не ломает поиск. |
| `test_search_with_gps_filter` | Фильтр has_gps=true не ломает поиск. |
| `test_dates_histogram` | Гистограмма дат возвращает структуру с годами и общим количе |
| `test_photo_list` | Эндпоинт списка фото возвращает photos с заполненными path/p |
| `test_photo_list_sort_changed_desc` | /api/photos/list с sort=changed_desc не падает и возвращает  |
| `test_search_person_filter` | Фильтр по персоне обрабатывается без краша (может быть 200 и |
| `test_search_deleted_filter` | Фильтр удалённых фото не ломает поиск. |

**Класс `TestPhotosDateGPSAPI`** (7 методов: 7 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_set_date` | Установка даты на несуществующее фото возвращает 404. |
| `test_clear_date` | Сброс даты на несуществующем фото возвращает 404. |
| `test_set_gps` | Установка GPS на несуществующее фото возвращает 404. |
| `test_clear_gps` | Сброс GPS на несуществующем фото возвращает 404. |
| `test_clear_date` |  |
| `test_set_gps` |  |
| `test_clear_gps` |  |

**Класс `TestPhotosDeleteAPI`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_mark_deleted` | Пометка несуществующего фото как удалённого возвращает 404. |
| `test_undelete` | Восстановление несуществующего фото возвращает 404. |

**Класс `TestPersonsAPI`** (5 методов: 5 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_list_persons` | Список персон возвращает пагинированный ответ с полями perso |
| `test_list_persons_has_comment` | Каждая персона в списке содержит поле comment. |
| `test_get_names` | Эндпоинт имён персон доступен. |
| `test_update_persona` | Обновление несуществующей персоны не крашит сервер. |
| `test_update_persona_with_comment` | Персоне можно задать comment через PUT. |

**Класс `TestCatalogAPI`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_get_roots` | Корни каталога возвращаются без ошибок. |
| `test_get_stats` | Статистика каталога доступна. |
| `test_locate` | Локация несуществующего пути не падает. |

**Класс `TestMapAPI`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_map_photos_endpoint` | /api/photos/map возвращает список с lat/lon. |
| `test_map_page_loads` | Страница карты загружается. |

**Класс `TestPipelineControlAPI`** (3 методов: 3 публичных, 0 внутренних)
*Деструктивные тесты — вызывают реальные systemctl/pkill/MQTT stop.*
| Метод | Описание |
|-------|----------|
| `test_control_stop` | Остановка пайплайна — mock os.system + MQTT, проверяем тольк |
| `test_control_start_faces_has_limit` | Запуск faces — mock os.system + MQTT, проверяем только HTTP  |
| `test_control_start_describe_has_params` | Запуск describe — mock os.system + MQTT, проверяем только HT |

**Класс `TestSystemAPI`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_health` | Health-check эндпоинт возвращает status: ok. |
| `test_log` | Чтение логов через API не падает. |
| `test_changes` | История изменений возвращается с полем changes. |

**Класс `TestSystemReportAPI`** (17 методов: 17 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_system_report` | System report возвращает host/gpu/memory/pipeline. |
| `test_monitoring` | Monitoring возвращает live + history. |
| `test_maintenance_stats` | Maintenance stats возвращает структуру с метриками БД. |
| `test_ai_log` | AI log endpoint возвращает список. |
| `test_config_update_env_key` | Config update с env_key изменяет настройку. |
| `test_control_reset` | Control reset сбрасывает флаги шага. |
| `test_control_start_embed` | Запуск embed — mock os.system, проверяем HTTP 200. |
| `test_control_start_exif` | Запуск exif — mock os.system, проверяем HTTP 200. |
| `test_control_start_ingest` | Запуск ingest — mock os.system, проверяем HTTP 200. |
| `test_backup_download` | Backup download возвращает gzip (нужна реальная БД). |
| `test_maintenance_vacuum` | Maintenance vacuum выполняется (нужна реальная БД). |
| `test_maintenance_dedup_embeddings` | Maintenance dedup embeddings выполняется. |
| `test_top_personas_for_facts` | Top personas for facts возвращает список. |
| `test_watchdog_crashes` | Watchdog crashes endpoint возвращает структуру. |
| `test_watchdog_sleep_wake` | Watchdog sleep + wake работают. |
| `test_static_files` | Статические файлы отдаются. |
| `test_ollama_check` | Ollama check endpoint не падает. |

**Класс `TestCatalogTreeAPI`** (15 методов: 15 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_tree_empty` | Tree без root_id возвращает пустую структуру. |
| `test_tree_with_root` | Tree с root_id возвращает файлы из тестового root. |
| `test_tree_with_path_filter` | Tree с фильтром пути возвращает поддиректории. |
| `test_browse_dirs` | Browse dirs возвращает директории корня. |
| `test_browse_nonexistent` | Browse несуществующего пути fallback на /. |
| `test_hash_status` | Hash status возвращает структуру с счётчиками. |
| `test_duplicates_empty` | Duplicates на пустой БД возвращает пустой список. |
| `test_hash_backfill_status` | Hash backfill status возвращает running флаг. |
| `test_hash_backfill_stop` | Hash backfill stop выполняется без ошибок. |
| `test_add_root_nonexistent` | Add root с несуществующим путём возвращает ошибку или ok. |
| `test_toggle_root_nonexistent` | Toggle несуществующего root возвращает 404. |
| `test_delete_root_nonexistent` | Delete несуществующего root возвращает 500 (ошибка БД). |
| `test_scan_root` | Scan root запускается (mock os.system). |
| `test_sync` | Sync запускается (mock os.system). |
| `test_locate_with_data` | Locate для существующего пути находит root. |

**Класс `TestPersonsExtendedAPI`** (10 методов: 10 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_get_person_not_found` | GET персона по несуществующему ID возвращает 404. |
| `test_get_person_faces_not_found` | Лица несуществующей персоны — пустой список или 500. |
| `test_get_persons_by_name_empty` | Поиск по несуществующему имени возвращает пустой список. |
| `test_merge_persons_nonexistent` | Merge несуществующих персон возвращает 400. |
| `test_delete_person_not_found` | Delete несуществующей персоны возвращает 404. |
| `test_persons_named_only` | Фильтр named_only возвращает только именованные персоны. |
| `test_persons_pagination` | Пагинация персон limit/offset работает. |
| `test_get_person_with_data` | GET существующей персоны возвращает данные. |
| `test_get_person_faces_with_data` | Лица существующей персоны возвращаются. |
| `test_batch_update_nonexistent_name` | Batch update по несуществующему имени обновляет 0 персон. |

**Класс `TestSemanticSearchAPI`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_semantic_search_empty_query` | Пустой запрос возвращает пустой результат. |
| `test_semantic_search_no_query` | Без параметра q возвращает пустой результат. |

**Класс `TestVideoAPI`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_video_stream_not_found` | Video stream для несуществующего файла возвращает 404. |
| `test_video_meta_not_found` | Video meta для несуществующего файла возвращает 404. |

**Класс `TestFlirAPI`** (6 методов: 6 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_flir_info_not_found` | FLIR info для несуществующего фото возвращает 404. |
| `test_flir_visual_not_found` | FLIR visual для несуществующего фото возвращает 404. |
| `test_flir_thermal_not_found` | FLIR thermal для несуществующего фото возвращает 404. |
| `test_flir_temperature_not_found` | FLIR temperature для несуществующего фото возвращает 404. |
| `test_flir_raw_palette_not_found` | FLIR raw palette для несуществующего фото возвращает 404. |
| `test_flir_overlay_not_found` | FLIR overlay для несуществующего фото возвращает 404. |

**Класс `TestPhotosExtendedAPI`** (12 методов: 12 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_photos_root` | Корневой эндпоинт /api/photos/ требует параметр path. |
| `test_thumbnail_not_found` | Thumbnail для несуществующего фото возвращает 404 или fallba |
| `test_face_not_found` | Face по несуществующему ID возвращает 404. |
| `test_face_context_not_found` | Face context по несуществующему ID возвращает 404. |
| `test_description_not_found` | Description для несуществующего пути возвращает null. |
| `test_reprocess_log` | Reprocess log возвращает структуру с логом. |
| `test_neighbor_not_found` | Neighbor для несуществующей даты возвращает 404 или пусто. |
| `test_edits_not_found` | Edits для несуществующего content_hash возвращают пустой спи |
| `test_rich_description_not_found` | PUT rich_description для несуществующего фото возвращает 404 |
| `test_monitor_feed` | Monitor feed endpoint доступен. |
| `test_reverse_geocode` | Reverse geocode возвращает результат (может быть ошибка). |
| `test_describe_endpoint` | Describe endpoint с несуществующими путями возвращает 400. |

**Класс `TestPhotosWithDataAPI`** (9 методов: 9 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_thumbnail_with_data` | Thumbnail для существующего фото (файла нет на диске) — 404. |
| `test_description_with_data` | Description для существующего фото возвращает текст. |
| `test_edits_with_hash` | Edits для существующего content_hash возвращают структуру. |
| `test_add_edit` | Добавление edit для существующего content_hash. |
| `test_neighbor_with_data` | Neighbor для существующей даты возвращает соседа. |
| `test_search_with_data` | Search на БД с данными возвращает результаты. |
| `test_photo_detail_with_data` | Корневой эндпоинт с path возвращает детали фото. |
| `test_map_with_data` | Map endpoint с GPS-данными возвращает точки. |
| `test_dates_with_data` | Dates histogram с данными возвращает годы. |

**Класс `TestSettingsAPI`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_get_setting_not_found` | GET несуществующей настройки возвращает пустое значение. |
| `test_set_and_get_setting` | PUT + GET настройки работает. |
| `test_top_personas_for_facts` | Top personas for facts возвращает text. |

**Класс `TestConfigAPI`** (4 методов: 4 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_get_config` | GET /api/config возвращает группы настроек. |
| `test_config_update_env_key` | Config update с env_key изменяет настройку. |
| `test_config_update_prompt_key` | Config update с prompt_ ключом сохраняется в settings БД. |
| `test_config_update_no_key` | Config update без env_key возвращает ok=False. |

**Класс `TestBackupAPI`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_backup_download` | Backup download возвращает gzip. |
| `test_backup_upload_no_file` | Backup upload без файла возвращает 422. |

**Класс `TestProxyAPI`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_ollama_check` | Ollama check endpoint не падает. |
| `test_ollama_check_invalid_url` | Ollama check с некорректным URL не крашит. |
| `test_ollama_models` | Ollama models endpoint не падает. |

**Класс `TestAdminAPI`** (5 методов: 5 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_admin_page` | Admin страница загружается. |
| `test_admin_js` | Admin JS файл доступен. |
| `test_gallery_page` | Gallery страница загружается. |
| `test_persons_page` | Persons страница загружается. |
| `test_catalog_page` | Catalog страница загружается. |

**Класс `TestServicesAPI`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_get_services` | GET /api/services возвращает список сервисов. |
| `test_restart_unknown_service` | Restart неизвестного сервиса возвращает ok=False. |

**Класс `TestMqttWorkersAPI`** (1 методов: 1 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_mqtt_workers` | GET /api/mqtt/workers возвращает статус воркеров. |

**Класс `TestControlExtendedAPI`** (7 методов: 7 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_control_start_hash` | Запуск hash step — mock os.system. |
| `test_control_start_dedup_ingest` | Запуск dedup_ingest step. |
| `test_control_start_chain` | Запуск chain step (pipeline). |
| `test_control_start_unknown_step` | Запуск неизвестного step возвращает ok=False. |
| `test_control_stop` | Control stop — mock системных вызовов. |
| `test_control_reset_unknown_step` | Control reset с неизвестным step. |
| `test_control_start_describe_with_root` | Запуск describe с root_id — mock os.system. |

**Класс `TestFixOllamaUrl`** (4 методов: 4 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_adds_http_prefix` | URL без схемы получает http://. |
| `test_keeps_http` | URL с http:// сохраняется. |
| `test_converts_https_to_http` | https:// заменяется на http://. |
| `test_adds_port` | URL без порта получает :11434. |

**Класс `TestSpaFallback`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_html_request_returns_gallery` | Запрос HTML для неизвестного пути возвращает gallery.html. |
| `test_non_html_request_returns_404` | Запрос без text/html возвращает 404. |

**Класс `TestMaintenanceExtendedAPI`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_maintenance_stats_structure` | Maintenance stats возвращает ожидаемые поля. |
| `test_maintenance_vacuum` | Maintenance vacuum выполняется. |
| `test_maintenance_dedup_embeddings` | Maintenance dedup embeddings выполняется. |

#### `test_code_quality.py` (963 строк)
*test_code_quality.py — структурная аналитика кода для ИИ-агентов.*
`tests/test_code_quality.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `test_no_critical_monoliths` | Файлы больше FILE_MAX_LINES — критичные монолиты. |
| `test_file_sizes_report` | Отчёт по всем файлам > FILE_WARN_LINES — warning, не fail. |
| `test_no_giant_functions` | Python функции > FUNC_MAX_LINES — критичные монстры. |
| `test_long_functions_report` | Отчёт по функциям > FUNC_WARN_LINES — warning, не fail. |
| `test_no_extreme_complexity` | Функции с complexity > COMPLEXITY_MAX — критичные. |
| `test_complexity_report` | Отчёт по функциям с complexity > COMPLEXITY_WARN. |
| `test_no_unmaintainable_files` | Файлы с MI < MI_MIN — непригодные для поддержки. |
| `test_mi_report` | Отчёт по файлам с MI < MI_WARN. |
| `test_html_duplication_not_critical` | Дублирование между HTML файлами > DUP_MAX_BLOCKS — критичное. |
| `test_html_duplication_report` | Отчёт по дублированию HTML — warning. |
| `test_no_undefined_names` | Ruff F821 — undefined names (баг: обращение к несуществующей переменной). |
| `test_no_repeated_dict_keys` | Ruff F601 — повтор ключа в dict (перезатирание значения). |
| `test_no_bare_except` | Ruff E722 — bare except (глушит все ошибки включая KeyboardInterrupt). |
| `test_blind_except_backlog` | BLE001 — blind except Exception без re-raise (AI-антипаттерн #1). |
| `test_unused_imports_backlog` | F401 — unused imports. Backlog: порог = baseline, только снижается. |
| `test_unused_vars_backlog` | F841 — unused local variables. Backlog: порог = baseline, только снижается. |
| `test_cyclomatic_complexity_backlog` | C901 — функции с cyclomatic complexity > 15 (манифест §4.1). |
| `test_no_dead_code_100pct` | Vulture — мёртвый код с 100% confidence (точно неиспользуемое). |
| `test_dead_code_report` | Отчёт по мёртвому коду — warning. |
| `test_no_duplicate_js_functions` | Функции определённые в нескольких JS файлах — дублирование кода. |
| `test_no_duplicate_js_functions_report` | Отчёт по дублированию — warning (даже если функция в одном файле, но >1 раза). |
| `test_no_js_conflicts_per_html_page` | Конфликты функций на одной HTML странице. |
| `test_no_js_global_conflicts_per_html_page` | Конфликты глобальных var на одной HTML странице. |
| `test_god_object_backlog` | God Object detection — кол-во методов в классе (манифест §4.4). |
| `test_coupling_backlog` | Coupling — обращения к db.* из одного модуля (манифест §4.3, ≤100). |
| `test_branch_coverage_baseline_documented` | Branch coverage baseline — документация порога (манифест §3.3). |
| `test_eslint_errors_backlog` | ESLint: ошибки frontend (манифест §2.4 — 0 errors обязательно). |

**Внутренние хелперы:** 15 (_-функций)

#### `test_user_flows.py` (728 строк)
*E2E tests that mirror the real user experience in gallery.html.*
`tests/test_user_flows.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `check_server` |  |

**Внутренние хелперы:** 9 (_-функций)

**Класс `TestBrowseGallery`** (8 методов: 8 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_gallery_page_loads` |  |
| `test_timeline_loads` |  |
| `test_first_page_of_photos` |  |
| `test_photo_card_fields` |  |
| `test_thumbnail_loads` |  |
| `test_infinite_scroll_next_page` |  |
| `test_status_polling` |  |
| `test_status_cached_second_call` |  |

**Класс `TestViewPhotoDetail`** (9 методов: 9 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_detail_opens_on_click` |  |
| `test_detail_shows_description` |  |
| `test_detail_shows_faces` |  |
| `test_detail_shows_personas` |  |
| `test_face_crop_endpoint` |  |
| `test_face_context_endpoint` |  |
| `test_full_photo_endpoint` |  |
| `test_neighbor_next` |  |
| `test_neighbor_prev` |  |

**Класс `TestSearchWithFilters`** (13 методов: 13 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_text_search` |  |
| `test_person_filter` |  |
| `test_has_faces_filter` |  |
| `test_has_description_filter` |  |
| `test_has_gps_filter` |  |
| `test_date_range_filter` |  |
| `test_deleted_filter` |  |
| `test_sort_date_asc` |  |
| `test_sort_date_desc` |  |
| `test_search_results_include_faces` |  |
| `test_search_by_content_hash` |  |
| `test_person_filter_panel_loads` |  |
| `test_person_names_autocomplete` |  |

**Класс `TestPersonManagement`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_open_face_modal` |  |
| `test_person_faces_list` |  |
| `test_person_by_name` |  |

**Класс `TestPhotoOperations`** (7 методов: 7 публичных, 0 внутренних)
*Операции с фото — на миникопии БД.*
| Метод | Описание |
|-------|----------|
| `test_set_date` | Ручная дата устанавливается через API. |
| `test_clear_date` | Ручная дата очищается через API. |
| `test_set_gps` | GPS координаты устанавливаются через API. |
| `test_clear_gps` | GPS координаты очищаются через API. |
| `test_delete_and_undelete` | Мягкое удаление и восстановление через API. |
| `test_rotate_photo` | Поворот фото через API edits — файл должен существовать. |
| `test_get_edits` | Чтение правок: content_hash есть в minidb. |

**Класс `TestMapView`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_map_photos` |  |
| `test_map_page_loads` |  |

**Класс `TestCatalogPage`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_catalog_roots` |  |
| `test_catalog_stats` |  |
| `test_catalog_page_loads` |  |

**Класс `TestConfigAndControl`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_config_page` |  |
| `test_admin_page_loads` |  |
| `test_watchdog_crashes` |  |

**Класс `TestPageNavigation`** (1 методов: 1 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_page_loads` |  |

**Класс `TestEnrichDescription`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_enrich_photo` |  |
| `test_save_rich_description` |  |

**Класс `TestSemanticSearch`** (2 методов: 2 публичных, 0 внутренних)
*GPU required — needs llama-server for embedding + LanceDB.*
| Метод | Описание |
|-------|----------|
| `test_semantic_search_basic` |  |
| `test_semantic_search_no_query` |  |

**Класс `TestReverseGeocode`** (1 методов: 1 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_reverse_geocode` |  |

**Класс `TestBackup`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_download_backup` |  |
| `test_maintenance_stats` |  |

**Класс `TestSettings`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_get_setting` |  |
| `test_set_and_read_setting` | Запись и чтение setting через API — на миникопии БД. |

#### `test_database.py` (645 строк)
`tests/test_database.py`

**Класс `TestDatabaseInit`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_creates_tables` | При инициализации создаются все необходимые таблицы. |
| `test_migrations_applied` | Миграции добавили колонки manual_gps, manual_date, deleted. |

**Класс `TestPhotoCRUD`** (7 методов: 7 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_add_photo` | Добавление фото сохраняет путь и описание. |
| `test_add_photo_with_gps` | Добавление фото с GPS сохраняет координаты. |
| `test_add_photo_with_camera` | Добавление фото с информацией о камере сохраняет марку. |
| `test_get_photo_nonexistent` | Запрос несуществующего фото возвращает None без ошибок. |
| `test_get_photo_by_path` | Поиск фото по пути находит только что добавленное. |
| `test_count_photos` | Счётчик фото правильно считает добавленные записи. |
| `test_get_all_photos` | get_all_photos возвращает только canonical файлы из catalog. |

**Класс `TestPhotoSearch`** (8 методов: 8 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_search_basic` | Базовый поиск возвращает фото и корректный total. |
| `test_search_by_text` | Поиск по тексту находит фото с указанным словом в описании. |
| `test_search_with_faces_filter` | Фильтр has_faces=True возвращает только фото с лицами. |
| `test_search_with_gps_filter` | Фильтр has_gps=True находит фото с координатами. |
| `test_search_date_range` | Фильтр по диапазону дат ограничивает результаты. |
| `test_search_sort_asc` | Сортировка date_asc: более ранние фото идут первыми. |
| `test_search_sort_desc` | Сортировка date_desc: более поздние фото идут первыми. |
| `test_search_by_person` | Поиск по имени персоны находит фото с этим человеком. |

**Класс `TestDateHistogram`** (1 методов: 1 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_histogram` | Гистограмма дат содержит структуру years+months и корректный |

**Класс `TestPhotoUpdate`** (4 методов: 4 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_update_description` | Обновление description меняет значение в базе. |
| `test_update_rich_description` | Обновление rich_description отдельно от обычного. |
| `test_soft_delete` | Мягкое удаление: deleted=1, запись остаётся. |
| `test_update_manual_date` | Ручная дата сохраняется отдельно от автоматической. |

**Класс `TestFaceCRUD`** (5 методов: 5 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_add_face` | Добавление лица к фото возвращает face_id. |
| `test_add_face_duplicate_ignored` | Повторное добавление того же face_id игнорируется. |
| `test_get_face` | Получение лица по id возвращает корректную confidence. |
| `test_get_faces_for_photo` | Все лица одного фото возвращаются одним запросом. |
| `test_count_faces` | Счётчик лиц корректно учитывает добавленные записи. |

**Класс `TestPersonaCRUD`** (10 методов: 10 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_add_persona` | Добавление персоны с именем успешно. |
| `test_add_persona_duplicate_ignored` | Дубликат persona_id не создаёт вторую запись. |
| `test_get_persona` | Получение персоны по id возвращает display_name. |
| `test_get_all_personas` | Все персоны возвращаются списком. |
| `test_update_persona` | Обновление display_name и comment персоны. |
| `test_update_persona_clear_name` | Очистка display_name через clear_display_name=True. |
| `test_get_display_names` | Список имён содержит display_name всех персон. |
| `test_get_personas_by_name` | Поиск персон по имени находит все с одинаковым именем. |
| `test_merge_personas` | Слияние переносит лица из source в target, source удаляется. |
| `test_face_count_map` | face_count_map возвращает количество лиц по persona_id. |

**Класс `TestCatalogCRUD`** (5 методов: 5 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_add_root` | Добавление корня каталога с alias. |
| `test_get_roots` | Список корней возвращает все добавленные. |
| `test_delete_root` | Удаление корня: после удаления get возвращает None. |
| `test_add_catalog_files_batch` | Пакетное добавление файлов каталога. |
| `test_count_catalog_files` | Счётчик файлов с WHERE-условием. |

**Класс `TestCatalogExtended`** (8 методов: 8 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_update_catalog_root` | Обновление root: alias и enabled. |
| `test_update_catalog_file` | Обновление файла каталога по file_id. |
| `test_update_catalog_file_by_path` | Обновление файла каталога по abs_path. |
| `test_delete_catalog_file` | Удаление файла каталога по file_id. |
| `test_delete_catalog_files_by_root` | Удаление всех файлов root. |
| `test_get_catalog_file_by_path` | Поиск файла каталога по abs_path. |
| `test_get_catalog_file_by_path_not_found` | Поиск несуществущего пути возвращает None. |
| `test_add_photos_batch` | Пакетное добавление фото. |

**Класс `TestEditsCRUD`** (6 методов: 6 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_add_and_get_edits` | Добавление edit и получение по content_hash. |
| `test_add_multiple_edits` | Несколько edits для одного content_hash. |
| `test_remove_edit` | Удаление edit по edit_id. |
| `test_clear_edits_by_action` | Очистка edits по action. |
| `test_clear_all_edits` | Очистка всех edits для content_hash. |
| `test_get_edits_empty` | Пустой список для несуществующего content_hash. |

**Класс `TestSettings`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_set_and_get_setting` | Установка и получение настройки. |
| `test_get_setting_default` | Получение несуществующей настройки возвращает default. |
| `test_set_setting_overwrite` | Перезапись существующей настройки. |

**Класс `TestSystemMetrics`** (1 методов: 1 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_insert_and_get_metrics` | Вставка и получение системных метрик. |

**Класс `TestCanonicalDuplicates`** (5 методов: 5 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_mark_canonical_no_dupes` | mark_canonical_duplicates без дублей возвращает (0, 0). |
| `test_mark_canonical_with_dupes` | mark_canonical_duplicates помечает дубли как is_canonical=0. |
| `test_get_duplicate_paths` | get_duplicate_paths возвращает пути не-canonical копий. |
| `test_is_path_canonical` | is_path_canonical кэширует и возвращает статус. |
| `test_invalidate_canonical_cache` | invalidate_canonical_cache сбрасывает кэш. |

**Класс `TestGetStatus`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_status_empty_db` | get_status на пустой БД возвращает нули. |
| `test_status_with_data` | get_status с данными возвращает ненулевые счётчики. |

**Класс `TestInvalidateForPersona`** (1 методов: 1 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_invalidate_resets_flags` | invalidate_for_persona сбрасывает described, embedded для за |

**Класс `TestFaceExtended`** (5 методов: 5 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_get_all_faces` | get_all_faces возвращает все лица. |
| `test_count_faces_with_where` | count_faces с WHERE условием. |
| `test_get_faces_for_persona` | get_faces_for_persona возвращает лица персоны. |
| `test_update_face_persona` | update_face_persona меняет persona_id у лица. |
| `test_persona_face_id_map` | persona_face_id_map возвращает map persona_id → face_id. |

**Класс `TestCosineSimilarity`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_identical_vectors` | Косинусная схожесть идентичных векторов = 1.0. |
| `test_orthogonal_vectors` | Косинусная схожесть ортогональных векторов = 0.0. |
| `test_zero_vector` | Косинусная схожесть с нулевым вектором = 0.0. |

#### `test_performance.py` (531 строк)
*Performance tests against the REAL production database.*
`tests/test_performance.py`

**Зависит от:** `database`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `db` |  |
| `http` |  |

**Внутренние хелперы:** 1 (_-функций)

**Класс `TestDatabasePerformance`** (8 методов: 8 публичных, 0 внутренних)
*Direct DB method timing — measures SQLite query speed.*
| Метод | Описание |
|-------|----------|
| `test_get_status` |  |
| `test_search_60` |  |
| `test_search_60_with_face_enrichment` |  |
| `test_date_histogram` |  |
| `test_count_photos` |  |
| `test_get_all_faces_baseline` |  |
| `test_get_all_personas_baseline` |  |
| `test_targeted_vs_all_faces` |  |

**Класс `TestAPIPerformance`** (13 методов: 11 публичных, 2 внутренних)
*HTTP endpoint timing — measures full request-response cycle.*
| Метод | Описание |
|-------|----------|
| `test_health` |  |
| `test_gallery_page` |  |
| `test_api_status` |  |
| `test_api_status_cached` |  |
| `test_api_search_60` |  |
| `test_api_dates` |  |
| `test_api_config` |  |
| `test_api_log` |  |
| `test_api_status_no_event_loop_block` |  |
| `test_api_concurrent_status_polling` |  |
| `test_api_concurrent_search` |  |

**Класс `TestDatabaseIndexCoverage`** (8 методов: 8 публичных, 0 внутренних)
*Verify critical indexes exist for performance-critical queries.*
| Метод | Описание |
|-------|----------|
| `test_faces_content_hash_index` |  |
| `test_catalog_files_abs_path_index` |  |
| `test_catalog_files_content_hash_index` |  |
| `test_photos_root_id_index` |  |
| `test_photos_deleted_index` |  |
| `test_photos_effective_date_index` |  |
| `test_query_plan_faces_by_content_hash` |  |
| `test_query_plan_status_photos_root` |  |

**Класс `TestAntipatternDetection`** (7 методов: 7 публичных, 0 внутренних)
*Detect known performance antipatterns in API code.*
| Метод | Описание |
|-------|----------|
| `test_search_endpoint_no_get_all_faces` |  |
| `test_list_endpoint_no_get_all_faces` |  |
| `test_semantic_search_no_get_all_faces` |  |
| `test_status_endpoint_runs_in_executor` |  |
| `test_log_reading_in_executor` |  |
| `test_no_db_get_status_in_main_thread` |  |
| `test_status_cache_ttl_not_zero` |  |

**Класс `TestScaleBaseline`** (1 методов: 1 публичных, 0 внутренних)
*Document current DB scale so performance budgets stay realistic.*
| Метод | Описание |
|-------|----------|
| `test_record_counts` |  |

#### `test_mqtt_unit.py` (471 строк)
*Тесты для mqtt_client.py — unit-тесты с моками MQTT.*
`tests/test_mqtt_unit.py`

**Зависит от:** `mqtt_client`

**Класс `TestTopicFunctions`** (12 методов: 12 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_worker_status_topic` |  |
| `test_worker_progress_topic` |  |
| `test_worker_pid_topic` |  |
| `test_worker_gpu_held_topic` |  |
| `test_gpu_lock_topic` |  |
| `test_control_start_topic` |  |
| `test_control_stop_topic` |  |
| `test_control_pause_topic` |  |
| `test_control_resume_topic` |  |
| `test_watchdog_mode_topic` |  |
| `test_db_cmd_topic` |  |
| `test_db_result_topic` |  |

**Класс `TestPublish`** (7 методов: 6 публичных, 1 внутренних)
| Метод | Описание |
|-------|----------|
| `test_publish_dict` | publish с dict сериализует в JSON. |
| `test_publish_bool` | publish с bool → 'true'/'false'. |
| `test_publish_int` | publish с int → str. |
| `test_publish_float` | publish с float → str. |
| `test_publish_str` | publish со str без преобразования. |
| `test_publish_retain_qos` | publish передаёт retain и qos. |

**Класс `TestWorkerMQTT`** (16 методов: 15 публичных, 1 внутренних)
| Метод | Описание |
|-------|----------|
| `test_stop_requested_all` | _handle_stop с step='all' ставит _stop_requested. |
| `test_stop_requested_specific` | _handle_stop с конкретным step совпадает. |
| `test_stop_requested_other` | _handle_stop с чужим step не останавливает. |
| `test_stop_requested_bad_json` | _handle_stop с некорректным JSON не крашит. |
| `test_stop_requested_empty_payload` | _handle_stop с пустым payload не крашит. |
| `test_pause` | _handle_pause ставит _pause_requested. |
| `test_resume` | _handle_resume снимает _pause_requested. |
| `test_publish_status` | publish_status публикует статус. |
| `test_publish_progress` | publish_progress публикует done/total/pct. |
| `test_publish_progress_extra` | publish_progress с extra добавляет поля. |
| `test_publish_progress_zero_total` | publish_progress с total=0 не крашит (max(total,1) = 1). |
| `test_publish_pid` | publish_pid публикует PID процесса. |
| `test_publish_gpu_held` | publish_gpu_held публикует bool. |
| `test_publish_progress_extra_overwrites` | publish_progress extra может перезаписать done/total. |
| `test_release_gpu_non_gpu_worker` | release_gpu для не-GPU воркера — no-op. |

**Класс `TestApiMQTT`** (26 методов: 25 публичных, 1 внутренних)
| Метод | Описание |
|-------|----------|
| `test_worker_states_init` | ApiMQTT инициализирует состояния всех воркеров. |
| `test_is_worker_alive_idle` | Воркер в idle — не живой. |
| `test_is_worker_alive_running_no_pid` | Воркер running без pid — живой (fallback). |
| `test_is_worker_alive_running_with_live_pid` | Воркер running с живым pid — живой. |
| `test_is_worker_alive_running_with_dead_pid` | Воркер running с мёртвым pid — мёртв, статус→dead. |
| `test_is_worker_alive_done` | Воркер done — не живой. |
| `test_is_worker_alive_dead` | Воркер dead — не живой. |
| `test_is_worker_alive_paused_with_pid` | Воркер paused с живым pid — живой. |
| `test_get_current_step_idle` | Все idle — current_step=idle. |
| `test_get_current_step_running` | Один воркер running — current_step=имя воркера. |
| `test_get_current_step_first_running` | Первый running воркер из списка — current_step. |
| `test_send_start` | send_start публикует команду start. |
| `test_send_start_no_params` | send_start без params. |
| `test_send_stop` | send_stop публикует команду stop. |
| `test_send_pause` | send_pause публикует команду pause. |
| `test_send_resume` | send_resume публикует команду resume. |
| `test_release_gpu_from_api` | release_gpu_from_api очищает lock и шлёт resume. |
| `test_get_watchdog_mode` | get_watchdog_mode возвращает текущий режим. |
| `test_is_db_writing_default` | is_db_writing по умолчанию False. |
| `test_make_handler_status` | _make_handler для status обновляет состояние. |
| `test_make_handler_progress` | _make_handler для progress парсит JSON. |
| `test_make_handler_progress_bad_json` | _make_handler для progress с плохим JSON → None. |
| `test_make_handler_pid` | _make_handler для pid парсит int. |
| `test_make_handler_pid_bad` | _make_handler для pid с не-int → None. |
| `test_make_handler_gpu_held` | _make_handler для gpu_held парсит bool. |

**Класс `TestConstants`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_worker_names` |  |
| `test_gpu_workers` |  |
| `test_pipeline_gpu_procs` |  |

#### `test_environment.py` (410 строк)
*Tests that the runtime environment has correct dependency versions.*
`tests/test_environment.py`

**Зависит от:** `config`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `test_numpy_below_2` | Проверяет что numpy < 2.0. |
| `test_onnxruntime_gpu_pinned` | Проверяет что onnxruntime-gpu строго 1.18.0. |
| `test_opencv_python_works` | Проверяет что opencv-python совместим с текущим numpy. |
| `test_opencv_headless_works` | Проверяет что opencv-python-headless совместим с текущим numpy. |
| `test_insightface_importable` | Проверяет что insightface импортируется без ошибок. |
| `test_all_dependencies_list` | Сводная проверка всех критических зависимостей одним тестом. |
| `test_api_service_active` |  |
| `test_watchdog_service_active` | watchdog.service должен быть active — иначе pipeline не следит. |
| `test_mosquitto_service_active` | mosquitto.service (MQTT broker) должен быть active. |
| `test_all_services_active` | Сводная: все три сервиса активны одним тестом. |
| `test_api_health_responds` | Health-check API отвечает на localhost:8000. |
| `test_mqtt_broker_reachable` | MQTT брокер доступен на localhost:1883. |
| `test_pipeline_process_exists` | Процесс pipeline.py запущен ИЛИ idle (все шаги завершены). |
| `test_watchdog_process_exists` | Процесс watchdog.py запущен. |
| `test_api_status_returns_data` | Статус API возвращает ненулевые счётчики фото. |
| `test_gallery_search_works` | Галерея: /api/photos/search возвращает валидный JSON с фото. |
| `test_gallery_photos_api_works` | Галерея: ключевые API фото возвращают 200 + JSON. |
| `test_gallery_page_renders` | Галерея: /gallery отдаёт HTML (не 500). |
| `test_watchdog_mode_consistent_with_flags` | mode из API согласован с реальным состоянием: sleeping/waiting/active. |
| `test_persons_api_includes_unnamed` | Без named_only API персон возвращает и именованных и неименованных. |
| `test_admin_js_valid` | Все JS модули админки не содержат синтаксических ошибок — проверяется через Node |
| `test_all_gallery_endpoints_return_json` | Все ключевые API эндпоинты отдают валидный JSON — без этого |

**Внутренние хелперы:** 3 (_-функций)

#### `test_gallery_ui.py` (351 строк)
*Tests for core gallery UI functionality.*
`tests/test_gallery_ui.py`

**Зависит от:** `database`, `main`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `gallery` |  |

**Внутренние хелперы:** 1 (_-функций)

**Класс `TestGallerySearchPage`** (12 методов: 12 публичных, 0 внутренних)
*Главный экран галереи — /api/photos/search*
| Метод | Описание |
|-------|----------|
| `test_search_200` | Поиск возвращает 200 на реальных данных. |
| `test_search_returns_photo_list` | Результат содержит total >= 3 и photos длиной >= 3. |
| `test_search_photo_has_required_fields` | Каждое фото содержит все поля нужные фронтенду. |
| `test_search_photo_content_hash_present` | Все фото в результатах поиска имеют content_hash. |
| `test_search_photo_faces_linked_by_content_hash` | Лица привязаны к фото через content_hash, а не photo_id. |
| `test_search_no_deleted_photos` | Удалённые фото не показываются в результатах поиска. |
| `test_search_text_query` | Текстовый поиск находит фото по описанию. |
| `test_search_person_filter` | Фильтр по персоне находит фото с этим человеком. |
| `test_search_has_faces_filter` | Фильтр has_faces=true: все результаты имеют faces_present=Tr |
| `test_search_has_gps_filter` | Фильтр has_gps=true находит фото с координатами. |
| `test_search_date_range` | Фильтр по диапазону дат корректно ограничивает результаты. |
| `test_search_deleted_only` | Фильтр deleted_only=true показывает только удалённые фото. |

**Класс `TestGalleryDatesPage`** (3 методов: 3 публичных, 0 внутренних)
*Страница дат — /api/photos/dates*
| Метод | Описание |
|-------|----------|
| `test_dates_200` | Гистограмма дат возвращает 200. |
| `test_dates_has_years` | Год 2024 содержит ≥2 фото. |
| `test_dates_no_deleted` | Удалённые фото исключены из гистограммы. |

**Класс `TestGalleryStatusPage`** (3 методов: 3 публичных, 0 внутренних)
*Страница статуса — /api/status*
| Метод | Описание |
|-------|----------|
| `test_status_200` | Статус доступен. |
| `test_status_has_progress_fields` | Ответ содержит все поля прогресса. |
| `test_status_total_reasonable` | Счётчики catalog/photos >= 3, pct_ingested = 100%. |

**Класс `TestGalleryMapPage`** (2 методов: 2 публичных, 0 внутренних)
*Карта — /api/photos/map*
| Метод | Описание |
|-------|----------|
| `test_map_200` | Карта возвращает 200. |
| `test_map_returns_gps_photos` | Результат — список фото с lat/lon. |

**Класс `TestGalleryNeighbor`** (2 методов: 2 публичных, 0 внутренних)
*Навигация между фото — /api/photos/neighbor*
| Метод | Описание |
|-------|----------|
| `test_neighbor_next_200` | Соседнее фото вперёд доступно. |
| `test_neighbor_prev_200` | Соседнее фото назад доступно. |

**Класс `TestGalleryPhotoCRUD`** (3 методов: 3 публичных, 0 внутренних)
*Операции с фото — date/gps/delete/undelete*
| Метод | Описание |
|-------|----------|
| `test_set_date` | Ручная дата устанавливается и возвращает success. |
| `test_set_gps` | GPS координаты устанавливаются через API. |
| `test_mark_deleted_and_undelete` | Удаление и восстановление: оба возвращают 200. |

**Класс `TestGalleryPersonPage`** (3 методов: 3 публичных, 0 внутренних)
*Страница персон — /api/persons*
| Метод | Описание |
|-------|----------|
| `test_persons_list_200` | Список персон — пагинированный ответ с total. |
| `test_persons_names_200` | Имена персон доступны для автокомплита. |
| `test_person_has_faces` | Персона имеет face_count ≥ количеству привязанных лиц. |

**Класс `TestGalleryCatalogPage`** (2 методов: 2 публичных, 0 внутренних)
*Страница каталога — /api/catalog*
| Метод | Описание |
|-------|----------|
| `test_roots_200` | Корни каталога доступны. |
| `test_stats_200` | Статистика каталога доступна. |

#### `test_pipeline_control.py` (348 строк)
`tests/test_pipeline_control.py`

**Зависит от:** `api.photos`, `config`, `main`, `mqtt_client`

**Класс `TestApiStatus`** (4 методов: 4 публичных, 0 внутренних)
*Статус API через MQTT — главный источник current_step.*
| Метод | Описание |
|-------|----------|
| `test_status_returns_pipeline_fields` | Ответ содержит поля current_step, processes, server_time. |
| `test_status_idle_when_no_workers` | Без MQTT-воркеров current_step = idle. |
| `test_status_sees_mqtt_worker` |  |
| `test_status_mqtt_priority_over_flags` |  |

**Класс `TestControlStart`** (3 методов: 3 публичных, 0 внутренних)
*Тесты вызывают реальный /api/control/start — ЗАПУСКАЕТ ПРОЦЕССЫ.*
| Метод | Описание |
|-------|----------|
| `test_start_unknown_step` | Неизвестный step возвращает ok=False. |
| `test_start_returns_step` |  |
| `test_start_chain` |  |

**Класс `TestControlStop`** (4 методов: 4 публичных, 0 внутренних)
*Тесты вызывают реальный /api/control/stop — ОСТАНАВЛИВАЕТ ПРОЦЕССЫ.*
| Метод | Описание |
|-------|----------|
| `test_stop_returns_ok` |  |
| `test_stop_removes_flags` | Флаги удаляются ТОЛЬКО из tmp_data (не реальный FLAG_DIR). |
| `test_stop_creates_no_restart` | no_restart в tmp_data создаётся после stop. |
| `test_start_removes_no_restart` |  |

**Класс `TestGPUArbitrationViaMQTT`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_enrich_uses_mqtt_gpu` |  |
| `test_enrich_no_mqtt_falls_through` |  |
| `test_mqtt_gpu_lock_and_release` |  |

**Класс `TestWatchdogMode`** (2 методов: 2 публичных, 0 внутренних)
*Режим сторожевого пса: active когда следит, sleeping когда спит.*
| Метод | Описание |
|-------|----------|
| `test_watchdog_crashes_returns_mode` | Эндпоинт возвращает mode и no_restart. |
| `test_watchdog_mode_consistent` | mode=sleeping <=> no_restart=True, mode=active <=> no_restar |

**Класс `TestControlButtonStates`** (3 методов: 3 публичных, 0 внутренних)
*Проверка что кнопки UI реагируют на состояние пайплайна.*
| Метод | Описание |
|-------|----------|
| `test_status_idle_after_stop` |  |
| `test_current_step_not_idle_when_pipeline_flag` | С флагом pipeline current_step не idle. |
| `test_pipeline_started_at_none_when_idle` |  |

**Класс `TestConfigAPI`** (4 методов: 4 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_config_returns_groups` |  |
| `test_config_group_structure` |  |
| `test_config_has_paths` |  |
| `test_config_has_models` |  |

**Класс `TestOllamaEmbedAI`** (13 методов: 12 публичных, 1 внутренних)
*Integration tests for Ollama dual-circuit embedding (requires AI)*
| Метод | Описание |
|-------|----------|
| `test_ollama_embed_single` |  |
| `test_ollama_embed_batch_4` |  |
| `test_embed_engine_ollama_mode` |  |
| `test_embed_engine_local_mode` |  |
| `test_get_ollama_mode` |  |
| `test_set_and_get_ollama_url` |  |
| `test_set_and_get_ollama_mode` |  |
| `test_set_ollama_embed_chunk` |  |
| `test_ollama_check_invalid_url` |  |
| `test_ollama_models_invalid_url` |  |
| `test_fix_ollama_url_formats` |  |
| `test_describe_backend_setting` |  |

#### `test_security.py` (299 строк)
*test_security.py — тесты безопасности (SAST + SCA + фаззинг).*
`tests/test_security.py`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `test_bandit_no_high_without_nosec` | SAST: 0 находок HIGH severity без обоснованного nosec. |
| `test_bandit_no_medium_without_nosec` | SAST: 0 находок MEDIUM severity без обоснованного nosec. |
| `test_no_known_cves` | SCA: 0 известных CVE в runtime-зависимостях. |
| `test_fuzz_path_no_crash` | Фаззинг: произвольный path — сервер не должен падать (500 или обрыв). |
| `test_fuzz_json_body_no_crash` | Фаззинг: произвольное JSON тело на POST эндпоинт — сервер не должен падать. |
| `test_fuzz_query_params_no_crash` | Фаззинг: некорректные query-параметры — сервер не должен падать. |
| `test_fuzz_path_traversal_no_crash` | Фаззинг: path traversal попытки (../) — сервер не должен падать или отдать файлы |

**Внутренние хелперы:** 2 (_-функций)

#### `conftest.py` (253 строк)
`tests/conftest.py`

**Зависит от:** `database`, `main`

**Публичные функции:**
| Функция | Описание |
|---------|----------|
| `tmp_data` |  |
| `db` |  |
| `db_with_photos` |  |
| `app_client` |  |
| `minidb` | Миникопия реальной БД: структура + первые N реальных строк. |

**Внутренние хелперы:** 4 (_-функций)

#### `test_system_helpers.py` (226 строк)
*Тесты для system_helpers.py — чистые unit-тесты без GPU/MQTT.*
`tests/test_system_helpers.py`

**Зависит от:** `system_helpers`

**Класс `TestDeterminePipelineStep`** (9 методов: 8 публичных, 1 внутренних)
| Метод | Описание |
|-------|----------|
| `test_idle_no_flags` | Нет флагов — шаг idle. |
| `test_mqtt_step_overrides_flags` | MQTT шаг приоритетнее флагов. |
| `test_flag_describe` | Флаг describe определяет шаг. |
| `test_flag_embed` | Флаг embed определяет шаг. |
| `test_flag_faces` | Флаг faces определяет шаг. |
| `test_flag_exif` | Флаг exif определяет шаг. |
| `test_flag_pipeline` | Флаг pipeline определяет шаг. |
| `test_no_mq` | Работа без MQTT (mq=None). |

**Класс `TestGetGitInfo`** (1 методов: 1 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_returns_commit_and_date` | Git info возвращает commit hash и date в реальном репо. |

**Класс `TestReadLogInfo`** (6 методов: 6 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_empty_log` | Чтение несуществующего лога возвращает пустые структуры. |
| `test_log_with_tags` | Чтение лога с тегами извлекает progress. |
| `test_log_faces_detecting` | Лог с [FACES] detecting определяет фазу. |
| `test_log_faces_clustering` | Лог с Running DBSCAN определяет фазу clustering. |
| `test_log_faces_done` | Лог с Clustering done определяет фазу done. |
| `test_log_faces_loading` | Лог с InsightFace loaded определяет фазу loading. |

**Класс `TestCollectDisks`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_returns_list` | _collect_disks возвращает список дисков. |
| `test_disk_structure` | Каждый диск имеет нужные поля. |

**Класс `TestCollectGpuProcesses`** (1 методов: 1 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_returns_list` | _collect_gpu_processes возвращает список. |

**Класс `TestCollectTopProcs`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_returns_list` | _collect_top_procs возвращает список процессов. |
| `test_proc_structure` | Каждый процесс имеет pid, name, mem_pct, cpu_pct. |

**Класс `TestCollectPipelineStats`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_stats_empty_db` | _collect_pipeline_stats на пустой БД возвращает нули. |
| `test_stats_with_data` | _collect_pipeline_stats с данными возвращает ненулевые счётч |

#### `test_mqtt.py` (180 строк)
`tests/test_mqtt.py`

**Зависит от:** `mqtt_client`

**Класс `TestMQTTWorkerLifecycle`** (3 методов: 3 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_worker_publishes_running_on_start` | Воркер публикует статус running + PID при старте, API их вид |
| `test_worker_publishes_progress` | Воркер публикует прогресс done/total с процентом. |
| `test_mqtt_stop_sets_stopped_flag` | API-команда stop доходит до воркера, worker.stopped() = True |

**Класс `TestMQTTApiStatus`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_api_detects_mqtt_worker_alive` | API видит живого воркера, get_current_step возвращает не idl |
| `test_api_sees_dead_worker_as_idle` | После done+disconnect воркер считается мёртвым с точки зрени |

**Класс `TestMQTTGPUArbitration`** (1 методов: 1 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_pause_resume_cycle` | API может приостановить и возобновить воркер через pause/res |

**Класс `TestMQTTFlagFallback`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_status_uses_flags_when_no_mqtt_worker` | Без MQTT статус берётся из файлов-флагов. |
| `test_mqtt_overrides_stale_flag` | MQTT-статус приоритетнее файлов-флагов. |

#### `test_middleware.py` (93 строк)
`tests/test_middleware.py`

**Класс `TestBfcacheFixMiddleware`** (5 методов: 5 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_bfcache_encoded_url` | BFCACHE: закодированный URL перенаправляется на правильный п |
| `test_bfcache_decoded_url` | BFCACHE: декодированный URL тоже обрабатывается без ошибок. |
| `test_head_converted_to_get` | HEAD-запросы конвертируются в GET, возвращают 200 с пустым т |
| `test_normal_get_unaffected` | Обычный GET не затрагивается middleware. |
| `test_bfcache_preserves_query` | Query-параметры сохраняются при BFCACHE-редиректе. |

**Класс `TestBrowserErrorRedirect`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_api_404_redirects_browser` | Браузерный 404 на API редиректится на gallery. |
| `test_api_404_keeps_json_client` | JSON-клиент получает честный 404, а не редирект. |

**Класс `TestSpaFallback`** (2 методов: 2 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_unknown_path_returns_gallery` | SPA fallback: любой неизвестный путь отдаёт gallery.html. |
| `test_unknown_path_json_404` | SPA fallback не срабатывает для JSON-запросов. |

**Класс `TestPageRoutes`** (4 методов: 4 публичных, 0 внутренних)
| Метод | Описание |
|-------|----------|
| `test_page_serves_html` | Все SPA-страницы отдают HTML с content-type text/html. |
| `test_root_redirects` | Корень '/' редиректит на /gallery. |
| `test_favicon` | Favicon отдаётся без ошибок. |
| `test_health` | Эндпоинт /health возвращает status: ok. |

## God Objects (классы с >20 методов)

| Всего | Публ. | Внутр. | Файл | Класс |
|-------|-------|--------|------|-------|
| 91 | 70 | 21 | src/database.py | DatabaseManager |
| 26 | 25 | 1 | tests/test_mqtt_unit.py | TestApiMQTT |

## Топ-10 файлов по размеру

| Строк | Файл | Endpoints | Хелперов |
|-------|------|-----------|----------|
| 1535 | src/api/photos.py | 26 | 24 |
| 1443 | src/database.py | 0 | 2 |
| 1352 | src/main.py | 52 | 13 |
| 1145 | tests/test_api.py | 0 | 0 |
| 1037 | vision_describe.py | 0 | 25 |
| 963 | tests/test_code_quality.py | 0 | 15 |
| 775 | enrich_description.py | 0 | 6 |
| 746 | pipeline.py | 0 | 29 |
| 728 | tests/test_user_flows.py | 0 | 9 |
| 645 | embed.py | 0 | 18 |
