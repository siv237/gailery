<img src="web/logo-light.png" width="378">

# Gailery — AI-фотогалерея для домашнего файлового сервера

**Быстрая установка** (Ubuntu 24.04 + NVIDIA GPU):
```bash
curl -fsSL https://raw.githubusercontent.com/siv237/gailery/main/install.sh | sudo bash
```

**Gailery** — это веб-галерея для домашней файлопомойки, которая не просто показывает фотки, а понимает что на них. Запускается на вашем сервере, в фоне неторопливо анализирует фотографии и строит базу знаний: кто на фото, где снято, что происходит. Ваши фото остаются на вашем диске, ничто не уходит в облако.

Что она умеет:

- **Смысловой поиск** — ищите «весёлая вечеринка» или «мама на даче», и найдутся фото, даже если в описании этих слов нет. Поиск понимает смысл, а не только точные совпадения
- **Распознавание людей** — лица на фото группируются автоматически. Нужно только подписать: «Это Анна» — и все фото Анны найдутся по имени. Не обязательно подписывать каждого человека — unnamed кластеры тоже участвуют в поиске
- **Умные описания** — AI описывает фото на русском, а затем обогащает описания именами из вашей базы: вместо «мужчина в чёрной куртке» появляется «Петров Алексей»
- **Карта** — фото с GPS-координатами на интерактивной карте. Кластеры при зуме превращаются в миниатюры, reverse geocoding показывает адрес
- **Умное масштабирование** — кроп лица с контекстом: щёлкните по лицу на фото и получите кадр, центрированный на этом человеке, а не просто обрезанный квадрат
- **Таймлайн и слайдшоу** — навигация по годам, автопрокрутка по коллекции
- **Тёмная и светлая тема**

Всё это работает на одной дешёвой GPU за $30 — без подписок, без облака, без отправки ваших фото куда-либо.

**Фото-архив — неприкосновенен.** Gailery никогда не пишет в папку с фотографиями. Все описания, имена, семантические индексы, миниатюры — в собственной базе. Оригинальные файлы только читаются.

---

## Скриншоты

### Галерея
![Галерея](web/screenshots/gallery.png)
Сетка фотографий с таймлайном, поиском (точный + смысловой), слайдшоу, обогащёнными AI-описаниями. Светлая тема.

### Карта
![Карта](web/screenshots/map.png)
Интерактивная GPS-карта (Leaflet). Фото с координатами — точки на карте, при зуме 15+ превращаются в миниатюры. Кластеры группируют близкие фото. Попап с описанием и датой, reverse geocoding, ручная привязка GPS. Переключение слоёв: схема / спутник.

### Персоны
![Персоны](web/screenshots/personas.png)
Найденные лица группируются в персоны автоматически (DBSCAN кластеризация). Слева — именованные персоны с превью лица и счётчиком, справа — безымянные кластеры. Клик открывает карточку: поле ввода имени с автокомплитом, сетка лиц с confidence, привязка/отвязка кластеров. При переименовании — выбор: применить ко всем кластерам с этим именем или только к одному.

### Управление
![Управление](web/screenshots/control.png)
Панель управления: запуск пайплайна, бекап/рестор базы, обслуживание (VACUUM, дедупликация). Тёмная тема.

---

## Зачем это нужно

У вас дома сервер с дисками. На них годами копятся фотографии: с телефонов, с поездок, с дней рождения. Тысячи файлов в папках вроде `2023/2023_06_20 - Петровы и Друзья/`. Найти конкретное фото невозможно — нет описаний, никто не помнит когда и где.

Gailery подключается к вашей файлопомойке (SMB, NFS, bind mount — read-only) и в фоне постепенно разбирает архив:

1. Сканирует всё, вытягивает даты и GPS из EXIF
2. Описывает каждую фотографию по-русски
3. Находит лица, группирует в персоны — вы подписываете имена
4. Обогащает описания именами из базы
5. Строит смысловой индекс для поиска по содержимому

В итоге вы заходите в веб-галерею с телефона или ноутбука, набираете «лето на даче» — и вот они, фото. Или открываете персону «Анна» и видите все её фото за 10 лет. Или смотрите на карте, где снимали в отпуске.

---

## Возможности

