"""Provide the gitsync command line interface."""

import pathlib

import click

from ._core import Synchonizer


class _App:
    def __call__(self) -> None:
        pass


@click.command(name="gitsync")
@click.argument(
    "source_dir", required=True, type=click.Path(
        exists=True, file_okay=False, dir_okay=True, readable=True,
        allow_dash=False, path_type=pathlib.Path
    )
)
@click.argument(
    "repository_dir", required=True, type=click.Path(
        exists=True, file_okay=False, dir_okay=True, readable=True,
        writable=True, allow_dash=False, path_type=pathlib.Path
    )
)
def main(source_dir: pathlib.Path, repository_dir: pathlib.Path) -> None:
    """Synchronize a vanilla directory to a git repository."""
    Synchonizer(source_dir=source_dir, repository_dir=repository_dir)()


if __name__ == "__main__":
    main()
