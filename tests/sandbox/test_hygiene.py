from pathlib import Path

# Вычисляем корень репозитория динамически относительно __file__
REPO_ROOT = Path(__file__).resolve().parents[2]

ALLOWLIST = {
    # "relative/path.py": "short architect-approved reason and follow-up task id"
    "src/sandbox/bootstrap/commands/install_live_cleanup.py":
        "T317+T321: granular Render delete statuses, _resolve_render_api_key, cleanroom policy. Split to T324.",
    "src/sandbox/bootstrap/commands/install_live_telegram.py":
        "T305+T320: token source guard, Render env-var merge GET→PUT. Split to T324.",
    "src/sandbox/runtime.py":
        "T307.2+T318: webhook secret validation, Telegram sendMessage for all paths. Split to T324.",
    "tests/sandbox/bootstrap/test_cleanup_hardening.py":
        "T310+T317+T321+T322: comprehensive cleanup tests (31 tests). Split to T324.",
    "tests/sandbox/bootstrap/test_install_live_blockers.py":
        "T305+T322: env-var guard tests, nested envVar preservation. Split to T324.",
    "tests/sandbox/test_runtime.py":
        "T307.2+T318: webhook + sendMessage tests (27 tests). Split to T324.",
}

def count_lines(path: Path) -> int:
    """Подсчитывает количество строк в файле, включая комментарии и пустые строки."""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return sum(1 for _ in f)

def is_ignored(path: Path) -> bool:
    """Проверяет, должен ли файл или директория быть проигнорированы."""
    relative_parts = path.relative_to(REPO_ROOT).parts
    for part in relative_parts:
        if part == "__pycache__" or part.startswith("."):
            return True
    return False

def test_sandbox_files_line_count():
    """Проверка лимитов размера файлов для sandbox (500 строк для src, 700 строк для tests)."""
    violations = []

    # 1. Сканирование src/sandbox
    src_dir = REPO_ROOT / "src" / "sandbox"
    if src_dir.exists():
        for path in src_dir.rglob("*.py"):
            if is_ignored(path):
                continue
            relative_path_str = path.relative_to(REPO_ROOT).as_posix()
            if relative_path_str in ALLOWLIST:
                continue
            line_count = count_lines(path)
            if line_count > 500:
                violations.append((relative_path_str, line_count, 500))

    # 2. Сканирование tests/sandbox
    tests_dir = REPO_ROOT / "tests" / "sandbox"
    if tests_dir.exists():
        for path in tests_dir.rglob("*.py"):
            if is_ignored(path):
                continue
            relative_path_str = path.relative_to(REPO_ROOT).as_posix()
            if relative_path_str in ALLOWLIST:
                continue
            line_count = count_lines(path)
            if line_count > 700:
                violations.append((relative_path_str, line_count, 700))

    if violations:
        # Сортируем детерминированно по пути
        violations.sort(key=lambda x: x[0])

        error_msg = ["Sandbox file hygiene policy check failed!"]
        error_msg.append("The following files exceed the maximum line count limit:")
        for rel_path, actual, limit in violations:
            error_msg.append(f"  - {rel_path}: {actual} lines (limit: {limit})")

        error_msg.append("\nGuidance:")
        error_msg.append("1. Refactor and split the file into smaller modules to satisfy the limit.")
        error_msg.append("2. Or temporarily add the file to ALLOWLIST in 'tests/sandbox/test_hygiene.py'")
        error_msg.append("   with a short architect-approved reason and follow-up task ID.")

        assert False, "\n".join(error_msg)
