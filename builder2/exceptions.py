class BuilderException(Exception):
    def __init__(self, message, exit_code=1):
        super().__init__(message)

        self.exit_code = exit_code
        self.message = message


class BuilderValidationException(BuilderException):
    def __init__(self, message, details):
        super().__init__(message)

        self.details = details
