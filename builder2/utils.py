import math
import re


def replace_non_alphanumeric(string, replace):
    return re.sub("[^\\da-zA-Z]+", replace, string) if string else string


def get_command_timeout(reference_timeout, timeout_multiplier):
    return int(math.ceil(timeout_multiplier * reference_timeout)) if timeout_multiplier > 1.0 else reference_timeout
