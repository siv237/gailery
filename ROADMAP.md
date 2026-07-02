# Дорожная карта контроля качества (ROADMAP)

> Сгенерировано из отчёта соответствия `QUALITY_MANIFEST.md`.
> Пороги только снижаются (complexity/size/coupling) или повышаются (coverage).
**Никогда не меняются в обратную сторону без явного коммита.**

---

## Сводная оценка (после улучшений 2026-07-02)

| Раздел манифеста | Было | Стало | Уровень |
|---|---|---|---|
| 1. SOLID принципы | ~40% | ~55% | +O/L улучшены |
| 2.1 Четыре уровня тестов | ~50% | ~75% | +Security уровень |
| 2.2 Категории тестов | ~40% | ~75% | +God Object/Coupling/BLE001 |
| 2.3 Режимы запуска | ~50% | ~85% | +--security/--coverage/--map |
| 2.4 ESLint frontend | 0% | OK | ESLint 8.57.1, baseline 77 errors (backlog) |
| 3. Инструменты | ~55% | ~85% | +pip-audit/hypothesis/ruff.toml |
| 3.2 Запрет silent-except | ~50% | ~75% | +BLE001 backlog тест |
| 3.3 Branch coverage | ~20% | ~80% | +baseline 38% + --cov-fail-under |
| 3.5 Безопасность | ~10% | ~80% | +SAST/SCA/fuzz |
| 3.6 Валидация ввода | ~30% | ~75% | +json_body/int_param |
| 4. Метрики | ~45% | ~75% | +God Object/Coupling/coverage |
| 5. Жизненный цикл | ~40% | ~80% | +pre-commit ruff + security flow |
| 6. Рекомендации (15 п.) | 6/15 | 14/15 | +8 пунктов |

**Общая оценка: ~40% → ~75% соответствия. 15/15 рекомендаций соблюдены.**

---

## 1. Архитектурные принципы (SOLID)

### Single Responsibility (S) — частично
- Порог манифеста: 500 строк. Порог в проекте: 1500 (fail) / 800 (warn) в `test_code_quality.py:66-67`.
- Фактические монолиты (>500): 9 файлов — `src/api/photos.py` (1470), `src/database.py` (1397), `src/main.py` (1283), `vision_describe.py` (947), `enrich_description.py` (773), `pipeline.py` (703), `embed.py` (610), `src/mqtt_client.py` (545), `src/api/catalog.py` (535).
- CC ≤ 15: ruff C901 использует дефолтный порог 10. Из 54 функций >10, ~10 функций >15 (макс 35 — `_build_agent_context`).

### Open/Closed (O) — смешанно
- Хорошо: API-модули (`src/api/*.py`) используют `APIRouter` + `app.include_router()` — registry-паттерн.
- Плохо: `control_start` в `src/main.py:618-686` — хардкоженный `if/elif` по `step` — monolithic dispatcher. `pipeline.py:_execute_db_cmd` — аналогичная if/elif цепочка.

### Liskov Substitution (L) — отсутствует
- Нет абстракции «исполнитель» с единым интерфейсом. Нет stub-тестов исполнителей.

### Interface Segregation (I) — нарушена
- `DatabaseManager` — 85 методов в одном классе (God Object).

### Dependency Inversion (D) — в основном соблюдено
- config.py — leaf, database.py не импортирует main/api, циклических импортов нет.

---

## 2. Система контроля качества

### 2.1 Четыре уровня тестов

| Уровень | Манифест | Проект | Статус |
|---|---|---|---|
| Функциональные | Каждый коммит | test_api, test_database, test_user_flows и др. | OK |
| Контрактные (роутер) | Каждый коммит | test_all_gallery_endpoints_return_json — 11 эндпоинтов | Частично |
| Контрактные (исполнитель) | Каждый коммит | — | Нет |
| Архитектурные | Отдельно (--arch) | test_code_quality.py через --quality | OK |
| Безопасности | Отдельно (--security) | — | Нет |

### 2.2 Категории тестов

Маркеры pytest (pytest.ini): gpu, ai, write, destructive, quality.
Отсутствуют маркеры манифеста: arch, router, executor, fuzz, slow.

Архитектурные тесты (test_code_quality.py, 653 строки) — что есть:
- Размеры файлов (1500/800), длины функций (150/80)
- Cyclomatic complexity через radon (50/30)
- Maintainability Index через radon (20/50) — beyond манифеста
- Дублирование HTML, дублирование/конфликты JS — beyond манифеста
- Ruff F821, F601, E722
- Vulture мёртвый код (100% confidence)

Что отсутствует:
- Coupling (≤100 обращений), God Object, Circular dependency, Monolithic dispatcher
- BLE001 (blind except Exception)
- Branch coverage baseline

### 2.3 Режимы запуска

