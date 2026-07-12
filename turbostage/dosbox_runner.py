import os
import subprocess
import tempfile


def run_dosbox(
    dosbox_path: str,
    executable_path: str,
    *,
    base_conf: str | None = None,
    full_screen: bool = False,
    cpu_cycles: int = 0,
    mt32_roms_path: str | None = None,
    config_content: str | None = None,
) -> int:
    """Run DOSBox Staging with a given executable.

    Args:
        dosbox_path: Path to the dosbox binary.
        executable_path: Full path to the executable to run.
        base_conf: Optional path to a base dosbox-staging.conf.
        full_screen: Launch in fullscreen mode.
        cpu_cycles: CPU cycles (0 = auto/default).
        mt32_roms_path: Path to MT-32 ROM directory.
        config_content: Raw DOSBox config text to append.

    Returns:
        Exit code from the DOSBox process.
    """
    command = [dosbox_path, "--noprimaryconf"]
    if base_conf:
        command.extend(["--conf", base_conf])
    if full_screen:
        command.append("--fullscreen")

    extra_config = _build_extra_config(cpu_cycles, mt32_roms_path, config_content)
    if extra_config:
        with tempfile.NamedTemporaryFile(suffix=".conf", mode="wt", delete=False) as f:
            f.write(extra_config)
            f.flush()
            command.extend(["--conf", f.name])

    command.append(executable_path)
    return subprocess.run(command, check=True).returncode


def _build_extra_config(
    cpu_cycles: int = 0,
    mt32_roms_path: str | None = None,
    config_content: str | None = None,
) -> str:
    """Build extra DOSBox config sections from optional overrides."""
    parts = []
    if config_content:
        parts.append(config_content)
    if cpu_cycles > 0:
        parts.append(f"\n[cpu]\ncpu_cycles = {cpu_cycles}\ncpu_cycles_protected = {cpu_cycles}\n")
    if mt32_roms_path:
        parts.append(f"\n[mt32]\nromdir = {mt32_roms_path}\n")
    return "\n".join(parts)
