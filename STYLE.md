# Gailery Design System — STYLE.md

> Единый источник истины для всех страниц. Тесты парсят CSS и проверяют соответствие.
> Отклонение = fail.

---

## Манифест принципов

### 1. Single source of truth (NN/g)
Каждый компонент определён **один раз** в `shared.css` и переиспользуется везде.
Дублирование одного стиля под разными именами классов — нарушение.
Если 3 класса определяют одинаковый визуальный стиль — это 3 ошибки.

### 2. Limit your choices (Refactoring UI)
Чем меньше разновидностей — тем консистентнее.
- Кнопки: **3** варианта (base/secondary, primary/go, danger/stop) — не 18
- Инпуты: **1** стиль на всех страницах — не 8
- Карточки: **1** базовый стиль — не 28
Каждая новая разновидность — техдолг. Тесты фиксируют потолок, он только снижается.

### 3. Design tokens, not hardcoded values (Material 3 / Primer)
Цвета, отступы, размеры — именованные значения из палитры.
Hex напрямую — только в STYLE.md и shared.css. На страницах — классы.
`#fff` в `<button style="...">` = нарушение.

### 4. Use fewer borders (Refactoring UI)
Вместо бордюров — box-shadow, контраст фонов, больше пространства.
Меньше `border` = чище интерфейс.

### 5. Hierarchy through contrast, not size (Refactoring UI)
Не все элементы равны. Размер — не единственный инструмент.
Color, weight, spacing передают иерархию лучше чем `font-size: 999px`.

### 6. Theme-aware from the start (Primer)
Каждый цветной селектор имеет `.light-theme` вариант.
Инлайн `style=""` с цветом — запрещён (нельзя переопределить тему).
CSS variables (`var(--c-*)`) — для admin, hex из палитры — для страниц.

### 7. shared.css is the component library (NN/g Component Library)
Общие стили компонентов живут в `shared.css`, не дублируются per-page.
Страница использует `.btn`, `.card`, `.input` — не переопределяет их.
Per-page определения кнопок/инпутов/карточек → 0.

### 8. Consistency metric — testable (NN/g + Refactoring UI)
Консистентность измерима: число разновидностей стиля на тип элемента.
Тесты парсят CSS, считают уникальные сигнатуры, падают при росте.
Порог (baseline) только снижается — это метрика техдолга.

---

## Палитра

### Тёмная тема (базовая)

| Токен | Hex | Назначение |
|---|---|---|
| `bg-page` | `#0d1117` | Фон страницы |
| `bg-card` | `#161b22` | Фон карточек, панелей, toolbar |
| `bg-input` | `#0d1117` | Фон инпутов, текстовых полей |
| `bg-secondary` | `#21262d` | Вторичный фон (бейджи, hover) |
| `bg-deep-alt` | `#0d2240` | Альтернативный тёмный фон (embed) |
| `bg-green-tint` | `#0d2818` | Зелёный фон (success state) |
| `bg-red-tint` | `#2d0a0a` | Красный фон (danger state) |
| `border-default` | `#21262d` | Стандартная граница |
| `border-strong` | `#30363d` | Яркая граница (hover, акцент) |
| `border-muted` | `#d8dee4` | Светлая граница (редко) |
| `text-primary` | `#c9d1d9` | Основной текст |
| `text-bright` | `#e6edf3` | Яркий текст (заголовки) |
| `text-muted` | `#8b949e` | Приглушённый текст |
| `text-dim` | `#6e7681` | Дим текст (метаданные) |
| `text-faint` | `#484f58` | Очень тусклый (placeholder) |
| `accent` | `#58a6ff` | Акцент (ссылки, активные) |
| `accent-bg` | `#1f6feb` | Акцент фон (кнопки) |
| `success` | `#3fb950` | Успех |
| `success-bg` | `#238636` | Кнопки успеха |
| `success-hover` | `#2ea043` | Hover успеха |
| `warning` | `#d29922` | Предупреждение |
| `danger` | `#f85149` | Опасность |
| `danger-bg` | `#da3633` | Кнопки опасности |
| `orange` | `#f0883e` | Оранжевый (метки) |
| `gold` | `#e3b341` | Золото (theme toggle) |
| `purple` | `#d2a8ff` | Фиолетовый (config keys) |
| `purple-bg` | `#8250df` | Фиолетовый фон |
| `green-soft` | `#dafbe1` | Мягкий зелёный фон (diff) |
| `blue-soft` | `#ddf4ff` | Мягкий синий фон (diff) |
| `red-soft` | `#ffebe9` | Мягкий красный фон (diff) |
| `gray-light` | `#8c949e` | Серый (светлый faint) |
| `border-light-gray` | `#b1bac4` | Светло-серая граница |
| `panel-dark` | `#1c2128` | Тёмная панель (catalog) |

