#!/bin/bash
set -uo pipefail

on_error() {
    echo -e "\033[0;31m[ERROR] Скрипт упал на строке $1 (код $2)\033[0m" >&2
    exit $2
}
trap 'on_error $LINENO $?' ERR

# =============================================================================
# Gailery — АВТО-инсталлер (двухрежимный: с GPU и без GPU)
#
# Отличия от install.sh:
#   * НЕ падает, если нет nvidia-smi. Вместо этого переходит в CPU-режим.
#   * Сам детектит GPU и выбирает состав зависимостей:
#       GPU : torch(cu124) + onnxruntime-gpu + llama.cpp/llama-cpp-python WITH CUDA
#              + CUDA Toolkit + cuDNN  (полностью повторяет install.sh)
#       CPU : torch(PyPI CPU) + onnxruntime(CPU) + llama.cpp/llama-cpp-python WITHOUT CUDA
#              (CUDA Toolkit и cuDNN НЕ ставятся)
#   * Код проекта НЕ меняется. Хардкод n_gpu_layers=99 / -ngl 99 в коде становится
#     инертным no-op на CPU-сборках llama.cpp и просто игнорируется.
#   * Опционально: если задана переменная окружения AUTO_OLLAMA_URL, в no-GPU режиме
#     прописывается OLLAMA_MODE=ollama (гибрид с удалённой видеокартой).
#
# Протестировано на: Ubuntu 24.04. Требует запуска от root.
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

# INSTALL_DIR можно переопределить: INSTALL_DIR=/path bash auto_install.sh
INSTALL_DIR="${INSTALL_DIR:-/opt/gailery}"
VENV_DIR="$INSTALL_DIR/venv"
LLAMA_CPP_DIR="/opt/llama.cpp"
GGUF_DIR="$INSTALL_DIR/models/gguf"
CUDA_ARCH="61"
SVC_NAME="gailery"
SVC_PIPELINE="${SVC_NAME}-pipeline"
SVC_WATCHDOG="${SVC_NAME}-watchdog"
CODE_UPDATED=0

# =============================================================================
# 0. Проверка прав и ДЕТЕКТ GPU
# =============================================================================
log_step "0. Права и детект окружения"

if [ "$(id -u)" -ne 0 ]; then
    log_error "Запустите от root: sudo bash auto_install.sh"
    exit 1
fi

# --- Детект GPU (НЕ фатальный, в отличие от install.sh) ---
HAS_GPU=0
GPU_NAME="(нет)"
CUDA_VERSION="(нет)"
COMPUTE_CAP=""
if command -v nvidia-smi &>/dev/null; then
    DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
    CUDA_VERSION=$(nvidia-smi 2>&1 | grep -oP 'CUDA Version:\s*\K[\d.]+' || echo "unknown")
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    VRAM_TOTAL=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1)
    COMPUTE_CAP=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1)
    HAS_GPU=1
    log_info "GPU обнаружен: $GPU_NAME (VRAM $VRAM_TOTAL, CUDA $CUDA_VERSION, CC $COMPUTE_CAP)"
else
    log_warn "nvidia-smi НЕ найден — переходим в CPU-режим (без локальной видеокарты)."
    log_warn "Внимание: AI-задачи (описание/индексация) на CPU работают, но МЕДЛЕННО."
fi

# Архитектура CUDA (нужна только при GPU)
CC_MAJOR=""; CC_MINOR=""
if [ "$HAS_GPU" -eq 1 ] && [ -n "$COMPUTE_CAP" ]; then
    CC_MAJOR=$(echo "$COMPUTE_CAP" | cut -d'.' -f1)
    CC_MINOR=$(echo "$COMPUTE_CAP" | cut -d'.' -f2)
    CUDA_ARCH="${CC_MAJOR}${CC_MINOR}"
fi

IS_PASCAL=0
if [ "$HAS_GPU" -eq 1 ]; then
    if [ "$CC_MAJOR" -eq 6 ] && [ "$CC_MINOR" -eq 1 ]; then
        log_warn "Pascal SM 6.1 — нужен cuDNN 8.x"
        IS_PASCAL=1
    else
        log_info "SM $COMPUTE_CAP — cuDNN 8 не требуется"
    fi
fi

PYTHON_VERSION=$(python3 --version 2>/dev/null | cut -d' ' -f2 | cut -d'.' -f1,2)
if [ "$PYTHON_VERSION" != "3.12" ]; then
    log_warn "Рекомендован Python 3.12, найден: $PYTHON_VERSION"
