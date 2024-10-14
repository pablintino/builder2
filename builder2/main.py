import configargparse

from builder2 import __version__
from builder2.commands import bootstrap, install, load_certificates, get, source


def __build_args_parser():
    parser = configargparse.ArgumentParser(prog="builder2")
    subparsers = parser.add_subparsers(dest="command", required=True)
    bootstrap.register(subparsers)
    install.register(subparsers)
    load_certificates.register(subparsers)
    get.register(subparsers)
    source.register(subparsers)
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def main():
    args = __build_args_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
