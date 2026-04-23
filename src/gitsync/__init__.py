"""Provide the gitsync package."""

import importlib.metadata
import typing

from ._log import logger

_PKG_METADATA: typing.Final[   # noqa: RUF067
    importlib.metadata.PackageMetadata
] = importlib.metadata.metadata(
    __name__
)

__version__: typing.Final[str | None] = _PKG_METADATA.get("version")
__author__: typing.Final[str | None] = _PKG_METADATA.get("author")

__all__ = [
    "logger",
]