### Светлая тема

| Токен | Hex | Назначение |
|---|---|---|
| `bg-page` | `#ffffff` | Фон страницы |
| `bg-card` | `#f6f8fa` | Фон карточек |
| `bg-input` | `#f6f8fa` | Фон инпутов |
| `bg-secondary` | `#eaeef2` | Вторичный фон |
| `border-default` | `#d0d7de` | Граница |
| `border-strong` | `#afb8c1` | Яркая граница |
| `text-primary` | `#24292f` | Основной текст |
| `text-muted` | `#57606a` | Приглушённый |
| `text-dim` | `#6e7681` | Дим |
| `text-faint` | `#8c959f` | Очень тусклый |
| `accent` | `#0969da` | Акцент |
| `success` | `#1f883d` | Успех |
| `success-bg` | `#1f883d` | Кнопки |
| `success-hover` | `#29994a` | Hover успеха |
| `success-deep` | `#1a7f37` | Глубокий зелёный (hover light) |
| `warning` | `#9a6700` | Предупреждение |
| `danger` | `#cf222e` | Опасность |
| `danger-bg` | `#a40e26` | Кнопки |
| `orange` | `#bc4c00` | Оранжевый |
| `gold` | `#0969da` | Золото (→ акцент) |
| `purple` | `#8250df` | Фиолетовый |
| `gray` | `#333` | Тёмно-серый (map borders) |
| `gray-mid` | `#999` | Серый (map) |

### Запрещённые цвета

Любой hex не из таблиц выше = нарушение. Исключения:
- `#fff` / `#ffffff` — белый (текст на цветных кнопках)
- `#000` — чёрный (text-shadow)
- `transparent` / `rgba(...)` с прозрачностью — допустимо

---

## Типографика

| Свойство | Значение | Назначение |
|---|---|---|
| `font-family` | `monospace` | Все страницы |
| `font-family` | `system-ui, sans-serif` | Запрещён для страниц |
| Очень мелкий текст | `8px` | Микро-метки |
| Мелкий текст | `9px` | Микро-бейджи |
| Мелкий текст | `10px` | .card-source, .sidebar-footer .ver |
| Приглушённый текст | `11px` | .wcard-row, .cfg-desc, .status-val |
| Метаданные | `12px` | .card-meta, .detail-header .meta |
| Основной текст | `13px` | Тело карточек, панелей |
| Заголовок карточки | `14px`, `font-weight: 600` | .card-title, .task-info .tn |
| Средний заголовок | `15px` | Промежуточный |
| Заголовок страницы (h1/h2) | `16px` | В шапке |
| Крупный заголовок | `18px` | Подзаголовки |
| Большой текст | `20px` | Акценты |
| Большой заголовок | `22px` | Разделы |
| Крупный заголовок | `24px` | Разделы (admin) |
| Числа дашборда | `28px` | Admin dashboard |
| Числа дашборда | `30px` | Admin dashboard |
| Числа дашборда | `32px` | Admin dashboard |
| Числа дашборда | `36px` | Admin dashboard |
| Числа дашборда | `40px` | Admin dashboard |
| Числа дашборда | `44px` | Admin dashboard |
| `line-height` | `1.3` — `1.5` | По умолчанию |

### Запрещённые размеры шрифтов
- Любой размер не из таблицы выше = нарушение

---

## Компоненты

### Кнопки

