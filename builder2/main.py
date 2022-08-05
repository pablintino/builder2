import configargparse

from builder2.di import Container
from builder2 import __version__
from builder2.commands import bootstrap, install, load_certificates, get


def __build_args_parser():
    parser = configargparse.ArgumentParser(prog="builder2")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap.register(subparsers)
    install.register(subparsers)
    install.register(subparsers)
    load_certificates.register(subparsers)
    get.register(subparsers)
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def main():
    args = __build_args_parser().parse_args()

    Container.config.from_dict(args.__dict__)

    container = Container()
    container.wire(
        modules=[
            __name__,
            install.__name__,
            bootstrap.__name__,
            load_certificates.__name__,
            get.__name__,
        ]
    )

    args.func(args)


if __name__ == "__main__":
    main()
