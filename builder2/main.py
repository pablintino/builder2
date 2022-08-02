import configargparse

from builder2.di import Container
from builder2.commands import bootstrap, install, load_certificates

parser = configargparse.ArgumentParser(prog="builder2")
subparsers = parser.add_subparsers(dest="command", required=True)


def main():
    bootstrap.register(subparsers)
    install.register(subparsers)
    install.register(subparsers)
    load_certificates.register(subparsers)
    args = parser.parse_args()

    Container.config.from_dict(args.__dict__)

    container = Container()
    container.wire(
        modules=[
            __name__,
            install.__name__,
            bootstrap.__name__,
            load_certificates.__name__,
        ]
    )

    args.func(args)


if __name__ == "__main__":
    main()