| Класс | Назначение | Стиль dark | Стиль light |
|---|---|---|---|
| `.btn` | Базовая (secondary) | bg:#21262d, text:#c9d1d9, border:#30363d | bg:#f6f8fa, text:#24292f, border:#d0d7de |
| `.btn-go` | Действие (success) | bg:#238636, text:#fff | bg:#1f883d, text:#fff |
| `.btn-stop` | Стоп (danger) | bg:#da3633, text:#fff | bg:#cf222e, text:#fff |
| `.btn-sec` | Вторичная | bg:#21262d, text:#c9d1d9 | bg:#f6f8fa, text:#24292f |
| `.btn-warn` | Предупреждение | bg:#9e6a03, text:#fff | bg:#9a6700, text:#fff |
| `.btn-danger` | Опасная (outline) | bg:#21262d, border:#f85149, text:#f85149 | bg:#f6f8fa, border:#cf222e, text:#cf222e |

Размеры: `padding: 6px 16px`, `border-radius: 4px`, `font-size: 12px`, `font-family: monospace`
Hover: затемнение bg на +1 шаг, `cursor: pointer`
Disabled: `bg:#21262d, text:#484f58, cursor: default`

### Карточки

| Класс | Назначение | Стиль dark | Стиль light |
|---|---|---|---|
| `.card` | Карточка | bg:#161b22, border:#21262d, radius:6px | bg:#ffffff, border:#d0d7de |
| `.card:hover` | Hover | border:#30363d, transform:translateY(-2px) | border:#afb8c1 |
| `.card-body` | Внутренности | padding:12px 14px | — |
| `.card-title` | Заголовок | font:13px/600, color:#c9d1d9 | color:#24292f |
| `.card-meta` | Метаданные | font:11px, color:#8b949e | color:#57606a |

### Инпуты

| Класс | Назначение | Стиль dark | Стиль light |
|---|---|---|---|
| `.input` / `input[type=text]` | Текст | bg:#0d1117, text:#c9d1d9, border:#30363d, radius:4px | bg:#f6f8fa, text:#24292f, border:#d0d7de |
| `input:focus` | Фокус | border:#58a6ff | border:#0969da |
| `select` | Выбор | bg:#0d1117, text:#c9d1d9, border:#30363d | bg:#f6f8fa, text:#24292f, border:#d0d7de |

Размеры: `padding: 6px 10px`, `font-size: 13px`, `font-family: monospace`

### Сетки

| Класс | Назначение | Параметры |
|---|---|---|
| `.grid` | Фото/карточки | `display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:6px; padding:10px 20px` |
| `.grid-albums` | Альбомы | `minmax(280px,1fr); gap:16px; padding:20px` |
| `.summary` | Dashboard boxes | `display:flex; gap:8px` |

### Списки / Sidebar

| Класс | Назначение | Стиль dark | Стиль light |
|---|---|---|---|
| `.sidebar a` | Пункт меню | color:#8b949e, padding:7px 16px, border-left:3px transparent | color:#57606a |
| `.sidebar a:hover` | Hover | color:#c9d1d9, bg:rgba(255,255,255,.04) | color:#24292f, bg:#f6f8fa |
| `.sidebar a.active` | Активный | color:#58a6ff, border-left:#58a6ff, bg:rgba(88,166,255,.08) | color:#0969da, border-left:#0969da |
| `.mm-a` | Mobile пункт | color:#8b949e, padding:13px 16px, border-left:3px transparent | color:#57606a |
| `.mm-a.active` | Mobile активный | color:#58a6ff, bg:rgba(88,166,255,.06) | color:#0969da |

### Бейджи / Теги

| Класс | Назначение | Стиль dark | Стиль light |
|---|---|---|---|
| `.badge` / `.card-source` | Метка | bg:#21262d, color:#8b949e, radius:3px, font:10px | bg:#eaeef2, color:#57606a |
| `.tb-run` | Запущено | bg:rgba(35,134,54,.2), color:#3fb950, border:#238636 | bg:rgba(31,136,61,.15), color:#1f883d |
| `.tb-idle` | Ожидание | bg:#21262d, color:#6e7681 | bg:#eaeef2, color:#57606a |