- **AI-описание фото** — VLM (Qwen3.5-4B) генерирует описания на русском языке через llama-server
- **Обогащение описаний** — LLM подставляет имена людей, контекст папок и дат (tool-calling с 3 инструментами)
- **Детекция лиц** — InsightFace buffalo_l (GPU, onnxruntime CUDA): детекция + 512-dim векторные представления
- **Кластеризация персон** — DBSCAN (cosine, eps=0.4) инкрементально: существующие персоны не пересчитываются
- **Семантический поиск** — Qwen3-Embedding-0.6B (1024-dim), LanceDB cosine similarity
- **Текстовый поиск** — SQL LIKE по описаниям
- **EXIF-метаданные** — дата, GPS, камера, ISO, фокусное расстояние
- **GPS-карта** — Leaflet + markercluster, reverse geocoding
- **Каталог файлов** — сканирование источников, отслеживание статуса обработки
- **Веб-интерфейс** — галерея с таймлайном, слайдшоу, тёмная/светлая тема, адаптивный логотип
- **Бекап/рестор** — скачать/залить базу данных через веб-интерфейс
- **Обслуживание БД** — VACUUM SQLite, дедупликация LanceDB, размеры в реальном времени

## Стек

| Компонент | Технология |
|-----------|------------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| БД | SQLite (метаданные) + LanceDB (векторы) |
| VLM описание | Qwen3.5-4B GGUF Q4_K_M через llama-server (порт 8101) |
| LLM обогащение | Qwen3.5-4B GGUF через llama-server (порт 8103, tool-calling) |
| Семантические индексы | Qwen3-Embedding-0.6B: PyTorch CUDA (пайплайн) + GGUF (поиск, порт 8102) |
| Лица | InsightFace buffalo_l (onnxruntime-gpu 1.18, CUDA, SCRFD+ArcFace) |
| Кластеризация | scikit-learn DBSCAN (cosine) |
| EXIF | ExifRead + Pillow |
| Миниатюры | pyvips (WebP, 3 размера: sm=400, md=800, lg=1200) |
| Inference сервер | llama.cpp (llama-server, кастомные CUDA kernels, без cuDNN) |
| Frontend | Vanilla HTML/CSS/JS, Leaflet.js |

---

## Установка и развёртывание

### 1. Системные требования

- **ОС**: Debian 12+ / Ubuntu 24.04+ (проверено на Ubuntu 24.04)
- **GPU**: NVIDIA с CUDA support, минимум 6GB VRAM (проверено на P104-100 8GB, Pascal SM 6.1)
- **Драйвер NVIDIA**: 560+ (CUDA 12.6 на хосте, toolkit в контейнере не нужен)
- **Python**: 3.12
- **RAM**: 8GB минимум, 16GB рекомендовано
- **Диск**: ~15GB под модели + кэш + место под миниатюры и БД (на 96K фото: data 6GB, thumbs 2GB)

### 2. Клонирование

```bash
git clone https://github.com/siv237/gailery.git /opt/gailery
cd /opt/gailery
```

### 3. Переменные окружения

```bash
cp .env.example .env
```

Отредактируйте `.env`:

```bash
PHOTO_SHARE_PATH=/mnt/photos                # Папка с фото (read-only достаточно!)
GALLERY_DATA_DIR=/opt/gailery/data          # SQLite + LanceDB
GALLERY_THUMBNAILS_DIR=/opt/gailery/thumbnails
GALLERY_LOGS_DIR=/opt/gailery/logs
LLAMA_CPP_DIR=/opt/llama.cpp                # Папка куда собран llama.cpp
GALLERY_VENV_PYTHON=/opt/gailery/venv/bin/python3
```

### 4. Python-окружение

```bash
python3 -m venv /opt/gailery/venv
source /opt/gailery/venv/bin/activate
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
```

> **Важно для Pascal (SM 6.1)**: onnxruntime-gpu требует cuDNN 8.x. cuDNN 9.x не работает.
> Пакет `nvidia.cudnn` версии 8 ставится через pip (см. ниже). Для SM 70+ (Turing/Ampere) этот шаг не нужен.

### 5. Сборка llama.cpp

llama-server используется для VLM описаний, обогащения текстов и семантической индексации поиска.

```bash
git clone https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp
cd /opt/llama.cpp

# Сборка с CUDA (без cuDNN — кастомные CUDA kernels)
cmake -B build -DGGML_CUDA=ON
cmake --build build --config Release -j$(nproc)
```

После сборки бинарник: `/opt/llama.cpp/build/bin/llama-server`

### 6. Скачивание моделей

Все GGUF-модели кладутся в `/opt/gailery/gguf/`:

```bash
mkdir -p /opt/gailery/gguf
```

