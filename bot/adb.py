"""Testable ADB process adapter for the 0.2 infrastructure layer."""

from __future__ import annotations

import math
import os
import subprocess
from numbers import Integral, Real
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from bot.config import RuntimeConfig


Command = tuple[str, ...]
Runner = Callable[..., subprocess.CompletedProcess[str]]
Spawner = Callable[..., subprocess.Popen[bytes]]


class AdbError(RuntimeError):
    """An ADB process failed to start or returned an unsuccessful result."""

    def __init__(
        self,
        command: Command,
        *,
        reason: str = "ADB command failed",
        returncode: int | None = None,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> None:
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

        details = [reason, f"command={list(command)!r}"]
        if returncode is not None:
            details.append(f"returncode={returncode}")
        if stderr and stderr.strip():
            details.append(f"stderr={stderr.strip()!r}")
        if stdout and stdout.strip():
            details.append(f"stdout={stdout.strip()!r}")
        super().__init__("; ".join(details))


class AdbTimeoutError(AdbError):
    """An ADB process exceeded its configured timeout."""

    def __init__(
        self,
        command: Command,
        timeout: float,
        *,
        stdout: str | None = None,
        stderr: str | None = None,
    ) -> None:
        self.timeout = timeout
        super().__init__(
            command,
            reason=f"ADB command timed out after {timeout:g} seconds",
            stdout=stdout,
            stderr=stderr,
        )


class AdbClient:
    """Execute device-scoped ADB commands through a controlled subprocess call."""

    def __init__(
        self,
        adb_executable: str,
        serial: str,
        *,
        default_timeout: float = 10.0,
        runner: Runner | None = None,
        spawner: Spawner | None = None,
    ) -> None:
        self.adb_executable = _non_empty(adb_executable, "adb_executable")
        self.serial = _non_empty(serial, "serial")
        self.default_timeout = _positive_timeout(default_timeout)
        self._runner = subprocess.run if runner is None else runner
        self._spawner = subprocess.Popen if spawner is None else spawner

    @classmethod
    def from_config(
        cls,
        config: RuntimeConfig,
        *,
        default_timeout: float = 10.0,
        runner: Runner | None = None,
        spawner: Spawner | None = None,
    ) -> "AdbClient":
        """Build a client from only the ADB fields of ``RuntimeConfig``."""

        return cls(
            adb_executable=config.adb_executable,
            serial=config.device_serial,
            default_timeout=default_timeout,
            runner=runner,
            spawner=spawner,
        )

    def get_state(self, *, timeout: float | None = None) -> str:
        """Return the device state reported by ``adb get-state``."""

        return self._run("get-state", timeout=timeout).stdout.strip()

    def shell(
        self, *args: str | os.PathLike[str], timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run a non-interactive command through ``adb shell``."""

        if not args:
            raise ValueError("shell requires at least one command argument")
        return self._run(
            "shell",
            *(_non_empty(arg, "shell argument") for arg in args),
            timeout=timeout,
        )

    def spawn_shell(
        self,
        *args: str | os.PathLike[str],
        capture_output: bool = False,
    ) -> subprocess.Popen[bytes]:
        """Start a persistent ``adb shell`` process owned by the caller."""

        if not args:
            raise ValueError("spawn_shell requires at least one command argument")
        command = self._command(
            "shell", *(_non_empty(arg, "shell argument") for arg in args)
        )
        try:
            return self._spawner(
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=(subprocess.PIPE if capture_output else subprocess.DEVNULL),
                stderr=subprocess.DEVNULL,
                shell=False,
            )
        except OSError as error:
            raise AdbError(command, reason=f"Could not spawn ADB: {error}") from error

    def tap(
        self, x: int, y: int, *, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Tap an absolute pixel coordinate on the device."""

        pixel_x = _pixel_coordinate(x, "x")
        pixel_y = _pixel_coordinate(y, "y")
        return self.shell("input", "tap", str(pixel_x), str(pixel_y), timeout=timeout)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int,
        *,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Swipe between absolute pixel coordinates on the device."""

        coordinates = (
            _pixel_coordinate(x1, "x1"),
            _pixel_coordinate(y1, "y1"),
            _pixel_coordinate(x2, "x2"),
            _pixel_coordinate(y2, "y2"),
        )
        duration = _positive_integer(duration_ms, "duration_ms")
        return self.shell(
            "input",
            "swipe",
            *(str(value) for value in coordinates),
            str(duration),
            timeout=timeout,
        )

    def push(
        self,
        local_path: str | os.PathLike[str],
        remote_path: str | os.PathLike[str],
        *,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Push a local file to an explicit path on the device."""

        return self._run(
            "push",
            _non_empty(local_path, "local_path"),
            _non_empty(remote_path, "remote_path"),
            timeout=timeout,
        )

    def forward(
        self,
        local: str,
        remote: str,
        *,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Create an ADB port forwarding rule."""

        return self._run(
            "forward",
            _non_empty(local, "local endpoint"),
            _non_empty(remote, "remote endpoint"),
            timeout=timeout,
        )

    def remove_forward(
        self, local: str, *, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Remove an ADB port forwarding rule by its local endpoint."""

        return self._run(
            "forward",
            "--remove",
            _non_empty(local, "local endpoint"),
            timeout=timeout,
        )

    def list_forwards(self, *, timeout: float | None = None) -> tuple[str, ...]:
        """Return active ADB forwarding rules for lifecycle diagnostics."""

        result = self._run("forward", "--list", timeout=timeout)
        return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())

    def _run(
        self, *args: str, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        command = self._command(*args)
        effective_timeout = (
            self.default_timeout if timeout is None else _positive_timeout(timeout)
        )

        try:
            result = self._runner(
                list(command),
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise AdbTimeoutError(
                command,
                effective_timeout,
                stdout=_output_text(error.stdout),
                stderr=_output_text(error.stderr),
            ) from error
        except OSError as error:
            raise AdbError(command, reason=f"Could not execute ADB: {error}") from error

        if result.returncode != 0:
            raise AdbError(
                command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        return result

    def _command(self, *args: str) -> Command:
        return self.adb_executable, "-s", self.serial, *args


def _non_empty(value: str | os.PathLike[str], name: str) -> str:
    try:
        text = os.fspath(value)
    except TypeError as error:
        raise ValueError(f"{name} must be a non-empty path or string") from error
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{name} must be a non-empty path or string")
    return text.strip()


def _positive_timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("timeout must be a positive finite number")
    timeout = float(value)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive finite number")
    return timeout


def _pixel_coordinate(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer pixel coordinate")
    return int(value)


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


def _output_text(value: str | bytes | None) -> str | None:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