fi

# =============================================================================
# 1. Системные пакеты
# =============================================================================
log_step "1. Системные пакеты"

DEBIAN_FRONTEND=noninteractive apt-get update -qq 2>/dev/null || true

DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-upgrade \
    build-essential cmake python3-venv python3-dev \
    libvips-dev mosquitto mosquitto-clients ffmpeg \
    libgl1-mesa-dev libglib2.0-0 xxhash wget git unzip \
    g++-12 gcc-12 libimage-exiftool-perl

log_info "Системные пакеты проверены"

# =============================================================================
# 2. Клонирование / обновление репозитория
# =============================================================================
log_step "2. Клонирование / обновление репозитория"

if [ -d "$INSTALL_DIR/.git" ]; then
    log_info "Репозиторий в $INSTALL_DIR — обновляем..."
    BEFORE=$(git -C "$INSTALL_DIR" rev-parse HEAD)
    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" reset --hard origin/main
    git -C "$INSTALL_DIR" clean -fd
    AFTER=$(git -C "$INSTALL_DIR" rev-parse HEAD)
    if [ "$BEFORE" != "$AFTER" ]; then
        log_info "Обновлено: $BEFORE → $AFTER"
        CODE_UPDATED=1
    else
        log_info "Код актуален (без изменений)"
        CODE_UPDATED=0
    fi
else
    git clone https://github.com/siv237/gailery.git "$INSTALL_DIR"
    log_info "Репозиторий клонирован в $INSTALL_DIR"
    CODE_UPDATED=1
fi

# =============================================================================
# 3. Директории и .env
# =============================================================================
log_step "3. Директории и .env"

mkdir -p "$INSTALL_DIR"/{data,thumbnails,logs,models/gguf,models/insightface/models/buffalo_l}

if [ ! -f "$INSTALL_DIR/.env" ]; then
    cat > "$INSTALL_DIR/.env" << ENVEOF
# Gailery environment configuration (сгенерировано auto_install.sh)
PHOTO_SHARE_PATH=/photos

GALLERY_DATA_DIR=$INSTALL_DIR/data

GALLERY_THUMBNAILS_DIR=$INSTALL_DIR/thumbnails

GALLERY_LOGS_DIR=$INSTALL_DIR/logs

LLAMA_CPP_DIR=$LLAMA_CPP_DIR

GALLERY_VENV_PYTHON=$VENV_DIR/bin/python3

GALLERY_SERVICE_NAME=$SVC_NAME

GALLERY_MQTT_PREFIX=$SVC_NAME
ENVEOF
    log_info ".env создан"
else
    log_info ".env уже существует (не перезаписываем)"
fi

# Гибридный режим (только no-GPU): если задан AUTO_OLLAMA_URL — уходим на удалённый Ollama
if [ "$HAS_GPU" -eq 0 ] && [ -n "${AUTO_OLLAMA_URL:-}" ]; then
    log_info "Задан AUTO_OLLAMA_URL=$AUTO_OLLAMA_URL — переключаем на Ollama (гибрид)."
    grep -q '^OLLAMA_MODE=' "$INSTALL_DIR/.env" || echo 'OLLAMA_MODE=ollama' >> "$INSTALL_DIR/.env"
    grep -q '^OLLAMA_BASE_URL=' "$INSTALL_DIR/.env" || echo "OLLAMA_BASE_URL=${AUTO_OLLAMA_URL}" >> "$INSTALL_DIR/.env"
    sed -i 's/^OLLAMA_MODE=.*/OLLAMA_MODE=ollama/' "$INSTALL_DIR/.env"
    sed -i "s|^OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=${AUTO_OLLAMA_URL}|" "$INSTALL_DIR/.env"
fi

# =============================================================================
# 4. Python venv и зависимости (ВЕТВЛЕНИЕ по GPU)
# =============================================================================
log_step "4. Python venv и зависимости (режим: $([ "$HAS_GPU" -eq 1 ] && echo GPU || echo CPU))"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

if python3 -c "import torch, fastapi, lancedb, insightface, onnxruntime, paho.mqtt, psutil, xxhash, cv2, rawpy, requests" 2>/dev/null; then
    log_info "Все Python-зависимости установлены"