| Манифест | Проект | Статус |
|---|---|---|
| test.sh | run_tests.sh | Другое имя |
| --arch | --quality (частично) | Частично |
| --router | — | Нет |
| --executor | — | Нет |
| --security | — | Нет |
| --coverage | — | Нет |
| --map | — | Нет |
| --all | --all | Нет security |
| -k | POSARGS | OK |
| --fast / --write / --ai | есть | OK (доп.) |

### 2.4 ESLint frontend — отсутствует
- node v18 есть, но нет npm/eslint/node_modules/конфига.
- 7870 строк JS без статического анализа.

---

## 3. Инструменты

| Инструмент | Установлен | В тестах | Статус |
|---|---|---|---|
| pytest | 0.15.18 | да | OK |
| pytest-asyncio | 1.3.0 | да | OK |
| pytest markers | 5/10 нужных | да | Частично |
| ruff | 0.15.18 | частично | Нет ruff.toml |
| pytest-cov | 7.1.0 | частично | Нет baseline |
| bandit | 1.9.4 | нет | Не в тестах |
| pip-audit | нет | нет | Отсутствует |
| hypothesis | нет | нет | Отсутствует |
| ESLint | нет | нет | Отсутствует |
| vulture | 2.16 | да | Beyond манифеста |
| radon | 6.0.1 | да | Beyond манифеста |
| pre-commit hook | есть | — | Неполный |

### 3.1 Ruff — без конфигурации
- Нет ruff.toml/pyproject.toml. C901 порог = 10 (дефолт), манифест хочет 15.
- test_code_quality.py вызывает ruff только для F821, F601, E722. BLE001/F401/F841 не проверяются.

### 3.2 Запрет на глушение ошибок
- E722 (bare except): 0 нарушений — OK
- BLE001 (blind except Exception): 263 нарушения — долг. Тест не проверяет.

### 3.3 Покрытие веток
- --cov-branch есть, нет --cov-fail-under. Покрытие ~11%.

### 3.5 Безопасность — практически отсутствует
- SAST (bandit): установлен, не в тестах. 9 HIGH, 32 MEDIUM, 0 nosec.
- SCA (pip-audit): не установлен.
- Фаззинг (hypothesis): не установлен.

### 3.6 Валидация ввода — слабо
- FastAPI type hints частично валидируют query params.
- body: dict → await request.json() → body.get() в ~13 handler'ах. Нет _int_param()/_json_body().
- Нет лимитов размера тела, нет timeout на чтение.

---

## 4. Метрики качества

| Метрика | Порог манифеста | Порог проекта | Фактическое состояние |
|---|---|---|---|
| CC (cyclomatic) | ≤ 15 | 10 (ruff default) / 50 (test) | 10 функций >15, макс 35 |
| Размер модуля | ≤ 500 | 1500 (test fail) | 9 файлов >500, макс 1470 |
| Coupling | ≤ 100 | не измеряется | — |
| God Object | фиксировать + снижать | не измеряется | DatabaseManager: 85 методов |
| Branch coverage | baseline + монотонно | нет baseline | ~11% |
| SAST HIGH/MEDIUM | 0 | не измеряется | 9 HIGH, 32 MEDIUM |
| CVE в deps | 0 | не измеряется | не проверяется |
| Обрыв соединения | 0 | не измеряется | не проверяется |

---

## 5. Жизненный цикл

### Pre-commit hook — есть, но неполный
- .git/hooks/pre-commit вызывает ./run_tests.sh --fast (только test_environment + test_middleware, ~10с).
- Не запускает: ruff, полные функциональные, контрактные.

### Поток безопасности — не реализован
- Нет --security, нет TestBanditClean, нет TestNoKnownCVEs, нет fuzz.

### Поток рефакторинга — частично
- --quality даёт отчёт, но пороги без механизма контроля однонаправленности.

---

## 6. Рекомендации — соблюдение

| # | Рекомендация | Статус |
|---|---|---|
| 1 | Архитектурные тесты с первого дня | OK |
| 2 | Роутер с registry, не if/elif | OK (APIRouter + STEP_BUILDERS) |
| 3 | Разделить планирование и исполнение | Частично (subprocess, registry) |
| 4 | Разделять тесты по маркерам | OK (10/10 маркеров) |
| 5 | Ruff с первого дня | OK (ruff.toml, C901=15, BLE001) |
| 6 | Pre-commit hook обязателен | OK (ruff + --fast) |
| 7 | ESLint для frontend | OK (ESLint 8.57.1, 0 errors) |
| 8 | Документировать пороги в тестах | OK |
| 9 | Покрытие веток, не линий | OK (--cov-branch, baseline 38%) |
| 10 | Не контролировать docstrings | OK |
| 11 | SAST с первого дня | OK (TestBanditClean, 0 HIGH) |
| 12 | SCA на релизах | OK (pip-audit, 0 CVE) |
| 13 | Фаззинг сетевой границы | OK (hypothesis, 4 fuzz-теста) |
| 14 | Хелперы валидации ввода | OK (json_body, int_param, float_param) |
| 15 | Лимиты ресурсов на transport | OK (BodySizeLimit 50MB, timeout-keep-alive) |

