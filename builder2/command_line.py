import logging
import os
import signal
import subprocess
import threading
import time
from typing import List, Dict

from builder2 import exceptions

__logger = logging.getLogger(__file__)


class __LogPipe(threading.Thread):
    def __init__(self, logger):
        threading.Thread.__init__(self)
        self.daemon = False
        self.fdRead, self.fdWrite = os.pipe()
        self.pipeReader = os.fdopen(self.fdRead)
        self.start()
        self.output = ""
        self._logger = logger

    def fileno(self):
        return self.fdWrite

    def run(self):
        for line in iter(self.pipeReader.readline, ""):
            self.output = self.output + line
            if self._logger:
                self._logger.info(line.strip("\n"))

        self.pipeReader.close()

    def close(self):
        os.close(self.fdWrite)

    def __enter__(self):
        return self

    def __exit__(self, exception_type, value, traceback):
        self.close()


def __process_cleanup(process: subprocess.Popen, shell: bool):
    if process:
        process.terminate()
        # Shell commands may freeze the process if not
        # properly killed (on timeouts)
        if process.pid and shell:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except OSError:
                pass


def run_process(
    command_list: List[str],
    cwd: str = None,
    timeout: int = 180,
    shell: bool = False,
    silent: bool = False,
):
    working_dir = os.getcwd() if not cwd else cwd
    start_time = time.time()
    with __LogPipe(__logger if not silent else None) as pipe:
        process = None
        try:
            process = subprocess.Popen(
                command_list,
                stdin=subprocess.DEVNULL,
                stdout=pipe,
                stderr=pipe,
                universal_newlines=True,
                shell=shell,
                cwd=working_dir,
                # If shell is used attach the setsid to
                # allow group kill of the processes
                preexec_fn=os.setsid if shell else None,
            )
            process.wait(timeout=timeout)
            process.wait(timeout=timeout)
            if process.returncode != 0:
                raise subprocess.CalledProcessError(
                    process.returncode, command_list, output=pipe.output
                )

            return pipe.output
        except subprocess.CalledProcessError:
            __logger.debug("Failed to execute %s. Exit code non-zero.", command_list)
            raise
        except subprocess.TimeoutExpired:
            __logger.error("Failed to execute %s. Timeout (%d)", command_list, timeout)
            raise
        finally:
            __process_cleanup(process, shell)
            __logger.debug(
                " Command '%s' took %f seconds to execute",
                command_list,
                (time.time() - start_time),
            )


def exec_command(command: List[str], env: Dict[str, str]):
    try:
        os.execvpe(command[0], command, env)
    except OSError as err:
        # If failed to execute (command not found, no permissions, etc.) get the errno and set it as return code
        __logger.debug(
            "Program %s exited with code %d",
            command[0],
            int(err.errno),
            exc_info=err,
        )
        raise err


def check_output(
    command_list: List[str],
    timeout: int = 180,
    cwd: str = None,
) -> str:
    try:
        return subprocess.check_output(
            command_list, timeout=timeout, cwd=cwd, encoding="utf-8"
        )
    except subprocess.CalledProcessError as err:
        __logger.debug("Failed to execute %s. Exit code non-zero.", command_list)
        raise exceptions.BuilderException(
            f"error running command {command_list}", exit_code=err.returncode
        ) from err