else
    log_info "Установка недостающих Python-зависимостей..."
    pip install --upgrade pip wheel setuptools

    if [ "$HAS_GPU" -eq 1 ]; then
        log_info "Установка PyTorch с CUDA 12.4..."
        pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
    else
        log_info "Установка PyTorch (CPU build из PyPI)..."
        pip install torch
    fi

    log_info "Установка requirements.txt (numpy<2)..."
    pip install "numpy<2.0"

    # Вырезаем torch и onnxruntime* — ставим отдельно в зависимости от режима
    grep -viE '^torch|^onnxruntime' "$INSTALL_DIR/requirements.txt" > /tmp/gailery-req-notorch.txt
    echo "numpy<2.0" > /tmp/gailery-constraints.txt
    pip install -r /tmp/gailery-req-notorch.txt -c /tmp/gailery-constraints.txt
    rm -f /tmp/gailery-req-notorch.txt /tmp/gailery-constraints.txt

    if [ "$HAS_GPU" -eq 1 ]; then
        log_info "Установка onnxruntime-gpu==1.18.0..."
        pip install onnxruntime-gpu==1.18.0
    else
        log_info "Установка onnxruntime (CPU)..."
        pip install onnxruntime
    fi
fi

log_info "Проверка torch CUDA: $(python3 -c "import torch; print(torch.__version__, 'CUDA:', torch.cuda.is_available())" 2>/dev/null || echo 'torch недоступен')"
log_info "Проверка onnxruntime: $(python3 -c "import onnxruntime; print(onnxruntime.get_available_providers())" 2>/dev/null || echo 'onnxruntime недоступен')"

deactivate

# =============================================================================
# 5. CUDA Toolkit (ТОЛЬКО при GPU)
# =============================================================================
if [ "$HAS_GPU" -eq 1 ]; then
    log_step "5. CUDA Toolkit из репозитория NVIDIA"
    if command -v /usr/local/cuda-12.6/bin/nvcc &>/dev/null; then
        log_info "CUDA Toolkit 12.6 уже установлен"
    else
        log_info "Добавление репозитория NVIDIA..."
        wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb \
            -O /tmp/cuda-keyring_1.1-1_all.deb
        dpkg -i /tmp/cuda-keyring_1.1-1_all.deb
        apt-get update -qq
        dpkg --remove --force-remove-reinstreq \
            libcuinj64-12.0 libnvidia-ml-dev nvidia-cuda-dev nvidia-cuda-toolkit \
            nvidia-profiler nvidia-visual-profiler nsight-systems nsight-systems-target \
            2>/dev/null || true
        log_info "Установка cuda-toolkit-12-6 (это долго, ~3GB)..."
        DEBIAN_FRONTEND=noninteractive apt-get install -y cuda-toolkit-12-6
        log_info "CUDA Toolkit 12.6 установлен: $(/usr/local/cuda-12.6/bin/nvcc --version | grep release)"
    fi
else
    log_step "5. CUDA Toolkit — ПРОПУЩЕНО (CPU-режим)"
fi

# =============================================================================
# 6. Сборка llama.cpp (GPU: с CUDA / CPU: без CUDA)
# =============================================================================
log_step "6. Сборка llama.cpp ($([ "$HAS_GPU" -eq 1 ] && echo 'WITH CUDA' || echo 'CPU-only'))"

if [ -x "$LLAMA_CPP_DIR/build/bin/llama-server" ]; then
    LLAMA_BRANCH=$(git -C "$LLAMA_CPP_DIR" symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "master")
    LLAMA_BEFORE=$(git -C "$LLAMA_CPP_DIR" rev-parse HEAD 2>/dev/null || echo "")
    git -C "$LLAMA_CPP_DIR" fetch origin 2>/dev/null || true
    LLAMA_REMOTE=$(git -C "$LLAMA_CPP_DIR" rev-parse "origin/$LLAMA_BRANCH" 2>/dev/null || echo "")
    if [ -n "$LLAMA_BEFORE" ] && [ -n "$LLAMA_REMOTE" ] && [ "$LLAMA_BEFORE" != "$LLAMA_REMOTE" ]; then
        log_info "llama.cpp обновился — пересборка..."
        git -C "$LLAMA_CPP_DIR" reset --hard "origin/$LLAMA_BRANCH"
        if [ "$HAS_GPU" -eq 1 ]; then
            cmake -B "$LLAMA_CPP_DIR/build" -S "$LLAMA_CPP_DIR" \
                -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH" \
                -DCMAKE_C_COMPILER=gcc-12 -DCMAKE_CXX_COMPILER=g++-12 \
                -DCMAKE_CUDA_HOST_COMPILER=g++-12 -DCMAKE_PREFIX_PATH=/usr/local/cuda-12.6
        else
            cmake -B "$LLAMA_CPP_DIR/build" -S "$LLAMA_CPP_DIR" \
                -DCMAKE_C_COMPILER=gcc-12 -DCMAKE_CXX_COMPILER=g++-12
        fi
        cmake --build "$LLAMA_CPP_DIR/build" --config Release -j"$(nproc)"
        log_info "llama-server пересобран"
    else
        log_info "llama-server уже собран и не обновлялся"
    fi
