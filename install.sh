#!/bin/bash
set -uo pipefail

on_error() {
    echo -e "\033[0;31m[ERROR] Скрипт упал на строке $1 (код $2)\033[0m" >&2
    exit $2
}
trap 'on_error $LINENO $?' ERR

# =============================================================================
# Gailery — скрипт автоустановки
# Протестировано на: Ubuntu 24.04, NVIDIA P104-100 (Pascal SM 6.1), 8GB VRAM
# Драйвер: NVIDIA 560+ (CUDA 12.6 на хосте)
# =============================================================================
#
# ДОКУМЕНТИРОВАННЫЕ НЮАНСЫ УСТАНОВКИ:
#
# 1. PyTorch из PyPI ставит версию с CUDA 13.0 — НЕСОВМЕСТИМО с драйвером 560
#    (CUDA 12.6). Решение: ставить torch==2.6.0 с --index-url cu124
#
# 2. onnxruntime-gpu 1.18.0 несовместим с numpy>=2 (AttributeError: _ARRAY_API)
#    Решение: numpy<2.0 (1.26.4). tifffile и opencv-headless хотят numpy>=2, но
#    работают с numpy<2 на практике.
#
# 3. CUDA Toolkit нужен для сборки llama.cpp. README говорит "toolkit в контейнере
#    не нужен", но на голой машине (не LXC) — нужен. apt-пакет nvidia-cuda-toolkit
#    ставит CUDA 12.0, которая ломается на libnvidia-compute-535 (dpkg cross-device
#    link error). Решение: ставить cuda-toolkit-12-6 из репозитория NVIDIA.
#
# 4. CUDA Toolkit 12.0 (из apt) не поддерживает GCC 13 (Ubuntu 24.04). Нужно
#    ставить CUDA 12.6 из репо NVIDIA (поддерживает GCC 13).
#    Альтернатива: gcc-12/g++-12 + -DCMAKE_CUDA_HOST_COMPILER=g++-12
#
# 5. naming inconsistency: репо "gailery", но contrib/*.service используют пути
#    /opt/gailray (с 'r'). Нужно унифицировать пути в .env и systemd-сервисах.
#    Этот скрипт использует /opt/gailery (как в README).
#
# 6. requirements.txt не включает paho-mqtt, psutil, xxhash — нужны отдельно.
#
# 7. Pascal SM 6.1: onnxruntime-gpu НЕ работает с cuDNN 9.x, требует libcudnn.so.8.
#    Но torch 2.6.0+cu124 требует libcudnn.so.9. Решение: pip ставит cuDNN 9 (для torch),
#    а cuDNN 8 .so-файлы извлекаются из pip wheel и кладутся в /usr/local/cudnn8 + ldconfig.
#    Для SM 70+ (Turing/Ampere) этот шаг не нужен.
#
# 8. При сборке llama.cpp нужно указать -DCMAKE_CUDA_ARCHITECTURES=61 для Pascal.
#    Без этого бинарник не будет использовать GPU.
#
# 9. mosquitto нужен для GPU-арбитража (MQTT lock). Ставится из apt.
#
# 10. libvips-dev нужен для pyvips (генерация миниатюр). Без -dev пакета pip
#     не соберёт pyvips.
#
# 11. python-multipart отсутствует в requirements.txt, но нужен для POST /api/backup/upload
#     (RuntimeError: Form data requires "python-multipart").
#
# 12. llama-cpp-python отсутствует в requirements.txt, но нужен для embed.py (local mode).
#     Требует сборки с CUDA: CMAKE_ARGS="-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61"
#     Нужен CUDA Toolkit (шаг 5) ДО установки.
#
# 13. embed.py хардкодит Qwen3-Embedding-0.6B-Q8_0.gguf, а models.py указывает
#     F16. Решение: скачать F16, создать симлинк Q8_0 → F16.
#
# 14. database.py get_status(): SUM() в SQLite возвращает NULL при пустой таблице,
#     что ломает max(None, int). Нужен патч: photos_row[N] or 0.
#
# 15. Пакет nvidia-cudnn-cu12 (не nvidia.cudnn) — правильное имя для pip.
#     Версия 8.9.7.29 для Pascal; torch хочет 9.x, но 8.x работает с onnxruntime.
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${BLUE}=== $1 ===${NC}"; }