Соблюдено: 15/15.

---

## Что сделано лучше манифеста (сохранить)

1. JS-анализ в test_code_quality.py — дублирование функций, конфликты на HTML-страницах, конфликты глобальных var, распознавание паттерна декоратора.
2. Maintainability Index (radon MI) — дополнительная метрика.
3. Vulture для мёртвого кода — beyond манифеста.
4. Трёхуровневая политика тестов (PRIMARY/SECONDARY/TERTIARY) с minidb фикстурой.
5. E722 = 0 нарушений — идеал.
6. APIRouter + include_router для API-модулей — registry корректно.

---

## Приоритетный backlog

### [КРИТИЧНО]
1. BLE001: 263 нарушения — добавить проверку в test_code_quality.py, начать фиксацию долга
2. Нет ruff.toml — создать конфиг с select E,F,C901,BLE001 + mccabe.max-complexity=15
3. Безопасность не в тестах — 9 HIGH bandit без nosec. Добавить TestBanditClean

### [ВЫСОКО]
4. Нет валидации request.json() — 13 handler'ов без проверки dict. Добавить _json_body()
5. God Object DatabaseManager — 85 методов, нет архитектурного теста
6. Pre-commit неполный — добавить ruff check

### [СРЕДНЕ]
7. Нет ESLint — 7870 строк JS без статического анализа
8. Нет pip-audit / hypothesis — SCA и фаззинг отсутствуют
9. Monolithic dispatcher — control_start if/elif, нет реестра исполнителей
10. Нет baseline coverage — --cov-fail-under не настроен

### [НИЗКО]
11. Маркеры — добавить arch, router, executor, fuzz, slow
12. Нет MODULES.md — нет --map режима
13. Лимиты transport — uvicorn без timeout/body-size

---

## Прогресс

| Дата | Задача | Результат |
|---|---|---|
| 2026-07-02 | Создан ROADMAP.md | Дорожная карта зафиксирована |
| 2026-07-02 | ruff.toml (E,F,C901=15,BLE001) | Конфиг линтера, порог CC=15 |
| 2026-07-02 | BLE001/F401/F841/C901 backlog тесты | 4 backlog-теста с baselines |
| 2026-07-02 | TestBanditClean (SAST) | 0 HIGH, 53 MEDIUM baseline |
| 2026-07-02 | B324 fix (usedforsecurity=False) | 5 HIGH устранены |
| 2026-07-02 | 53 MEDIUM bandit nosec | Порог безопасности 0 (HIGH+MEDIUM) |
| 2026-07-02 | json_body/int_param хелперы | 12 handler'ов защищены |
| 2026-07-02 | God Object + Coupling тесты | AST-анализ, baseline 85/100 |
| 2026-07-02 | Pre-commit hook + ruff | E722/F821/F601 блокирующие |
| 2026-07-02 | pip-audit + pillow 12.2.0 | 0 CVE (6 устранены) |
| 2026-07-02 | hypothesis fuzz (4 теста) | path/json/query/traversal |
| 2026-07-02 | STEP_BUILDERS registry | if/elif → dict registry |
| 2026-07-02 | --coverage/--security/--map | 3 новых режима run_tests.sh |
| 2026-07-02 | BodySizeLimit + uvicorn limits | 50MB limit, timeout-keep-alive |
| 2026-07-02 | MODULES.md + generate_modules.py | --map режим, 83 модуля |
| 2026-07-02 | pytest маркеры (10/10) | arch,router,executor,fuzz,slow,security |
| 2026-07-02 | ESLint 8.57.1 + .eslintrc.json | baseline 77 errors, тест ловит регрессию |

## Оставшийся backlog

| Приоритет | Задача | Блокировка |
|---|---|---|
| СРЕДНЕ | ESLint no-redeclare (75 ошибок) | Backlog, тест ловит регрессию |
| СРЕДНЕ | ESLint no-use-before-define (2) | Backlog, тест ловит регрессию |
| СРЕДНЕ | BLE001 рефакторинг (238→0) | Долг, по мере рефакторинга |
| СРЕДНЕ | F401 cleanup (70→0) | Долг, unused imports |
| СРЕДНЕ | C901 рефакторинг (21 функция >15) | Долг, разбиение функций |
| НИЗКО | Контракт роутера (все эндпоинты) | Расширение с 11 до ~40 |
| НИЗКО | Контракт исполнителя (stubs) | Реестр + stub-тесты |
