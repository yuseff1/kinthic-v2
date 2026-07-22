"""
silex_core/ops/service.py

Install, uninstall, start, and stop the Kinthic daemon as a persistent
OS-level service.

- Linux   → systemd user service  (~/.config/systemd/user/kinthic.service)
- macOS   → launchd LaunchAgent   (~/Library/LaunchAgents/com.kinthic.daemon.plist)
- Windows → falls back to helpful error message (use Task Scheduler manually)
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _python() -> str:
    """Absolute path to the running Python interpreter."""
    return sys.executable


def _cli_path() -> Path:
    """Absolute path to the kinthic CLI entry-point script."""
    # Prefer the installed console_scripts shim on PATH.
    which = shutil.which("kinthic")
    if which:
        return Path(which)
    # Fall back to running scripts/cli.py directly from the repo checkout.
    from silex_core.utils.config import PROJECT_ROOT
    return PROJECT_ROOT / "scripts" / "cli.py"


def _kinthic_home() -> Path:
    from silex_core.utils.config import KINTHIC_HOME
    return KINTHIC_HOME


def _daemon_log() -> Path:
    return _kinthic_home() / "logs" / "daemon.log"


def _venv_bin() -> str:
    """Return the bin/ directory of the active venv (if any), else empty string."""
    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        return str(Path(sys.prefix) / "bin")
    return ""


# ---------------------------------------------------------------------------
# Linux — systemd user service
# ---------------------------------------------------------------------------

def _systemd_unit_path() -> Path:
    """~/.config/systemd/user/kinthic.service"""
    config_home = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "systemd" / "user" / "kinthic.service"


def _systemd_unit_content() -> str:
    python = _python()
    cli = _cli_path()
    home = str(Path.home())
    daemon_log = str(_daemon_log())
    venv_bin = _venv_bin()
    path_env = f"{venv_bin}:/usr/local/bin:/usr/bin:/bin" if venv_bin else "/usr/local/bin:/usr/bin:/bin"

    return textwrap.dedent(f"""\
        [Unit]
        Description=Kinthic AI Agent Daemon
        Documentation=https://kinthic.com
        After=network-online.target
        Wants=network-online.target

        [Service]
        Type=simple
        WorkingDirectory={home}
        ExecStart={cli} daemon run
        Restart=on-failure
        RestartSec=5s
        StandardOutput=append:{daemon_log}
        StandardError=append:{daemon_log}

        Environment=HOME={home}
        Environment=PATH={path_env}

        [Install]
        WantedBy=default.target
    """)


def _systemd_install(force: bool = False) -> tuple[bool, str]:
    unit_path = _systemd_unit_path()
    if unit_path.exists() and not force:
        return False, (
            f"Service unit already exists at {unit_path}.\n"
            "Run with --force to overwrite."
        )

    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(_systemd_unit_content(), encoding="utf-8")

    # Enable lingering so user services survive logout on servers.
    user = os.getenv("USER", "")
    if user:
        subprocess.run(
            ["loginctl", "enable-linger", user],
            capture_output=True,
        )

    # Reload systemd and enable the unit.
    env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True, env=env,
    )
    result = subprocess.run(
        ["systemctl", "--user", "enable", "kinthic.service"],
        capture_output=True, env=env,
    )
    if result.returncode != 0:
        return False, (
            f"Installed unit at {unit_path} but could not enable it:\n"
            f"{result.stderr.decode().strip()}\n"
            "Try: systemctl --user enable kinthic.service"
        )

    return True, (
        f"✓ Kinthic service installed at {unit_path}\n"
        "  Start now:  systemctl --user start kinthic.service\n"
        "  Auto-start: already enabled (starts on next login / reboot)\n"
        "  Logs:       journalctl --user -u kinthic -f\n"
        f"              or tail -f {_daemon_log()}"
    )


def _systemd_uninstall() -> tuple[bool, str]:
    unit_path = _systemd_unit_path()
    if not unit_path.exists():
        return False, "No Kinthic systemd service unit found."

    env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
    subprocess.run(
        ["systemctl", "--user", "stop", "kinthic.service"],
        capture_output=True, env=env,
    )
    subprocess.run(
        ["systemctl", "--user", "disable", "kinthic.service"],
        capture_output=True, env=env,
    )
    unit_path.unlink(missing_ok=True)
    subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True, env=env,
    )
    return True, "✓ Kinthic systemd service uninstalled."


def _systemd_is_installed() -> bool:
    return _systemd_unit_path().exists()


def _systemd_start() -> tuple[bool, str]:
    env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
    result = subprocess.run(
        ["systemctl", "--user", "start", "kinthic.service"],
        capture_output=True, env=env,
    )
    if result.returncode == 0:
        return True, "✓ Kinthic daemon started via systemd."
    return False, f"systemctl start failed: {result.stderr.decode().strip()}"


def _systemd_stop() -> tuple[bool, str]:
    env = {**os.environ, "XDG_RUNTIME_DIR": f"/run/user/{os.getuid()}"}
    result = subprocess.run(
        ["systemctl", "--user", "stop", "kinthic.service"],
        capture_output=True, env=env,
    )
    if result.returncode == 0:
        return True, "✓ Kinthic daemon stopped via systemd."
    return False, f"systemctl stop failed: {result.stderr.decode().strip()}"


# ---------------------------------------------------------------------------
# macOS — LaunchAgent plist
# ---------------------------------------------------------------------------

def _launchagent_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.kinthic.daemon.plist"


def _launchagent_plist_content() -> str:
    python = _python()
    cli = str(_cli_path())
    home = str(Path.home())
    daemon_log = str(_daemon_log())

    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
            "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>com.kinthic.daemon</string>
            <key>ProgramArguments</key>
            <array>
                <string>{cli}</string>
                <string>daemon</string>
                <string>run</string>
            </array>
            <key>EnvironmentVariables</key>
            <dict>
                <key>HOME</key>
                <string>{home}</string>
                <key>PATH</key>
                <string>/usr/local/bin:/usr/bin:/bin</string>
            </dict>
            <key>RunAtLoad</key>
            <true/>
            <key>KeepAlive</key>
            <dict>
                <key>SuccessfulExit</key>
                <false/>
            </dict>
            <key>StandardOutPath</key>
            <string>{daemon_log}</string>
            <key>StandardErrorPath</key>
            <string>{daemon_log}</string>
        </dict>
        </plist>
    """)