INSTALL_DIR="/opt/gailery"
VENV_DIR="$INSTALL_DIR/venv"
LLAMA_CPP_DIR="/opt/llama.cpp"
GGUF_DIR="$INSTALL_DIR/models/gguf"
CUDA_ARCH="61"

# =============================================================================
# Проверка предварительных условий
# =============================================================================
log_step "0. Проверка предварительных условий"

if [ "$(id -u)" -ne 0 ]; then
    log_error "Запустите от root: sudo bash install.sh"
    exit 1
fi

if ! command -v nvidia-smi &>/dev/null; then
    log_error "nvidia-smi не найден. Установите драйвер NVIDIA (560+)."
    exit 1
fi

DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
CUDA_VERSION=$(nvidia-smi 2>&1 | grep -oP 'CUDA Version:\s*\K[\d.]+' || echo "unknown")
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
VRAM_TOTAL=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1)
COMPUTE_CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1)

log_info "Драйвер: $DRIVER_VERSION"
log_info "CUDA (хост): $CUDA_VERSION"
log_info "GPU: $GPU_NAME"
log_info "VRAM: $VRAM_TOTAL"
log_info "Compute Capability: $COMPUTE_CAP"

# Определяем архитектуру CUDA по compute capability
CC_MAJOR=$(echo "$COMPUTE_CAP" | cut -d'.' -f1)
CC_MINOR=$(echo "$COMPUTE_CAP" | cut -d'.' -f2)
CUDA_ARCH="${CC_MAJOR}${CC_MINOR}"

if [ "$CC_MAJOR" -eq 6 ] && [ "$CC_MINOR" -eq 1 ]; then
    log_warn "Pascal SM 6.1 — нужен cuDNN 8.x (шаг 8 обязателен)"
    IS_PASCAL=1
else
    log_info "SM $COMPUTE_CAP — cuDNN 8 не требуется"
    IS_PASCAL=0
fi

PYTHON_VERSION=$(python3 --version 2>/dev/null | cut -d' ' -f2 | cut -d'.' -f1,2)
if [ "$PYTHON_VERSION" != "3.12" ]; then
    log_warn "Рекомендован Python 3.12, найден: $PYTHON_VERSION"
fi

# =============================================================================
# 1. Системные пакеты
# =============================================================================
log_step "1. Установка системных пакетов"

DEBIAN_FRONTEND=noninteractive apt-get update -qq

DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    build-essential cmake python3-venv python3-dev \
    libvips-dev mosquitto mosquitto-clients ffmpeg \
    libgl1-mesa-dev libglib2.0-0 xxhash wget git unzip \
    g++-12 gcc-12

log_info "Системные пакеты установлены"

# =============================================================================
# 2. Клонирование репозитория
# =============================================================================
log_step "2. Клонирование репозитория"

if [ -d "$INSTALL_DIR/.git" ]; then
    log_info "Репозиторий уже в $INSTALL_DIR"
else
    git clone https://github.com/siv237/gailery.git "$INSTALL_DIR"
    log_info "Репозиторий клонирован в $INSTALL_DIR"
fi

# =============================================================================
# 3. Создание директорий и .env
# =============================================================================
log_step "3. Создание директорий и .env"

mkdir -p "$INSTALL_DIR"/{data,thumbnails,logs,models/gguf,models/insightface/models/buffalo_l}

if [ ! -f "$INSTALL_DIR/.env" ]; then
    cat > "$INSTALL_DIR/.env" << ENVEOF
# Gailery environment configuration
PHOTO_SHARE_PATH=/photos

GALLERY_DATA_DIR=$INSTALL_DIR/data

GALLERY_THUMBNAILS_DIR=$INSTALL_DIR/thumbnails

