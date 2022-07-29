import logging
import os
import subprocess
import threading
import time


class CommandRunner:
    class __LogPipe(threading.Thread):

        def __init__(self, logger):
            threading.Thread.__init__(self)
            self.daemon = False
            self.fdRead, self.fdWrite = os.pipe()
            self.pipeReader = os.fdopen(self.fdRead)
            self.start()
            self.output = ''
            self._logger = logger

        def fileno(self):
            return self.fdWrite

        def run(self):
            for line in iter(self.pipeReader.readline, ''):
                self.output = self.output + line
                if self._logger:
                    self._logger.info(line.strip('\n'))

            self.pipeReader.close()

        def close(self):
            os.close(self.fdWrite)

        def __enter__(self):
            return self

        def __exit__(self, exception_type, value, traceback):
            self.close()

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)

    def run_process(self, command_list, cwd=None, timeout=180, shell=False, silent=False):
        working_dir = os.getcwd() if not cwd else cwd
        start_time = time.time()
        try:
            with self.__LogPipe(self._logger if not silent else None) as pipe:
                process = subprocess.Popen(command_list, stdin=subprocess.DEVNULL, stdout=pipe, stderr=pipe,
                                           universal_newlines=True, shell=shell, cwd=working_dir)
                process.wait(timeout=timeout)
                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode, command_list, output=pipe.output)

                return pipe.output
        except subprocess.CalledProcessError:
            self._logger.debug("Failed to execute [%s]. Exit code non-zero.", command_list)
            raise
        except subprocess.TimeoutExpired:
            self._logger.error("Failed to execute [%s]. Timeout (%d)", command_list, timeout)
            raise
        finally:
            self._logger.debug(
                " Command '%s' took %f seconds to execute",
                command_list,
                (time.time() - start_time),
            )