---

## Эффекты

| Свойство | Значение | Назначение |
|---|---|---|
| `transition` | `.15s` (colors), `.2s` (transform), `.3s` (panel) | Плавность |
| `border-radius` | `0` (none), `2px` (хairline), `3px` (badges), `4px` (buttons/inputs), `6px` (cards), `8px` (panels), `10px` (special), `12px` (large cards), `16px` (modals), `50%` (circles) | Скругление |
| `box-shadow` | `0 8px 24px rgba(0,0,0,.4)` (dropdowns) | Тени только для overlay |
| `transform` | `translateY(-2px)` (card hover) | Подъём карточки |
| `cursor` | `pointer` (clickable), `default` (disabled) | Указатели |
| `opacity` | `.6` (pulse), `.7` (shimmer) | Анимации |

### Запрещённые эффекты
- `box-shadow` на карточках в обычном состоянии (только hover/overlay)
- `transition` > `.3s` (медленно)
- `border-radius` > `10px` (слишком круглое)
- `transform: scale(>1.1)` (слишком резко)

---

## Отступы и размеры

| Токен | Значение | Назначение |
|---|---|---|
| `padding-page` | `20px` | Внешний отступ контента от краёв |
| `padding-card` | `12px 14px` / `16px` | Внутри карточек |
| `padding-toolbar` | `10px 20px` | Toolbar |
| `gap-grid` | `6px` (gallery) / `8px` (admin) / `16px` (albums) | Между элементами сетки |
| `gap-flex` | `8px` / `12px` | Между flex элементами |
| `radius` | `6px` | Карточки |
| `radius-sm` | `4px` | Кнопки, инпуты |
| `radius-xs` | `3px` | Бейджи |
| `border-width` | `1px` (normal), `2px` (active/hover) | Толщина границ |

---

## Правила для теста

1. **Hex цвета** — только из таблиц палитры. Любой другой = fail.
2. **Инлайн `style=""`** с цветом (`:#`, `:rgb`) = запрещён.
3. **`.light-theme`** — каждый цветной селектор должен иметь light вариант.
4. **`font-family`** — `monospace` для body на всех страницах.
5. **`font-size`** — только из таблицы типографики (10/11/12/13/14/16/18px).
6. **`border-radius`** — только `3px/4px/6px` (до `10px` для особых случаев).
7. **`transition`** — не более `.3s`.
8. **`renderHeader()`** — все страницы используют единую шапку.
9. **`shared.css` + `shared.js`** — подключаются на всех страницах.
10. **Компонентные классы** — `.btn`, `.card`, `.grid` используются, не переопределяются с другими цветами.

---

## Тесты дизайн-системы

Все тесты в `tests/test_middleware.py`. Пороги (baseline) только снижаются.

### TestSharedHeader — единая шапка (12 тестов)

| Тест | Что проверяет | Best practice |
|---|---|---|
| `test_all_pages_200` | Все страницы отдают 200 | Доступность |
| `test_all_pages_have_render_header` | `renderHeader()` вызывается | Single source (NN/g) |
| `test_all_pages_load_shared_js_before_header` | shared.js загружается до шапки | Порядок инициализации |
| `test_all_pages_load_shared_css` | shared.css подключён | Component library (NN/g) |
| `test_shared_js_syntax_valid` | JS синтаксис валиден | Качество кода |
| `test_shared_css_has_header_styles` | CSS содержит стили шапки | Component library |
| `test_theme_styles_complete` | Light/dark темы полны | Theme-aware (Primer) |
| `test_no_duplicate_header_styles_in_pages` | Страницы не дублируют стили шапки | Single source |
| `test_theme_toggle_works_in_shared_js` | Переключатель темы работает | Theme-aware |
| `test_all_pages_have_shared_css` | shared.css на всех страницах | Component library |
| `test_all_css_elements_have_light_theme` | Все селекторы имеют light вариант | Theme-aware |
| `test_no_light_theme_body_selector` | Нет `.light-theme body` (неправильно) | CSS корректность |
| `test_no_inline_color_styles` | Нет инлайн стилей с цветом (baseline 17) | Design tokens, не hardcoded |