else
    if [ ! -d "$LLAMA_CPP_DIR/.git" ]; then
        git clone https://github.com/ggml-org/llama.cpp.git "$LLAMA_CPP_DIR"
    fi
    if [ "$HAS_GPU" -eq 1 ]; then
        log_info "Конфигурация cmake (CUDA arch=$CUDA_ARCH, GCC-12)..."
        cmake -B "$LLAMA_CPP_DIR/build" -S "$LLAMA_CPP_DIR" \
            -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH" \
            -DCMAKE_C_COMPILER=gcc-12 -DCMAKE_CXX_COMPILER=g++-12 \
            -DCMAKE_CUDA_HOST_COMPILER=g++-12 -DCMAKE_PREFIX_PATH=/usr/local/cuda-12.6
    else
        log_info "Конфигурация cmake (CPU-only, GCC-12)..."
        cmake -B "$LLAMA_CPP_DIR/build" -S "$LLAMA_CPP_DIR" \
            -DCMAKE_C_COMPILER=gcc-12 -DCMAKE_CXX_COMPILER=g++-12
    fi
    log_info "Сборка llama.cpp (это долго)..."
    cmake --build "$LLAMA_CPP_DIR/build" --config Release -j"$(nproc)"
    log_info "llama-server собран: $($LLAMA_CPP_DIR/build/bin/llama-server --version 2>&1 | head -1)"
fi

# =============================================================================
# 6b. llama-cpp-python (GPU: с CUDA / CPU: без CUDA)
# =============================================================================
source "$INSTALL_DIR/venv/bin/activate"

if ! python3 -c "import llama_cpp" 2>/dev/null; then
    if [ "$HAS_GPU" -eq 1 ]; then
        log_info "Сборка llama-cpp-python с CUDA..."
        CMAKE_ARGS="-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=$CUDA_ARCH -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.6/bin/nvcc -DCMAKE_PREFIX_PATH=/usr/local/cuda-12.6" \
            pip install llama-cpp-python --no-cache-dir
    else
        log_info "Сборка llama-cpp-python (CPU-only)..."
        CMAKE_ARGS="-DGGML_CUDA=OFF" pip install llama-cpp-python --no-cache-dir
    fi
else
    log_info "llama-cpp-python уже установлен"
fi

deactivate

# =============================================================================
# 7. Скачивание GGUF моделей (одинаково для GPU и CPU)
# =============================================================================
log_step "7. Скачивание GGUF моделей"

mkdir -p "$GGUF_DIR"

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

if [ ! -f "$GGUF_DIR/Qwen3-Embedding-0.6B-Q8_0.gguf" ]; then
    ln -sf "$GGUF_DIR/Qwen3-Embedding-0.6B-F16.gguf" "$GGUF_DIR/Qwen3-Embedding-0.6B-Q8_0.gguf"
    log_info "Создан симлинк Q8_0 → F16 (embed.py ожидает Q8_0)"
fi

