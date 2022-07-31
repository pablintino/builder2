import logging


def configure(level="INFO"):
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)8s] --- %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    logger = logging.getLogger()
    logger.setLevel(level)

    console = logging.StreamHandler()
    logger.addHandler(console)
    console.setFormatter(formatter)
    console.setLevel(level)