GALLERY_LOGS_DIR=$INSTALL_DIR/logs

LLAMA_CPP_DIR=$LLAMA_CPP_DIR

GALLERY_VENV_PYTHON=$VENV_DIR/bin/python3
ENVEOF
    log_info ".env создан"
else
    log_info ".env уже существует"
fi

# =============================================================================
# 4. Python venv и зависимости
# =============================================================================
log_step "4. Python venv и зависимости"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip wheel setuptools

# НЮАНС #1: torch из PyPI — CUDA 13.0, несовместимо с драйвером 560
# НЮАНС #2: onnxruntime-gpu 1.18.0 несовместим с numpy>=2
# Решение: сначала ставим torch с cu124, потом requirements с numpy<2

log_info "Установка PyTorch с CUDA 12.4 (нюанс: PyPI-версия использует CUDA 13)..."
pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124

log_info "Установка requirements.txt (с numpy<2 для onnxruntime-gpu)..."
pip install "numpy<2.0"

# НЮАНС #1: pip install -r requirements.txt пытается обновить torch до >=2.10.0
# (CUDA 13) и numpy до >=2. Решение: исключаем torch из requirements (уже стоит с cu124),
# фиксируем numpy<2 через constraint-файл.
grep -vi '^torch' "$INSTALL_DIR/requirements.txt" > /tmp/gailery-req-notorch.txt
cat > /tmp/gailery-constraints.txt << CONEOF
numpy<2.0
CONEOF
pip install -r /tmp/gailery-req-notorch.txt -c /tmp/gailery-constraints.txt
rm -f /tmp/gailery-req-notorch.txt /tmp/gailery-constraints.txt

# НЮАНС #6: paho-mqtt, psutil, xxhash отсутствуют в requirements.txt
log_info "Установка недостающих зависимостей (нюанс: не в requirements.txt)..."
pip install paho-mqtt psutil xxhash

log_info "Установка python-multipart (нюанс #11: нужен для backup upload)..."
pip install python-multipart

log_info "Проверка CUDA в PyTorch..."
python3 -c "import torch; print(f'torch {torch.__version__} CUDA: {torch.cuda.is_available()}')" || true

log_info "Проверка onnxruntime..."
python3 -c "import onnxruntime; print(f'onnxruntime providers: {onnxruntime.get_available_providers()}')" || true

deactivate

# =============================================================================
# 5. CUDA Toolkit (нюанс #3, #4)
# =============================================================================
log_step "5. CUDA Toolkit из репозитория NVIDIA"

# НЮАНС #3: apt-пакет nvidia-cuda-toolkit ломается на libnvidia-compute-535
# НЮАНС #4: CUDA 12.0 из apt не поддерживает GCC 13 (Ubuntu 24.04)
# Решение: cuda-toolkit-12-6 из репо NVIDIA

if command -v /usr/local/cuda-12.6/bin/nvcc &>/dev/null; then
    log_info "CUDA Toolkit 12.6 уже установлен"
else
    log_info "Добавление репозитория NVIDIA..."
    wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb \
        -O /tmp/cuda-keyring_1.1-1_all.deb
    dpkg -i /tmp/cuda-keyring_1.1-1_all.deb
    apt-get update -qq

    # Удаление сломанных пакетов от apt-версии (если были)
    dpkg --remove --force-remove-reinstreq \
        libcuinj64-12.0 libnvidia-ml-dev nvidia-cuda-dev nvidia-cuda-toolkit \
        nvidia-profiler nvidia-visual-profiler nsight-systems nsight-systems-target \
        2>/dev/null || true

    log_info "Установка cuda-toolkit-12-6 (это долго, ~3GB)..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y cuda-toolkit-12-6

    log_info "CUDA Toolkit 12.6 установлен: $(/usr/local/cuda-12.6/bin/nvcc --version | grep release)"
fi

# =============================================================================
# 6. Сборка llama.cpp
# =============================================================================
log_step "6. Сборка llama.cpp с CUDA"

