"""autotune entry point."""

from .preflight import check


def main() -> None:
    check()
    from .app import run
    run()


if __name__ == "__main__":
    main()
