#!/bin/bash
# ADR WSL2 Bootstrap — zero-to-repo wrapper for Win+WSL2
# Назначение: подготовить среду (uv, git, repo, deps) и запустить guided installer.
# Все live cloud mutations остаются под explicit y/N внутри wizard.

set -euo pipefail

echo "=== ADR WSL2 Bootstrap ==="
echo ""

# 1. Check OS/WSL2 context
if grep -qE "microsoft|WSL" /proc/version 2>/dev/null; then
    echo "[OK] Обнаружен WSL2."
else
    echo "⚠ Этот скрипт оптимизирован для WSL2."
    echo "  Текущая среда: $(uname -a 2>/dev/null | cut -d' ' -f1-7 || echo 'неизвестна')"
    echo "  Продолжить? [y/N]"
    read -r REPLY
    if [ "${REPLY:-}" != "y" ] && [ "${REPLY:-}" != "Y" ]; then
        echo "Отмена."
        exit 1
    fi
fi

# 2. Basic tools
echo ""
echo ">>> Проверка базовых инструментов..."

missing_tools=""
for cmd in git curl; do
    if command -v "$cmd" >/dev/null 2>&1; then
        echo "  [OK] $cmd"
    else
        echo "  [MISS] $cmd"
        missing_tools="$missing_tools $cmd"
    fi
done

if [ -n "$missing_tools" ]; then
    echo ""
    echo "  Устанавливаю отсутствующие пакеты: $missing_tools"
    sudo apt-get update -qq && sudo apt-get install -y -qq $missing_tools ca-certificates
fi

# 3. Docker Desktop integration check
echo ""
echo ">>> Проверка Docker..."
if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        echo "  [OK] Docker работает."
    else
        echo "  [WARN] Docker CLI найден, но демон не отвечает."
        if grep -qE "microsoft|WSL" /proc/version 2>/dev/null; then
            echo ""
            echo "  Возможная причина: Docker Desktop WSL integration не включена."
            echo "  Действия:"
            echo "    1. Откройте Docker Desktop в Windows"
            echo "    2. Settings → Resources → WSL Integration"
            echo "    3. Включите интеграцию для $(grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"' || echo 'Ubuntu')"
            echo "    4. Перезапустите WSL терминал"
            echo "    5. Проверьте: docker info"
        else
            echo ""
            echo "  На Linux: sudo systemctl start docker"
            echo "  Или установите Docker Engine: https://docs.docker.com/engine/install/ubuntu/"
        fi
        echo ""
        echo "  Без Docker live installer не сможет работать с Supabase."
        echo "  Dry-run preview (--dry-run) работает без Docker."
        echo "  Продолжить без Docker? [y/N]"
        read -r REPLY
        if [ "${REPLY:-}" != "y" ] && [ "${REPLY:-}" != "Y" ]; then
            echo "Отмена. Исправьте Docker и запустите скрипт снова."
            exit 1
        fi
    fi
else
    echo "  [MISS] Docker не найден."
fi

# 4. Install uv if missing
echo ""
echo ">>> Проверка uv..."
if command -v uv >/dev/null 2>&1; then
    echo "  [OK] uv: $(uv --version 2>/dev/null || echo 'версия не определена')"
else
    echo "  [MISS] uv не найден. Устанавливаю..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Reload env
    if [ -f "$HOME/.local/bin/env" ]; then
        source "$HOME/.local/bin/env"
    fi
    export PATH="$HOME/.local/bin:$PATH"
    echo "  [OK] uv установлен."
fi

# 5. Node.js check (for Supabase CLI and Render CLI)
echo ""
echo ">>> Проверка Node.js (для Supabase CLI и Render CLI)..."
if command -v node >/dev/null 2>&1; then
    echo "  [OK] Node.js: $(node --version 2>/dev/null || echo 'неизвестно')"
else
    echo "  [MISS] Node.js не найден."
    echo "  Supabase CLI и Render CLI требуют Node.js/npm."
    echo "  Установить Node.js сейчас? [y/N]"
    read -r REPLY
    if [ "${REPLY:-}" = "y" ] || [ "${REPLY:-}" = "Y" ]; then
        curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
        sudo apt-get install -y -qq nodejs
        echo "  [OK] Node.js установлен."
    else
        echo "  Пропущено. Установите Node.js самостоятельно перед запуском installer."
    fi
fi

# 6. Supabase CLI check
echo ""
echo ">>> Проверка Supabase CLI..."
if command -v supabase >/dev/null 2>&1; then
    echo "  [OK] Supabase CLI: $(supabase --version 2>/dev/null || echo 'неизвестно')"
else
    echo "  [MISS] Supabase CLI не найден."
    if command -v npm >/dev/null 2>&1; then
        echo "  Установить Supabase CLI через npm? [y/N]"
        read -r REPLY
        if [ "${REPLY:-}" = "y" ] || [ "${REPLY:-}" = "Y" ]; then
            npm install -g supabase
            echo "  [OK] Supabase CLI установлен."
        fi
    else
        echo "  Пропущено — npm не найден. Установите Supabase CLI самостоятельно."
    fi
fi

# 7. Render CLI check
echo ""
echo ">>> Проверка Render CLI..."
if command -v render >/dev/null 2>&1; then
    echo "  [OK] Render CLI обнаружен."
else
    echo "  [MISS] Render CLI не найден."
    if command -v npm >/dev/null 2>&1; then
        echo "  Установить Render CLI через npm? [y/N]"
        read -r REPLY
        if [ "${REPLY:-}" = "y" ] || [ "${REPLY:-}" = "Y" ]; then
            npm install -g @renderinc/cli
            echo "  [OK] Render CLI установлен."
        fi
    else
        echo "  Пропущено — npm не найден. Установите Render CLI самостоятельно."
    fi
fi

# 8. Clone or update ADR repo
REPO_URL="https://github.com/DiscipulusVitae/agentic-domain-runtime.git"
REPO_DIR="agentic-domain-runtime"

echo ""
echo ">>> Репозиторий ADR..."

if [ -d "$REPO_DIR" ]; then
    echo "  Найден существующий клон: $REPO_DIR"
    echo "  Обновить (git pull)? [y/N]"
    read -r REPLY
    if [ "${REPLY:-}" = "y" ] || [ "${REPLY:-}" = "Y" ]; then
        cd "$REPO_DIR"
        current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
        echo "  Текущая ветка: $current_branch"
        git fetch origin
        echo "  Обновляю..."
        git pull origin main
    else
        cd "$REPO_DIR"
        echo "  Пропущено обновление."
    fi
else
    echo "  Клонирую: $REPO_URL"
    git clone "$REPO_URL"
    cd "$REPO_DIR"
    echo "  [OK] Клонирован."
fi

# 9. Install Python dependencies
echo ""
echo ">>> Установка зависимостей (uv sync)..."
uv sync
echo "  [OK] Зависимости синхронизированы."

# 10. Done
echo ""
echo "=== Среда готова ==="
echo ""
echo "Доступные команды:"
echo "  uv run python -m src.sandbox bootstrap doctor       # проверка окружения"
echo "  uv run python -m src.sandbox bootstrap install --dry-run  # dry-run preview"
echo "  uv run python -m src.sandbox bootstrap install --yes      # live guided wizard"
echo ""
echo "Запустить live guided wizard сейчас? [y/N]"
read -r REPLY
if [ "${REPLY:-}" = "y" ] || [ "${REPLY:-}" = "Y" ]; then
    exec uv run python -m src.sandbox bootstrap install --yes
fi