#### 6.1. Qwen3.5-4B — VLM описание + LLM обогащение (2 файла)

```bash
cd /opt/gailery/gguf

# Основная модель (Q4_K_M, ~2.7GB)
wget https://huggingface.co/Qwen/Qwen3.5-4B-GGUF/resolve/main/qwen3.5-4b-q4_k_m.gguf \
     -O Qwen3.5-4B-Q4_K_M.gguf

# Мультимодальный проектор (BF16, ~675MB) — нужен только для VLM описания
wget https://huggingface.co/Qwen/Qwen3.5-4B-GGUF/resolve/main/mmproj-BF16.gguf \
     -O mmproj-BF16.gguf
```

#### 6.2. Qwen3-Embedding-0.6B — семантический поиск и векторные представления

Используется в двух форматах:
- **PyTorch** (HuggingFace) — батч-векторизация в пайплайне
- **GGUF** — on-demand поиск через llama-server

```bash
# GGUF для поиска (~1.2GB)
cd /opt/gailery/gguf
wget https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/qwen3-embedding-0.6b-f16.gguf \
     -O Qwen3-Embedding-0.6B-F16.gguf

# PyTorch модель — скачивается автоматически при первом запуске embed.py
# Или заранее:
pip install huggingface_hub
huggingface-cli download Qwen/Qwen3-Embedding-0.6B
```

#### 6.3. InsightFace — детекция лиц

Скачивается автоматически при первом запуске `faces.py` в `~/.insightface/models/`.

Если нет интернета на сервере:

```bash
mkdir -p ~/.insightface/models/buffalo_l
cd ~/.insightface/models/buffalo_l
wget https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip
unzip buffalo_l.zip && rm buffalo_l.zip
```

### 7. cuDNN 8 для onnxruntime-gpu (только Pascal SM 6.1)

На Turing (SM 75+) и новее этот шаг **не нужен** — cuDNN 9 работает.

```bash
pip install nvidia.cudnn==8.9.7.29

echo "/opt/gailery/venv/lib/python3.12/site-packages/nvidia/cudnn/lib" > /etc/ld.so.conf.d/gailery-cudnn.conf
echo "/opt/gailery/venv/lib/python3.12/site-packages/nvidia/cublas/lib" >> /etc/ld.so.conf.d/gailery-cudnn.conf
ldconfig
```

### 8. Создание директорий

```bash
mkdir -p /opt/gailery/{data,thumbnails,logs}
```

### 9. systemd сервис

```bash
cat > /etc/systemd/system/gailery.service << 'EOF'
[Unit]
Description=Gailery Photo Gallery API
After=network.target

[Service]
EnvironmentFile=/opt/gailery/.env
Type=simple
User=root
WorkingDirectory=/opt/gailery/src
Environment="PATH=/opt/gailery/venv/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/opt/gailery/src"
ExecStart=/opt/gailery/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=append:/opt/gailery/logs/gailery.log
StandardError=append:/opt/gailery/logs/gailery-error.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gailery
systemctl start gailery
```

### 10. Первый запуск

```bash
source /opt/gailery/venv/bin/activate
export PYTHONPATH=/opt/gailery/src

# 1. Сканирование фото-коллекции
python scan_catalog.py --scan

# 2. Наполнение БД (первые 100 фото для проверки)
python ingest.py --random 100

# 3. EXIF-метаданные
python exif.py --all

# 4. AI-описание (VLM, ~7 мин на 100 фото)
python describe.py --limit 100

# 5. Детекция лиц
python faces.py

# 6. Семантическая индексация для поиска
python embed.py

# 7. Миниатюры
python generate_thumbnails.py

# 8. Обработка всей коллекции (автоматический цикл)
python pipeline.py
```

Галерея доступна: `http://YOUR_SERVER:8000/gallery`

### Проверка установки

```bash
curl http://localhost:8000/api/status
nvidia-smi
python -c "import torch; print('CUDA:', torch.cuda.is_available())"
python -c "import onnxruntime; print('ORT:', onnxruntime.get_available_providers())"
ls /opt/gailery/gguf/
```

---

## Пайплайн обработки

```
scan_catalog → ingest → describe (VLM) → faces (InsightFace) → exif → embed
```

GPU используется по очереди: VLM → InsightFace → PyTorch. Одновременно только один GPU-процесс.

### Пропускная способность (P104-100, 8GB VRAM)

Замеры из 326K строк логов, стабильные прогоны:

| Этап | фото/час | Примечание |
|------|--------:|------------|
| INGEST | 440 000 | каталог + SQLite |
| DESCRIBE | ~700 | VLM, узкое место |
| FACES | 16 000 | InsightFace GPU |
| CLUSTER | ~1 700 | LanceDB+DBSCAN, падает с ростом БД |
| EXIF | 615 000 | ExifRead, I/O |
| EMBED | 14 000 | Qwen3-0.6B GPU |

**Итого ~0.7K фото/час** полным циклом (лимит — DESCRIBE).
Холодный старт 95K фото ≈ 6 дней. Инкремент 100 фото ≈ 10 мин.

### Модели GPU

| Модель | Формат | Размер | Порт | Назначение |
|--------|--------|--------|------|-----------|
| Qwen3.5-4B | GGUF Q4_K_M | 2.7 GB | 8101 | VLM описание (с mmproj, 675MB) |
| Qwen3.5-4B | GGUF Q4_K_M | 2.7 GB | 8103 | LLM обогащение (text, tool-calling) |
| Qwen3-Embedding-0.6B | GGUF F16 | 1.2 GB | 8102 | Семантические индексы (on-demand) |
| Qwen3-Embedding-0.6B | PyTorch fp16 | ~1.2 GB | — | Батч-векторизация (пайплайн) |
| InsightFace buffalo_l | ONNX | ~100 MB | — | Детекция + векторные представления лиц |

---

## API

### Фото
- `GET /api/photos/search` — текстовый поиск (q, persona, date, sort, limit)
- `GET /api/photos/semantic_search` — семантический поиск
- `GET /api/photos/dates` — гистограмма по годам
- `GET /api/photos/thumbnail?path=&size=` — миниатюра
- `GET /api/photos/face/{face_id}` — кроп лица
- `POST /api/photos/{id}/enrich` — обогащение описания
- `PUT /api/photos/{id}/rich_description` — сохранение описания

### Персоны
- `GET /api/persons` — список персон
- `POST /api/persons/{id}/name` — установить имя
- `POST /api/persons/merge` — объединить персоны

### Бекап и обслуживание
- `GET /api/backup/download` — скачать gallery.db.gz
- `POST /api/backup/upload` — залить бекап БД
- `GET /api/maintenance/stats` — размеры БД
- `POST /api/maintenance/vacuum` — VACUUM SQLite
- `POST /api/maintenance/dedup_embeddings` — дедупликация LanceDB

### Управление
- `POST /api/control/start` — запуск пайплайна
- `POST /api/control/stop` — остановка

## Веб-страницы

| Страница | Назначение |
|----------|-----------|
| `/gallery` | Галерея: сетка, поиск (точный + смысловой), таймлайн, слайдшоу, обогащение описаний |
| `/persons` | Персоны: имена, автокомплит, превью лиц |
| `/control` | Управление пайплайном, бекап, обслуживание БД |
| `/catalog` | Каталог источников файлов |
| `/map` | GPS-карта (Leaflet) |
| `/log` | Лог пайплайна |

## Структура проекта

```
gailery/
├── src/
│   ├── main.py                  # FastAPI приложение
│   ├── database.py              # DatabaseManager (SQLite + LanceDB)
│   ├── config.py                # Конфигурация (env vars)
│   ├── cluster_personas.py      # Кластеризация DBSCAN
│   ├── thumbnails.py            # pyvips миниатюры
│   ├── persona.py               # Persona CRUD
│   └── api/
│       ├── photos.py            # Фото API (search, semantic, enrich, thumbnail)
│       ├── persons.py           # Персоны API
│       └── catalog.py           # Каталог API
├── web/                         # HTML-страницы (vanilla JS)
│   ├── gallery.html             # Основная галерея (~2100 строк)
│   ├── personas.html            # Персоны
│   ├── control.html             # Управление + бекап + обслуживание
│   ├── catalog.html             # Каталог
│   ├── map.html                 # GPS-карта
│   ├── log.html                 # Лог
│   ├── logo-dark.png            # Логотип (тёмная тема)
│   └── logo-light.png           # Логотип (светлая тема)
├── gguf/                        # GGUF модели (not in git)
├── data/                        # SQLite + LanceDB (not in git)
├── venv/                        # Python venv (not in git)
├── thumbnails/                  # WebP миниатюры (not in git)
├── logs/                        # Логи (not in git)
├── pipeline.py                  # Оркестратор пайплайна
├── ingest.py                    # Наполнение БД
├── describe.py                  # Оркестратор VLM
├── vision_describe.py           # VLM описания (llama-server:8101)
├── faces.py                     # InsightFace + кластеризация
├── exif.py                      # EXIF-метаданные
├── embed.py                     # PyTorch семантическая индексация
├── enrich_description.py        # LLM обогащение (llama-server:8103, tool-calling)
├── scan_catalog.py              # Скан каталога
├── generate_thumbnails.py       # Генерация миниатюр (pyvips)
├── .env.example                 # Шаблон окружения
└── AGENTS.md                    # Контекст для AI-агентов
```