if [ -x "$LLAMA_CPP_DIR/build/bin/llama-server" ]; then
    log_info "llama-server уже собран"
else
    if [ ! -d "$LLAMA_CPP_DIR/.git" ]; then
        git clone https://github.com/ggml-org/llama.cpp.git "$LLAMA_CPP_DIR"
    fi

    # НЮАНС #8: CMAKE_CUDA_ARCHITECTURES=61 для Pascal
    log_info "Конфигурация cmake (CUDA arch=$CUDA_ARCH, GCC-12)..."
    cmake -B "$LLAMA_CPP_DIR/build" -S "$LLAMA_CPP_DIR" \
        -DGGML_CUDA=ON \
        -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH" \
        -DCMAKE_C_COMPILER=gcc-12 \
        -DCMAKE_CXX_COMPILER=g++-12 \
        -DCMAKE_CUDA_HOST_COMPILER=g++-12 \
        -DCMAKE_PREFIX_PATH=/usr/local/cuda-12.6

    log_info "Сборка llama.cpp (это долго, ~10 мин)..."
    cmake --build "$LLAMA_CPP_DIR/build" --config Release -j"$(nproc)"

    log_info "llama-server собран: $($LLAMA_CPP_DIR/build/bin/llama-server --version 2>&1 | head -1)"
fi

# =============================================================================
# 6b. llama-cpp-python (нюанс #12)
# =============================================================================
log_step "6b. llama-cpp-python для embed.py"

source "$VENV_DIR/bin/activate"

if python3 -c "import llama_cpp" 2>/dev/null; then
    log_info "llama-cpp-python уже установлен"
else
    log_info "Сборка llama-cpp-python с CUDA (нюанс #12: не в requirements.txt)..."
    CMAKE_ARGS="-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=$CUDA_ARCH -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.6/bin/nvcc -DCMAKE_PREFIX_PATH=/usr/local/cuda-12.6" \
        pip install llama-cpp-python --no-cache-dir
    log_info "llama-cpp-python установлен"
fi

deactivate

# =============================================================================
# 7. Скачивание GGUF моделей
# =============================================================================
log_step "7. Скачивание GGUF моделей"

mkdir -p "$GGUF_DIR"

# Qwen3.5-4B Q4_K_M (нюанс: репо unsloth, не Qwen — Qwen/ даёт 401)
VLM_SIZE=2740937888
if [ ! -f "$GGUF_DIR/Qwen3.5-4B-Q4_K_M.gguf" ] || [ "$(stat -c%s "$GGUF_DIR/Qwen3.5-4B-Q4_K_M.gguf" 2>/dev/null)" != "$VLM_SIZE" ]; then
    rm -f "$GGUF_DIR/Qwen3.5-4B-Q4_K_M.gguf"
    log_info "Скачивание Qwen3.5-4B-Q4_K_M (~2.7GB)..."
    wget -q --show-progress \
        "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf" \
        -O "$GGUF_DIR/Qwen3.5-4B-Q4_K_M.gguf"
else
    log_info "Qwen3.5-4B-Q4_K_M уже есть"
fi

# mmproj-BF16 (из того же репо unsloth)
MMPROJ_SIZE=675569344
if [ ! -f "$GGUF_DIR/mmproj-BF16.gguf" ] || [ "$(stat -c%s "$GGUF_DIR/mmproj-BF16.gguf" 2>/dev/null)" != "$MMPROJ_SIZE" ]; then
    rm -f "$GGUF_DIR/mmproj-BF16.gguf"
    log_info "Скачивание mmproj-BF16 (~675MB)..."
    wget -q --show-progress \
        "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/mmproj-BF16.gguf" \
        -O "$GGUF_DIR/mmproj-BF16.gguf"
else
    log_info "mmproj-BF16 уже есть"
fi

