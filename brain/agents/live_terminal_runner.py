"""
Neura Live Terminal Runner.
Executes test commands with real-time on-screen terminal output streaming,
GPU hardware acceleration telemetry, and IPC log synchronization.
Can run inside a dedicated native Windows console window (CREATE_NEW_CONSOLE)
or inline.
"""

import os
import sys
import time
import argparse
import subprocess
import ctypes
from typing import Optional


def set_console_title(title: str):
    """Sets native Windows console window title."""
    try:
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        else:
            sys.stdout.write(f"\033]0;{title}\007")
            sys.stdout.flush()
    except Exception:
        pass


def enable_ansi_colors():
    """Enables virtual terminal processing for Windows cmd/powershell."""
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            mode.value |= 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(handle, mode)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Neura Live Terminal Test Runner")
    parser.add_argument("--cmd", required=True, help="Command string or serialized args to execute")
    parser.add_argument("--cwd", default=os.getcwd(), help="Working directory for test execution")
    parser.add_argument("--title", default="Project Test", help="Display title for window")
    parser.add_argument("--gpu", default="Default GPU", help="GPU hardware compute target info")
    parser.add_argument("--log-file", required=True, help="Path to write live log stream")
    parser.add_argument("--exit-file", required=True, help="Path to write final returncode")
    parser.add_argument("--pause-on-exit", type=int, default=4, help="Seconds to pause before window close")

    args = parser.parse_args()

    enable_ansi_colors()
    set_console_title(f"NEURA LIVE TERMINAL // {args.title} [{args.gpu}]")

    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    header_lines = [
        f"{CYAN}{BOLD}╔════════════════════════════════════════════════════════════════════════════╗{RESET}",
        f"{CYAN}{BOLD}║                     NEURA LIVE TERMINAL // PROJECT TESTER                  ║{RESET}",
        f"{CYAN}{BOLD}╠════════════════════════════════════════════════════════════════════════════╣{RESET}",
        f"{CYAN}║ {BOLD}Target    :{RESET} {args.title:<62} {CYAN}║{RESET}",
        f"{CYAN}║ {BOLD}Directory :{RESET} {args.cwd[:62]:<62} {CYAN}║{RESET}",
        f"{CYAN}║ {BOLD}Hardware  :{RESET} {GREEN}{args.gpu[:62]:<62}{RESET} {CYAN}║{RESET}",
        f"{CYAN}{BOLD}╚════════════════════════════════════════════════════════════════════════════╝{RESET}",
        f"{YELLOW}{BOLD}>> ACTIVE COMMAND:{RESET} {args.cmd}",
        f"{CYAN}>> DIRECTORY     :{RESET} {args.cwd}",
        f"{CYAN}────────────────────────────────────────────────────────────────────────────{RESET}",
        f"{CYAN}{BOLD}>> LIVE CONSOLE OUTPUT STREAM:{RESET}\n",
    ]

    header_text = "\n".join(header_lines)
    sys.stdout.write(header_text)
    sys.stdout.flush()

    # Initialize log file
    os.makedirs(os.path.dirname(os.path.abspath(args.log_file)), exist_ok=True)
    with open(args.log_file, "w", encoding="utf-8") as f:
        f.write(f">> [NEURA LIVE TERMINAL START] {args.title}\n")
        f.write(f">> Compute Device: {args.gpu}\n")
        f.write(f">> Directory: {args.cwd}\n")
        f.write(f">> Command: {args.cmd}\n\n")

    returncode = -1
    start_time = time.time()

    try:
        proc = subprocess.Popen(
            args.cmd,
            cwd=args.cwd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy()
        )

        with open(args.log_file, "a", encoding="utf-8", buffering=1) as log_fp:
            for line in proc.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log_fp.write(line)
                log_fp.flush()

        proc.wait()
        returncode = proc.returncode

    except Exception as e:
        err_msg = f"{RED}[Live Terminal Runner Error]: {e}{RESET}\n"
        sys.stdout.write(err_msg)
        sys.stdout.flush()
        with open(args.log_file, "a", encoding="utf-8") as log_fp:
            log_fp.write(f"\n[Execution Exception]: {e}\n")
        returncode = -99

    duration = round(time.time() - start_time, 2)
    status_color = GREEN if returncode == 0 else RED
    status_label = "PASSED" if returncode == 0 else f"FAILED (CODE {returncode})"

    footer = [
        f"\n{CYAN}────────────────────────────────────────────────────────────────────────────{RESET}",
        f">> {status_color}{BOLD}EXECUTION COMPLETED: {status_label}{RESET} (Duration: {duration}s)",
        f"{CYAN}────────────────────────────────────────────────────────────────────────────{RESET}\n",
    ]
    sys.stdout.write("\n".join(footer))
    sys.stdout.flush()

    with open(args.log_file, "a", encoding="utf-8") as log_fp:
        log_fp.write(f"\n>> [NEURA LIVE TERMINAL FINISHED] Exit Code: {returncode} (Duration: {duration}s)\n")

    # Write returncode to exit-file
    try:
        with open(args.exit_file, "w", encoding="utf-8") as ef:
            ef.write(str(returncode))
    except Exception:
        pass

    if args.pause_on_exit > 0:
        pause_sec = args.pause_on_exit if returncode == 0 else max(args.pause_on_exit, 6)
        sys.stdout.write(f">> Window closing in {pause_sec}s... (Press Ctrl+C or Enter to close)\n")
        sys.stdout.flush()
        try:
            time.sleep(pause_sec)
        except (KeyboardInterrupt, Exception):
            pass

    sys.exit(returncode)


if __name__ == "__main__":
    main()
