#!/bin/bash
# ADR WSL2 Bootstrap — zero-to-repo wrapper for Win+WSL2
# Назначение: подготовить среду (uv, git, repo, deps) и запустить guided installer.
# Все live cloud mutations остаются под explicit y/N внутри wizard.
#
# Запуск: bash scripts/adr_bootstrap_wsl2.sh
# НЕ использовать sudo. Для apt-get скрипт сам запросит sudo.

set -euo pipefail

echo "=== ADR WSL2 Bootstrap ==="
echo ""

# 0. Root guard
if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ]; then
    echo "ОШИБКА: скрипт запущен от root через sudo."
    echo "  Запустите от обычного пользователя (без sudo):"
    echo "    bash scripts/adr_bootstrap_wsl2.sh"
    echo "  Для apt-get скрипт сам запросит пароль при необходимости."
    exit 1
fi

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
UV_FOUND=false
if command -v uv >/dev/null 2>&1; then
    UV_FOUND=true
    echo "  [OK] uv: $(uv --version 2>/dev/null || echo 'версия не определена')"
elif [ -x "$HOME/.local/bin/uv" ]; then
    UV_FOUND=true
    export PATH="$HOME/.local/bin:$PATH"
    echo "  [OK] uv: $($HOME/.local/bin/uv --version 2>/dev/null || echo 'найден в ~/.local/bin')"
fi

if [ "$UV_FOUND" != "true" ]; then
    echo "  [MISS] uv не найден. Устанавливаю..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    if [ -f "$HOME/.local/bin/env" ]; then
        source "$HOME/.local/bin/env"
    fi
    export PATH="$HOME/.local/bin:$PATH"
    echo "  [OK] uv установлен."
fi

# 5. Node.js check (for Supabase CLI)
echo ""
echo ">>> Проверка Node.js (для Supabase CLI)..."
if command -v node >/dev/null 2>&1; then
    echo "  [OK] Node.js: $(node --version 2>/dev/null || echo 'неизвестно')"
else
    echo "  [MISS] Node.js не найден."
    echo "  Supabase CLI требует Node.js/npm."
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
    echo "  [OK] Render CLI: $(render --version 2>/dev/null || echo 'обнаружен')"
else
    echo "  [MISS] Render CLI не найден."
    echo "  Render CLI распространяется как бинарник (не npm-пакет)."
    echo "  Установить сейчас? [y/N]"
    read -r REPLY
    if [ "${REPLY:-}" = "y" ] || [ "${REPLY:-}" = "Y" ]; then
        INSTALL_DIR="${HOME}/.local/bin"
        mkdir -p "$INSTALL_DIR"
        TMP_DIR=$(mktemp -d)
        trap 'rm -rf "$TMP_DIR"' EXIT
        echo "  Скачиваю Render CLI..."
        RENDER_VER=$(curl -sL "https://api.github.com/repos/render-oss/cli/releases/latest" | grep -o '"tag_name":[[:space:]]*"[^"]*"' | head -1 | cut -d'"' -f4)
        if [ -z "$RENDER_VER" ]; then
            RENDER_VER="v2.20.0"
        fi
        ZIP_URL="https://github.com/render-oss/cli/releases/download/${RENDER_VER}/cli_${RENDER_VER#v}_linux_amd64.zip"
        if curl -fsSL -o "$TMP_DIR/render.zip" "$ZIP_URL"; then
            unzip -o "$TMP_DIR/render.zip" -d "$TMP_DIR" >/dev/null 2>&1
            RENDER_BIN=$(ls "$TMP_DIR"/cli_v* 2>/dev/null | head -1)
            if [ -n "$RENDER_BIN" ] && [ -f "$RENDER_BIN" ]; then
                mv "$RENDER_BIN" "$INSTALL_DIR/render"
                chmod +x "$INSTALL_DIR/render"
                echo "  [OK] Render CLI ${RENDER_VER} установлен в $INSTALL_DIR/render"
                if ! echo "$PATH" | grep -q "$INSTALL_DIR"; then
                    echo "  Добавьте в ~/.bashrc: export PATH=\"\$HOME/.local/bin:\$PATH\""
                fi
            else
                echo "  Ошибка: не удалось найти бинарник в архиве."
                echo "  Установите вручную: https://github.com/render-oss/cli/releases"
            fi
        else
            echo "  Ошибка: не удалось скачать Render CLI."
            echo "  Установите вручную: https://github.com/render-oss/cli/releases"
        fi
    else
        echo "  Пропущено. Установите вручную: https://github.com/render-oss/cli/releases"
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
