#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VENV="$(dirname "$0")/venv/bin/python3"
FLAGS="-v --tb=short -q"

usage() {
  cat <<'EOF'
═══════════════════════════════════════
  Gailery Test Runner
═══════════════════════════════════════

Запуск:
  ./run_tests.sh              # read-only тесты (живая БД, безопасно)
  ./run_tests.sh --fast       # быстрая проверка UI (после каждого изменения)
  ./run_tests.sh --write      # + write-тесты на миникопии БД
  ./run_tests.sh --ai         # + AI/GPU тесты (требует GPU)
  ./run_tests.sh --quality    # аналитика кода (структура, сложность, дубли)
  ./run_tests.sh --all        # все тесты

Ключи:
  --fast    Быстрая проверка: только test_environment + test_middleware.
            Все страницы, все API JSON, сервисы. ~10 секунд.
            Запускать после КАЖДОГО изменения.
  --write   Добавить write-тесты на миникопии реальной БД.
  --ai      Добавить AI/GPU тесты (требует GPU).
  --quality Аналитика кода: монолиты, сложность, дубли, мёртвый код.
            Не блокирует pre-commit, только отчёт + fail на критичное.
  --all     --write + --ai + --quality.
  --help    Справка.
EOF
  exit 0
}

FAST=0
WRITE=0
AI=0
QUALITY=0
POSARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fast)     FAST=1;     shift ;;
    --write)    WRITE=1;    shift ;;
    --ai)       AI=1;       shift ;;
    --quality)  QUALITY=1;  shift ;;
    --all)      WRITE=1; AI=1; QUALITY=1; shift ;;
    --help)     usage ;;
    *)          POSARGS+=("$1"); shift ;;
  esac
done

echo "═══════════════════════════════════════"
echo "  Gailery Test Runner"
echo "═══════════════════════════════════════"

if [[ $QUALITY -eq 1 && $FAST -eq 0 && $WRITE -eq 0 && $AI -eq 0 ]]; then
  TARGET="tests/test_code_quality.py"
  MARK_FILTER=""
  echo "  mode: quality (code structure analytics)"
elif [[ $FAST -eq 1 ]]; then
  TARGET="tests/test_environment.py tests/test_middleware.py"
  MARK_FILTER=""
  echo "  mode: fast (environment + middleware)"
else
  TARGET="tests/"
  EXCLUDES=""
  [[ $WRITE -eq 0 ]] && EXCLUDES="$EXCLUDES and not write"
  [[ $AI -eq 0 ]]    && EXCLUDES="$EXCLUDES and not ai and not gpu"
  [[ $QUALITY -eq 0 ]] && EXCLUDES="$EXCLUDES and not quality"
  EXCLUDES="$EXCLUDES and not destructive"
  EXCLUDES="${EXCLUDES# and }"
  [[ -n "$EXCLUDES" ]] && MARK_FILTER="-k '$EXCLUDES'" || MARK_FILTER=""
  echo "  mode: ${WRITE:+write }${AI:+ai }read-only"
fi

echo "  filter: ${MARK_FILTER:-none}"
echo ""

CMD="$VENV -m pytest $TARGET $FLAGS ${POSARGS[*]} $MARK_FILTER"

eval "$CMD"
RC=$?

echo ""
if [ $RC -eq 0 ]; then
    echo "✅ Все тесты пройдены"
else
    echo "❌ Есть падающие тесты (код $RC)"
fi
echo "═══════════════════════════════════════"

exit $RC