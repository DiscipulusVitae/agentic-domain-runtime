import json
import pytest
from unittest.mock import MagicMock, patch

def mock_subprocess_run_ok(args, **kwargs):
    mock_res = MagicMock()
    mock_res.returncode = 0
    cmd = args[0]
    if cmd == "uv":
        mock_res.stdout = "uv 0.11.8"
    elif cmd == "docker" and args[1] == "--version":
        mock_res.stdout = "Docker version 24.0.7"
    elif cmd == "docker" and args[1] == "info":
        mock_res.stdout = "Docker Info"
    elif cmd == "supabase":
        mock_res.stdout = "2.101.0"
    elif cmd == "render" and args[1] == "--version":
        mock_res.stdout = "render v2.18.0"
    else:
        mock_res.stdout = "mocked ok"
    return mock_res


def mock_subprocess_run_fail(args, **kwargs):
    mock_res = MagicMock()
    cmd = args[0]
    if cmd == "supabase":
        mock_res.returncode = 1
        mock_res.stderr = "supabase not found"
        mock_res.stdout = ""
    elif cmd == "docker" and args[1] == "info":
        mock_res.returncode = 1
        mock_res.stderr = "Cannot connect to the Docker daemon"
        mock_res.stdout = ""
    elif cmd == "docker" and args[1] == "--version":
        mock_res.returncode = 127
        mock_res.stderr = "docker command not found"
        mock_res.stdout = ""
    else:
        mock_res.returncode = 0
        mock_res.stdout = "mocked ok"
    return mock_res


def mock_subprocess_run_critical_fail(args, **kwargs):
    mock_res = MagicMock()
    cmd = args[0]
    if cmd == "uv":
        mock_res.returncode = 127
        mock_res.stderr = "uv not found"
        mock_res.stdout = ""
    else:
        mock_res.returncode = 0
        mock_res.stdout = "mocked ok"
    return mock_res


def mock_subprocess_run_render_update_notice(args, **kwargs):
    mock_res = MagicMock()
    mock_res.returncode = 0
    cmd = args[0]
    if cmd == "uv":
        mock_res.stdout = "uv 0.11.8"
    elif cmd == "docker" and args[1] == "--version":
        mock_res.stdout = "Docker version 24.0.7"
    elif cmd == "docker" and args[1] == "info":
        mock_res.stdout = "Docker Info"
    elif cmd == "supabase":
        mock_res.stdout = "2.101.0"
    elif cmd == "render" and args[1] == "--version":
        mock_res.stdout = (
            "render v2.18.0\n"
            "A newer version of the Render CLI is available.\n"
            "Please run 'npm install -g @renderinc/cli' to update."
        )
    else:
        mock_res.stdout = "mocked ok"
    return mock_res


@pytest.fixture
def patch_subprocess_run_ok():
    with patch("subprocess.run", side_effect=mock_subprocess_run_ok) as mock_run:
        yield mock_run


@pytest.fixture
def patch_subprocess_run_fail():
    with patch("subprocess.run", side_effect=mock_subprocess_run_fail) as mock_run:
        yield mock_run


@pytest.fixture
def patch_subprocess_run_critical_fail():
    with patch("subprocess.run", side_effect=mock_subprocess_run_critical_fail) as mock_run:
        yield mock_run


@pytest.fixture
def patch_subprocess_run_render_update_notice():
    with patch("subprocess.run", side_effect=mock_subprocess_run_render_update_notice) as mock_run:
        yield mock_run