# Qwen3-Embedding-0.6B F16 (нюанс: HF файл lowercase f16, локальный uppercase F16)
EMBED_SIZE=1197629632
if [ ! -f "$GGUF_DIR/Qwen3-Embedding-0.6B-F16.gguf" ] || [ "$(stat -c%s "$GGUF_DIR/Qwen3-Embedding-0.6B-F16.gguf" 2>/dev/null)" != "$EMBED_SIZE" ]; then
    rm -f "$GGUF_DIR/Qwen3-Embedding-0.6B-F16.gguf"
    log_info "Скачивание Qwen3-Embedding-0.6B-F16 (~1.2GB)..."
    wget -q --show-progress \
        "https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/Qwen3-Embedding-0.6B-f16.gguf" \
        -O "$GGUF_DIR/Qwen3-Embedding-0.6B-F16.gguf"
else
    log_info "Qwen3-Embedding-0.6B-F16 уже есть"
fi

# НЮАНС #13: embed.py ожидает Q8_0, а мы скачали F16 — создаём симлинк
if [ ! -f "$GGUF_DIR/Qwen3-Embedding-0.6B-Q8_0.gguf" ]; then
    ln -sf "$GGUF_DIR/Qwen3-Embedding-0.6B-F16.gguf" "$GGUF_DIR/Qwen3-Embedding-0.6B-Q8_0.gguf"
    log_info "Создан симлинк Q8_0 → F16 (нюанс #13: embed.py ожидает Q8_0)"
fi