### TestPageStyleConformance — соответствие палитре (10 тестов)

| Тест | Что проверяет | Best practice |
|---|---|---|
| `test_no_forbidden_colors` | Нет запрещённых цветов | Design tokens (M3) |
| `test_all_hex_in_standard_palette` | Все hex из STYLE.md палитры | Design tokens |
| `test_no_inline_color_styles` | Инлайн стилей с цветом ≤ 17 (backlog) | Theme-aware |
| `test_all_pages_use_monospace_font` | `font-family: monospace` | Type scale (Refactoring UI) |
| `test_all_pages_have_light_theme_block` | `.light-theme {}` для body | Theme-aware |
| `test_dark_body_matches_standard` | Тёмный фон = `#0d1117` | Design tokens |
| `test_light_body_matches_standard` | Светлый фон = `#ffffff` / `#f6f8fa` | Design tokens |
| `test_admin_uses_css_variables` | Admin CSS использует `var(--c-*)` | Design tokens (Primer) |
| `test_font_sizes_in_standard_range` | Размеры только из таблицы | Type scale (Refactoring UI) |
| `test_no_non_monospace_font_family` | Нет запрещённых шрифтов | Type scale |
| `test_border_radius_in_standard` | radius только `0/2/3/4/6/8/10/12/16/50%` | Limit choices |
| `test_transition_not_too_slow` | transition ≤ .45s | Limit choices |

### TestStyleConsistency — метрика консистентности (5 тестов)

Парсят CSS всех страниц, считают уникальные визуальные сигнатуры
`(background, color, border, border-radius)` для каждого типа элемента.

| Тест | Что проверяет | Baseline | Цель | Best practice |
|---|---|---|---|---|
| `test_button_style_varieties` | Разновидностей стиля кнопок | **15** | ≤3 | Limit choices (Refactoring UI) |
| `test_input_style_varieties` | Разновидностей стиля инпутов | **8** | ≤1 | Single style |
| `test_card_style_varieties` | Разновидностей стиля карточек | **28** | ≤1 | Single style |
| `test_button_definitions_per_page` | Per-page определений кнопок | **9** | 0 | Component library в shared.css (NN/g) |
| `test_duplicate_button_styles_different_classes` | Дубликатов (один стиль, разные классы) | **6** | 0 | Single source of truth (NN/g) |
| `test_buttons_use_shared_classes` | Кнопок без общих классов | **11** | 0 | Component library (NN/g) |
| `test_no_page_with_alien_classes` | % уникальных классов на странице | **91%** | ≤40% | Single source (NN/g) |
| `test_no_shared_class_redefined_with_different_style` | Один класс — разные стили | **10** | 0 | Single source of truth (NN/g) |

#### Как работает метрика

```
CSS всех страниц → парсинг правил → (selector, {props})
  → фильтр по типу (button/input/card)
  → сигнатура (bg, color, border, radius)
  → группировка по сигнатуре
  → count уникальных = variety
```

- **Variety = 1** → все кнопки/инпуты/карточки выглядят одинаково (идеал)
- **Variety = 3** → base + primary + danger (допустимо для кнопок)
- **Variety = 18** → каждая страница придумала свой стиль (техдолг)

#### Как снижать baseline

1. Вынести стиль в `shared.css` как общий класс (`.btn`, `.btn-go`, `.btn-danger`)
2. Заменить per-page классы на общий (`.search-bar button` → `.btn-go`)
3. Убрать инлайн `style=""` → использовать класс
4. Запустить тест → variety уменьшилась → понизить baseline
5. Коммит

### Источники best practices

| Источник | Применённый принцип |
|---|---|
| Nielsen Norman Group — Design Systems 101 | Single source, component library, visual consistency |
| Refactoring UI (Wathan/Schoger) | Limit choices, type scale, fewer borders, hierarchy |
| Google Material Design 3 | Design tokens, primitives |
| GitHub Primer | CSS variables, theme-aware, component variants |
| web.dev / Google UX | Double diamond, validate with users |
