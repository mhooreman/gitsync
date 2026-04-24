"""Logging features."""

import logging
import sys
import typing

import termcolor


class _ConsoleFormatter(logging.Formatter):
    _LEVEL_FORMAT: typing.Final[dict[int, dict[str, str | list[str]]]] = {
        logging.DEBUG: {"color": "cyan"},
        logging.INFO: {"color": "white"},
        logging.WARNING: {"color": "yellow"},
        logging.ERROR: {"color": "red"},
        logging.CRITICAL: {"color": "red", "attrs": ["reverse"]},
    }

    def __init__(self) -> None:
        self._format_cache: dict[int, str] = {}
        super().__init__()

    def _get_format(self, levelno: int) -> str:
        if levelno in self._format_cache:
            return self._format_cache[levelno]
        lfmt = self._LEVEL_FORMAT[levelno]
        tm = termcolor.colored(text="%(asctime)s", color="green")
        lvl = termcolor.colored(
            text="%(levelname)-8s", **lfmt  # type: ignore[arg-type]
        )
        msg = termcolor.colored(
            text="%(message)s", **lfmt  # type: ignore[arg-type]
        )
        ret = f"{tm} | {lvl} | {msg}"
        self._format_cache[levelno] = ret
        return ret

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self._get_format(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


_CONSOLE_IO: typing.Final[typing.TextIO] = sys.stderr


class _LoggerBuilder:
    _instance: typing.ClassVar[typing.Self | None] = None

    def __new__(cls) -> typing.Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def _console_formatter(self) -> _ConsoleFormatter:
        return _ConsoleFormatter()

    @property
    def _console_handler(self) -> logging.Handler:
        ret = logging.StreamHandler(_CONSOLE_IO)
        ret.setLevel(logging.DEBUG)
        ret.setFormatter(self._console_formatter)
        return ret

    @property
    def logger(self) -> logging.Logger:
        ret = logging.getLogger(__name__.split(".", 1)[0])
        ret.setLevel(logging.DEBUG)
        if not any(
            isinstance(h, logging.StreamHandler) for h in ret.handlers
        ):
            ret.addHandler(self._console_handler)
        logging.captureWarnings(capture=True)
        return ret


logger: typing.Final[logging.Logger] = _LoggerBuilder().logger