# InsightFace buffalo_l (автоскачка при первом запуске, но скачаем заранее)
INSIGHTFACE_DIR="$INSTALL_DIR/models/insightface/models/buffalo_l"
if [ ! -d "$INSIGHTFACE_DIR" ] || [ ! -f "$INSIGHTFACE_DIR/det_10g.onnx" ]; then
    log_info "Скачивание InsightFace buffalo_l..."
    mkdir -p "$INSIGHTFACE_DIR"
    wget -q "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip" \
        -O /tmp/buffalo_l.zip
    unzip -o /tmp/buffalo_l.zip -d "$INSIGHTFACE_DIR"
    rm -f /tmp/buffalo_l.zip
    # Также копируем в ~/.insightface (insightface library ищет там)
    mkdir -p "$HOME/.insightface/models/buffalo_l"
    cp "$INSIGHTFACE_DIR"/*.onnx "$HOME/.insightface/models/buffalo_l/"
else
    log_info "InsightFace buffalo_l уже есть"
fi

# PyTorch модель Qwen3-Embedding-0.6B (автоскачка при первом запуске embed.py)
log_info "PyTorch модель Qwen3-Embedding-0.6B скачается автоматически при первом запуске embed.py"

# =============================================================================
# 8. cuDNN для Pascal (нюанс #7/#15)
# =============================================================================
log_step "8. cuDNN: 9 для torch + 8 для onnxruntime (Pascal)"

# НЮАНС #7/#15: torch 2.6.0+cu124 требует libcudnn.so.9, но onnxruntime-gpu
# на Pascal SM 6.1 работает ТОЛЬКО с libcudnn.so.8. Решение: pip ставит cuDNN 9
# (для torch), а cuDNN 8 .so-файлы кладём в /usr/local/cudnn8 и ldconfig.

source "$VENV_DIR/bin/activate"

# ldconfig: сначала пути от pip (cuDNN 9 + cublas)
CUDNN9_LIB="$VENV_DIR/lib/python3.12/site-packages/nvidia/cudnn/lib"
CUBLAS_LIB="$VENV_DIR/lib/python3.12/site-packages/nvidia/cublas/lib"
cat > /etc/ld.so.conf.d/gailery-cudnn.conf << LDEOF
$CUDNN9_LIB
$CUBLAS_LIB
LDEOF

if [ "$IS_PASCAL" -eq 1 ]; then
    if [ -f /usr/local/cudnn8/libcudnn.so.8 ]; then
        log_info "cuDNN 8 .so-файлы уже в /usr/local/cudnn8"
    else
        log_info "Установка cuDNN 8 .so для onnxruntime (Pascal)..."
        mkdir -p /tmp/cudnn8dl /usr/local/cudnn8
        pip download nvidia-cudnn-cu12==8.9.7.29 -d /tmp/cudnn8dl --no-deps
        cd /tmp/cudnn8dl
        unzip -o nvidia_cudnn_cu12-8.9.7.29-py3-none-manylinux1_x86_64.whl \
            -d /tmp/cudnn8dl/extracted "nvidia/cudnn/lib/*"
        cp -a /tmp/cudnn8dl/extracted/nvidia/cudnn/lib/. /usr/local/cudnn8/
        rm -rf /tmp/cudnn8dl
        # Добавляем путь cuDNN 8 в ldconfig
        echo "/usr/local/cudnn8" >> /etc/ld.so.conf.d/gailery-cudnn.conf
        log_info "cuDNN 8 .so-файлы установлены в /usr/local/cudnn8"
    fi
else
    log_info "Не Pascal — cuDNN 8 не нужен (cuDNN 9 из pip работает)"
fi

ldconfig
deactivate

# =============================================================================
# 9. Mosquitto (MQTT брокер для GPU арбитража)
# =============================================================================
log_step "9. Mosquitto MQTT брокер"

if systemctl is-active --quiet mosquitto; then
    log_info "Mosquitto уже запущен"
else
    systemctl enable mosquitto
    systemctl start mosquitto
    log_info "Mosquitto запущен"
fi

# =============================================================================
# 10. Systemd сервисы
# =============================================================================
log_step "10. Systemd сервисы"

# НЮАНС #5: contrib/*.service используют /opt/gailray, а не /opt/gailery
# Создаём сервисы с правильными путями

cat > /etc/systemd/system/gailery.service << 'SVCEOF'
[Unit]
Description=Gailery Photo Gallery API
After=network.target mosquitto.service
Wants=mosquitto.service

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
SVCEOF

cat > /etc/systemd/system/gailery-pipeline.service << 'SVCEOF'
[Unit]
Description=Gailery Pipeline Worker
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
EnvironmentFile=/opt/gailery/.env
Type=simple
User=root
WorkingDirectory=/opt/gailery
Environment="PATH=/opt/gailery/venv/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/opt/gailery/src"
ExecStart=/opt/gailery/venv/bin/python3 /opt/gailery/pipeline.py
Restart=on-failure
RestartSec=30
StandardOutput=append:/opt/gailery/logs/pipeline-stdout.log
StandardError=append:/opt/gailery/logs/pipeline-error.log

[Install]
WantedBy=multi-user.target
SVCEOF

cat > /etc/systemd/system/gailery-watchdog.service << 'SVCEOF'
[Unit]
Description=Gailery Pipeline Watchdog
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
EnvironmentFile=/opt/gailery/.env
Type=simple
User=root
WorkingDirectory=/opt/gailery
Environment="PATH=/opt/gailery/venv/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/opt/gailery/src"
ExecStart=/opt/gailery/venv/bin/python3 /opt/gailery/watchdog.py
Restart=on-failure
RestartSec=30
StandardOutput=append:/opt/gailery/logs/watchdog.log
StandardError=append:/opt/gailery/logs/watchdog-error.log

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable gailery
log_info "Systemd сервисы созданы и включены (gailery, gailery-pipeline, gailery-watchdog)"

# =============================================================================
# 11. Патч database.py (нюанс #14)
# =============================================================================
log_step "11. Патч database.py: SUM() → NULL при пустой таблице"

# НЮАНС #14: SUM() в SQLite возвращает NULL при пустой таблице, ломает max(None, int)
DB_FILE="$INSTALL_DIR/src/database.py"
if grep -q 'photos_total = photos_row\[1\]' "$DB_FILE" 2>/dev/null; then
    sed -i 's/photos_total = photos_row\[1\]/photos_total = photos_row[1] or 0/' "$DB_FILE"
    sed -i 's/photos_only = photos_row\[2\]/photos_only = photos_row[2] or 0/' "$DB_FILE"
    sed -i 's/videos_ingested = photos_row\[3\]/videos_ingested = photos_row[3] or 0/' "$DB_FILE"
    sed -i 's/described = photos_row\[4\]/described = photos_row[4] or 0/' "$DB_FILE"
    sed -i 's/faces_flagged = photos_row\[5\]/faces_flagged = photos_row[5] or 0/' "$DB_FILE"
    sed -i 's/exif_done = photos_row\[6\]/exif_done = photos_row[6] or 0/' "$DB_FILE"
    sed -i 's/embedded = photos_row\[7\]/embedded = photos_row[7] or 0/' "$DB_FILE"
    sed -i 's/videos_exif = photos_row\[8\]/videos_exif = photos_row[8] or 0/' "$DB_FILE"
    sed -i 's/photos_deleted = photos_row\[9\]/photos_deleted = photos_row[9] or 0/' "$DB_FILE"
    log_info "database.py пропатчен (or 0 для SUM() NULL)"
else
    log_info "database.py уже пропатчен или не нужен"
fi

# =============================================================================
# 12. Запуск веб-сервера
# =============================================================================
log_step "12. Запуск gailery"

systemctl start gailery || true

sleep 3

# =============================================================================
# 13. Проверка установки
# =============================================================================
log_step "13. Проверка установки"

echo ""
echo "--- GPU ---"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null || echo "nvidia-smi недоступен"

echo ""
echo "--- Python / CUDA ---"
source "$VENV_DIR/bin/activate"
python3 -c "
import torch
print(f'torch {torch.__version__} CUDA: {torch.cuda.is_available()}')
" 2>/dev/null || echo "torch проверка не удалась"

python3 -c "
import onnxruntime
print(f'onnxruntime providers: {onnxruntime.get_available_providers()}')
" 2>/dev/null || echo "onnxruntime проверка не удалась"

deactivate

echo ""
echo "--- llama-server ---"
[ -x "$LLAMA_CPP_DIR/build/bin/llama-server" ] && echo "OK: $LLAMA_CPP_DIR/build/bin/llama-server" || echo "MISSING: llama-server"

echo ""
echo "--- Модели GGUF ---"
ls -lh "$GGUF_DIR/" 2>/dev/null || echo "Директория $GGUF_DIR пуста"

echo ""
echo "--- InsightFace ---"
ls "$INSTALL_DIR/models/insightface/models/buffalo_l/" 2>/dev/null | head -3 || echo "Не скачан"

echo ""
echo "--- Mosquitto ---"
systemctl is-active mosquitto 2>/dev/null || echo "Не запущен"

echo ""
echo "--- Gailery API ---"
curl -s http://localhost:8000/health 2>/dev/null || echo "Gailery ещё не отвечает (подождите 10 сек и повторите: curl http://localhost:8000/health)"

echo ""
echo "--- Systemd сервисы ---"
systemctl is-enabled gailery 2>/dev/null || true
systemctl is-active gailery 2>/dev/null || true

# =============================================================================
# Итог
# =============================================================================
echo ""
echo "=========================================="
log_info "Установка завершена!"
echo "=========================================="
echo ""
echo "Галерея:       http://$(hostname -I 2>/dev/null | awk '{print $1}'):8000/gallery"
echo "API статус:    curl http://localhost:8000/api/status"
echo "Логи:          tail -f $INSTALL_DIR/logs/gailery.log"
echo ""
echo "Следующие шаги:"
echo "  1. Укажите путь к фото в .env: PHOTO_SHARE_PATH=/mnt/photos"
echo "  2. Добавьте корень сканирования:"
echo "     source $VENV_DIR/bin/activate && export PYTHONPATH=$INSTALL_DIR/src"
echo "     python scan_catalog.py --add /mnt/photos"
echo "  3. Запустите первый проход:"
echo "     python pipeline.py"
echo "  4. Или включите автопайплайн:"
echo "     systemctl enable --now gailery-pipeline"
echo "     systemctl enable --now gailery-watchdog"
echo ""
echo "Остановка/перезапуск:"
echo "  systemctl restart gailery"
echo "  systemctl stop gailery"
echo ""