INSIGHTFACE_DIR="$INSTALL_DIR/models/insightface/models/buffalo_l"
if [ ! -d "$INSIGHTFACE_DIR" ] || [ ! -f "$INSIGHTFACE_DIR/det_10g.onnx" ]; then
    log_info "Скачивание InsightFace buffalo_l..."
    mkdir -p "$INSIGHTFACE_DIR"
    wget -q "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip" \
        -O /tmp/buffalo_l.zip
    unzip -o /tmp/buffalo_l.zip -d "$INSIGHTFACE_DIR"
    rm -f /tmp/buffalo_l.zip
    mkdir -p "$HOME/.insightface/models/buffalo_l"
    cp "$INSIGHTFACE_DIR"/*.onnx "$HOME/.insightface/models/buffalo_l/"
else
    log_info "InsightFace buffalo_l уже есть"
fi

# =============================================================================
# 8. cuDNN (ТОЛЬКО при GPU)
# =============================================================================
if [ "$HAS_GPU" -eq 1 ]; then
    log_step "8. cuDNN: 9 для torch + 8 для onnxruntime (Pascal)"
    if [ -f /etc/ld.so.conf.d/gailery-cudnn.conf ]; then
        log_info "ldconfig пути cuDNN уже настроены"
    else
        source "$VENV_DIR/bin/activate"
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
                echo "/usr/local/cudnn8" >> /etc/ld.so.conf.d/gailery-cudnn.conf
                log_info "cuDNN 8 .so-файлы установлены в /usr/local/cudnn8"
            fi
        else
            log_info "Не Pascal — cuDNN 8 не нужен"
        fi
        ldconfig
        deactivate
    fi
else
    log_step "8. cuDNN — ПРОПУЩЕНО (CPU-режим)"
fi

# =============================================================================
# 9. Mosquitto (нужен для GPU-арбитража; в CPU-режиме безвреден)
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
# 10. Systemd сервисы (идентично для обоих режимов)
# =============================================================================
log_step "10. Systemd сервисы"

GAILERY_SERVICE="[Unit]
Description=Gailery Photo Gallery API
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
EnvironmentFile=$INSTALL_DIR/.env
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR/src
Environment=\"PATH=$VENV_DIR/bin:/usr/bin:/bin\"
Environment=\"PYTHONPATH=$INSTALL_DIR/src\"
ExecStart=$VENV_DIR/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 30 --limit-concurrency 20 --proxy-headers --forwarded-allow-ips=\"*\"
LimitNOFILE=524288
Restart=always
RestartSec=10
TimeoutStopSec=10
KillSignal=SIGINT
StandardOutput=append:$INSTALL_DIR/logs/gailery.log
StandardError=append:$INSTALL_DIR/logs/gailery-error.log

[Install]
WantedBy=multi-user.target"

if [ ! -f "/etc/systemd/system/${SVC_NAME}.service" ] || ! echo "$GAILERY_SERVICE" | diff -q - "/etc/systemd/system/${SVC_NAME}.service" >/dev/null 2>&1; then
    echo "$GAILERY_SERVICE" > "/etc/systemd/system/${SVC_NAME}.service"
    log_info "${SVC_NAME}.service обновлён"
else
    log_info "${SVC_NAME}.service актуален"
fi

PIPELINE_SERVICE="[Unit]
Description=Gailery Pipeline Worker
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
EnvironmentFile=$INSTALL_DIR/.env
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment=\"PATH=$VENV_DIR/bin:/usr/bin:/bin\"
Environment=\"PYTHONPATH=$INSTALL_DIR/src\"
ExecStart=$VENV_DIR/bin/python3 $INSTALL_DIR/pipeline.py
Restart=on-failure
RestartSec=30
StandardOutput=append:$INSTALL_DIR/logs/pipeline-stdout.log
StandardError=append:$INSTALL_DIR/logs/pipeline-error.log

[Install]
WantedBy=multi-user.target"

if [ ! -f "/etc/systemd/system/${SVC_PIPELINE}.service" ] || ! echo "$PIPELINE_SERVICE" | diff -q - "/etc/systemd/system/${SVC_PIPELINE}.service" >/dev/null 2>&1; then
    echo "$PIPELINE_SERVICE" > "/etc/systemd/system/${SVC_PIPELINE}.service"
    log_info "${SVC_PIPELINE}.service обновлён"
else
    log_info "${SVC_PIPELINE}.service актуален"
fi

WATCHDOG_SERVICE="[Unit]
Description=Gailery Pipeline Watchdog
After=network.target mosquitto.service
Wants=mosquitto.service

[Service]
EnvironmentFile=$INSTALL_DIR/.env
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment=\"PATH=$VENV_DIR/bin:/usr/bin:/bin\"
Environment=\"PYTHONPATH=$INSTALL_DIR/src\"
ExecStart=$VENV_DIR/bin/python3 $INSTALL_DIR/watchdog.py
Restart=on-failure
RestartSec=30
StandardOutput=append:$INSTALL_DIR/logs/watchdog.log
StandardError=append:$INSTALL_DIR/logs/watchdog-error.log

[Install]
WantedBy=multi-user.target"

if [ ! -f "/etc/systemd/system/${SVC_WATCHDOG}.service" ] || ! echo "$WATCHDOG_SERVICE" | diff -q - "/etc/systemd/system/${SVC_WATCHDOG}.service" >/dev/null 2>&1; then
    echo "$WATCHDOG_SERVICE" > "/etc/systemd/system/${SVC_WATCHDOG}.service"
    log_info "${SVC_WATCHDOG}.service обновлён"
else
    log_info "${SVC_WATCHDOG}.service актуален"
fi

systemctl daemon-reload
systemctl enable "$SVC_NAME" "$SVC_PIPELINE" "$SVC_WATCHDOG"
log_info "Systemd сервисы созданы и включены ($SVC_NAME, $SVC_PIPELINE, $SVC_WATCHDOG)"

# =============================================================================
# 11. Проверка database.py (нюанс #14)
# =============================================================================
log_step "11. Проверка database.py"
if grep -q 'or 0' "$INSTALL_DIR/src/database.py" 2>/dev/null; then
    log_info "database.py: патч SUM() NULL уже присутствует"
else
    log_warn "database.py: патч SUM() NULL отсутствует — нужен апгрейд репо"
fi

# =============================================================================
# 12. Перезапуск сервисов (при обновлении кода)
# =============================================================================
log_step "12. Перезапуск сервисов"
if [ "$CODE_UPDATED" -eq 1 ]; then
    log_info "Код обновлён — перезапускаем сервисы..."
    systemctl restart "$SVC_NAME" || true
    systemctl restart "$SVC_PIPELINE" 2>/dev/null || true
    systemctl restart "$SVC_WATCHDOG" 2>/dev/null || true
    log_info "Сервисы перезапущены"
else
    log_info "Код не обновлялся — перезапуск не нужен"
    systemctl start "$SVC_NAME" || true
fi

sleep 3

# =============================================================================
# 13. Проверка установки
# =============================================================================
log_step "13. Проверка установки"

echo ""
echo "--- GPU / режим ---"
if [ "$HAS_GPU" -eq 1 ]; then
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null || echo "nvidia-smi недоступен"
else
    echo "РЕЖИМ: CPU-ONLY (nvidia-smi отсутствует). Локальные AI-задачи пойдут на процессор."
fi

echo ""
echo "--- Python / CUDA ---"
source "$VENV_DIR/bin/activate"
python3 -c "import torch; print(f'torch {torch.__version__} CUDA: {torch.cuda.is_available()}')" 2>/dev/null || echo "torch проверка не удалась"
python3 -c "import onnxruntime; print(f'onnxruntime providers: {onnxruntime.get_available_providers()}')" 2>/dev/null || echo "onnxruntime проверка не удалась"
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
systemctl is-enabled "$SVC_NAME" 2>/dev/null || true
systemctl is-active "$SVC_NAME" 2>/dev/null || true

# =============================================================================
# Итог
# =============================================================================
echo ""
echo "=========================================="
if [ "$HAS_GPU" -eq 1 ]; then
    log_info "Установка завершена в GPU-режиме!"
else
    log_info "Установка завершена в CPU-режиме (без локальной GPU)!"
fi
echo "=========================================="
echo ""
echo "Галерея:       http://$(hostname -I 2>/dev/null | awk '{print $1}'):8000/gallery"
echo "API статус:    curl http://localhost:8000/api/status"
echo "Логи:          tail -f $INSTALL_DIR/logs/gailery.log"
echo ""
if [ "$HAS_GPU" -eq 0 ]; then
    echo "ВНИМАНИЕ: локальной видеокарты нет. Описание/индексация фото пойдут на CPU и будут"
    echo "медленными (по замерам ~7-12x медленнее GPU; весь архив — дни, не часы)."
    echo "Чтобы ускорить — запустите с AUTO_OLLAMA_URL=<адрес удалённого Ollama с GPU>,"
    echo "тогда AI-задачи уйдут на удалённый сервер:  AUTO_OLLAMA_URL=http://host:11434 bash auto_install.sh"
fi
echo ""
echo "Следующие шаги:"
echo "  1. Укажите путь к фото в .env: PHOTO_SHARE_PATH=/mnt/photos"
echo "  2. Добавьте корень сканирования:"
echo "     source $VENV_DIR/bin/activate && export PYTHONPATH=$INSTALL_DIR/src"
echo "     python scan_catalog.py --add /mnt/photos"
echo "  3. Запустите первый проход:"
echo "     python pipeline.py"
echo "  4. Или включите автопайплайн:"
echo "     systemctl enable --now $SVC_PIPELINE"
echo "     systemctl enable --now $SVC_WATCHDOG"