## Известные ограничения

- **Pascal SM 6.1**: cuDNN 9.x не работает, нужен 8.x; torch.compile не работает (Triton требует SM 70+). На Turing+ этих проблем нет
- **GPU разделена**: VLM, InsightFace, PyTorch — работают по очереди, одновременно одна модель на GPU
- **Семантический поиск**: при поиске стартует llama-server для векторизации, пайплайн в это время не работает
- **Read-only**: Gailery не модифицирует оригинальные фото — это фича, а не баг

---

## Пример: Proxmox + LXC + GPU

Рабочий конфиг автора проекта. Gailery не требует Proxmox — достаточно любой Linux-машины с NVIDIA GPU. Этот раздел для тех, кто хочет запустить в LXC.

### Железо

| Компонент | Значение |
|-----------|----------|
| Сервер | Xeon E5-2680 v4, 16C/32T |
| RAM | 16 GB |
| GPU | NVIDIA P104-100, 8GB VRAM, Pascal SM 6.1, PCIe x4 |
| Диск | 126GB virtio на SSD (Proxmox) |
| Фото | SMB mount read-only |

P104-100 — дешёвая бывшая майнинговая карта (~$30), пассивное охлаждение, 8GB VRAM. Тянет Qwen3.5-4B (VLM) + InsightFace + Qwen3-Embedding. GPU по очереди, одновременно одна модель.

### LXC-конфиг (непривилегированный)

```
# /etc/pve/lxc/CTID.conf

tags: gpu
unprivileged: 1

# GPU устройства
lxc.mount.entry: /dev/nvidia0 dev/nvidia0 none bind,optional,create=file
lxc.mount.entry: /dev/nvidia1 dev/nvidia1 none bind,optional,create=file
lxc.mount.entry: /dev/nvidiactl dev/nvidiactl none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-uvm dev/nvidia-uvm none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-uvm-tools dev/nvidia-uvm-tools none bind,optional,create=file
lxc.mount.entry: /dev/nvidia-modeset dev/nvidia-modeset none bind,optional,create=file

# NVIDIA утилиты и библиотеки (подставить свою версию драйвера)
lxc.mount.entry: /usr/bin/nvidia-smi usr/bin/nvidia-smi none bind,optional,create=file
lxc.mount.entry: /usr/lib/x86_64-linux-gnu/libnvidia-ml.so usr/lib/x86_64-linux-gnu/libnvidia-ml.so none bind,optional,create=file
lxc.mount.entry: /usr/lib/x86_64-linux-gnu/libcuda.so usr/lib/x86_64-linux-gnu/libcuda.so none bind,optional,create=file
lxc.mount.entry: /usr/lib/x86_64-linux-gnu/libcudadebugger.so usr/lib/x86_64-linux-gnu/libcudadebugger.so none bind,optional,create=file
lxc.mount.entry: /usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1 usr/lib/x86_64-linux-gnu/libnvidia-ml.so.1 none bind,optional,create=file
lxc.mount.entry: /usr/lib/x86_64-linux-gnu/libcuda.so.1 usr/lib/x86_64-linux-gnu/libcuda.so.1 none bind,optional,create=file
lxc.mount.entry: /usr/lib/x86_64-linux-gnu/libcudadebugger.so.1 usr/lib/x86_64-linux-gnu/libcudadebugger.so.1 none bind,optional,create=file
lxc.mount.entry: /usr/lib/x86_64-linux-gnu/libcuda.so.560.35.03 usr/lib/x86_64-linux-gnu/libcuda.so.560.35.03 none bind,optional,create=file

# Фото-архив (read-only)
lxc.mount.entry: /mnt/share mnt/share none bind,ro,optional,create=dir
```

> **Важно**: `libcuda.so.XXX` — подставить версию вашего драйвера. Узнать: `ls /usr/lib/x86_64-linux-gnu/libcuda.so.*` на хосте.