def _launchagent_install(force: bool = False) -> tuple[bool, str]:
    plist_path = _launchagent_plist_path()
    if plist_path.exists() and not force:
        return False, (
            f"LaunchAgent plist already exists at {plist_path}.\n"
            "Run with --force to overwrite."
        )

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(_launchagent_plist_content(), encoding="utf-8")

    result = subprocess.run(
        ["launchctl", "load", "-w", str(plist_path)],
        capture_output=True,
    )
    if result.returncode != 0:
        return False, (
            f"Installed plist at {plist_path} but launchctl load failed:\n"
            f"{result.stderr.decode().strip()}"
        )
    return True, (
        f"✓ Kinthic LaunchAgent installed at {plist_path}\n"
        "  It will start automatically on login.\n"
        f"  Logs: tail -f {_daemon_log()}"
    )


def _launchagent_uninstall() -> tuple[bool, str]:
    plist_path = _launchagent_plist_path()
    if not plist_path.exists():
        return False, "No Kinthic LaunchAgent found."
    subprocess.run(
        ["launchctl", "unload", "-w", str(plist_path)],
        capture_output=True,
    )
    plist_path.unlink(missing_ok=True)
    return True, "✓ Kinthic LaunchAgent uninstalled."


def _launchagent_is_installed() -> bool:
    return _launchagent_plist_path().exists()


def _launchagent_start() -> tuple[bool, str]:
    plist_path = _launchagent_plist_path()
    result = subprocess.run(
        ["launchctl", "load", "-w", str(plist_path)],
        capture_output=True,
    )
    if result.returncode == 0:
        return True, "✓ Kinthic LaunchAgent started."
    return False, f"launchctl load failed: {result.stderr.decode().strip()}"


def _launchagent_stop() -> tuple[bool, str]:
    plist_path = _launchagent_plist_path()
    result = subprocess.run(
        ["launchctl", "unload", str(plist_path)],
        capture_output=True,
    )
    if result.returncode == 0:
        return True, "✓ Kinthic LaunchAgent stopped."
    return False, f"launchctl unload failed: {result.stderr.decode().strip()}"


# ---------------------------------------------------------------------------
# Public API — dispatches to OS-specific backend
# ---------------------------------------------------------------------------

def _os() -> str:
    return platform.system()  # "Linux", "Darwin", "Windows"


def install_service(force: bool = False) -> tuple[bool, str]:
    """Install Kinthic as a persistent background service."""
    if _os() == "Linux":
        return _systemd_install(force)
    if _os() == "Darwin":
        return _launchagent_install(force)
    return False, (
        "Automatic service installation is not supported on Windows.\n"
        "Use Task Scheduler or run 'kinthic daemon run' in a dedicated terminal."
    )


def uninstall_service() -> tuple[bool, str]:
    """Remove the Kinthic service unit."""
    if _os() == "Linux":
        return _systemd_uninstall()
    if _os() == "Darwin":
        return _launchagent_uninstall()
    return False, "Service management is not supported on Windows."


def is_service_installed() -> bool:
    """Return True if a service unit exists on disk."""
    if _os() == "Linux":
        return _systemd_is_installed()
    if _os() == "Darwin":
        return _launchagent_is_installed()
    return False


def start_service() -> tuple[bool, str]:
    """Start the already-installed service."""
    if _os() == "Linux":
        return _systemd_start()
    if _os() == "Darwin":
        return _launchagent_start()
    return False, "Service management is not supported on Windows."


def stop_service() -> tuple[bool, str]:
    """Stop the running service without uninstalling it."""
    if _os() == "Linux":
        return _systemd_stop()
    if _os() == "Darwin":
        return _launchagent_stop()
    return False, "Service management is not supported on Windows."
