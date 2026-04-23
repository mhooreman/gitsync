import dataclasses
import functools
import os.path
import pathlib
import shutil
import subprocess  # noqa: S404
import typing

import click

from . import logger

_RSYNC_EXCLUDE: typing.Final[tuple[str, ...]] = (
    ".git",
    ".gitignore",
    ".gitattributes",
    ".gitmodules",
)


class NotAGitRepositoryError(OSError):
    pass


class IsAlreadyAGitRepositoryError(OSError):
    pass


@dataclasses.dataclass(kw_only=True, frozen=True)
class Synchonizer:
    vanilla_dir: pathlib.Path
    repository_dir: pathlib.Path

    def __post_init__(self) -> None:
        self._check_vanilla_dir()
        self._check_repository_dir()

    def _check_vanilla_dir(self) -> None:
        if not self.vanilla_dir.is_dir():
            raise NotADirectoryError(self.vanilla_dir)
        if self.vanilla_dir.joinpath(".git").exists():
            raise IsAlreadyAGitRepositoryError(self.vanilla_dir)

    def _check_repository_dir(self) -> None:
        if not self.repository_dir.is_dir():
            raise NotADirectoryError(self.repository_dir)
        if not self.repository_dir.joinpath(".git").exists():
            e = FileNotFoundError(self.vanilla_dir.joinpath(".git"))
            raise NotAGitRepositoryError(self.repository_dir) from e

    @staticmethod
    def _get_tool_path(name: str) -> pathlib.Path:
        tmp = shutil.which(name)
        default = None if tmp is None else pathlib.Path(tmp).resolve()
        ret = click.prompt(
            f"Location of {name}",
            default=default,
            type=click.Path(
                exists=True, file_okay=True, dir_okay=False, readable=True,
                allow_dash=False, path_type=pathlib.Path, executable=True
            )
        )
        if not isinstance(ret, pathlib.Path):
            raise TypeError(ret)
        return ret

    @functools.cached_property
    def git_bin_path(self) -> pathlib.Path:
        return self._get_tool_path("git")

    @functools.cached_property
    def rsync_bin_path(self) -> pathlib.Path:
        return self._get_tool_path("rsync")

    @staticmethod
    def _run_command(
        args: tuple[str] | list[str],
        from_dir: pathlib.Path | None = None
    ) -> None:
        cwd = pathlib.Path.cwd() if from_dir is None else from_dir
        logger.info("Command from %s: %s", cwd, " ".join(args))
        p = subprocess.Popen(  # noqa: S603
            args,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd
        )
        if typing.TYPE_CHECKING:
            if p.stdout is None:
                raise ValueError
        for line in p.stdout:
            if s := line.strip():
                logger.info("    %s", s)
        rc = p.wait()
        if rc != 0:
            raise subprocess.CalledProcessError(rc, args)

    def _run_rsync(self) -> None:
        args = [
            "rsync",
            "--verbose",
            "--archive",
            "--delete",
        ]
        for x in _RSYNC_EXCLUDE:
            args += ["--exclude", x]

        # Forcing addition of the terminal / on the vanilla, so that
        # rsync will dive into it instead of copying it
        vanilla_term_sep = str(self.vanilla_dir.resolve()) + os.path.sep
        args += [vanilla_term_sep, "."]
        self._run_command(args, from_dir=self.repository_dir)

    def _ask_premiminary_prompts(self) -> None:
        _ = self.git_bin_path
        _ = self.rsync_bin_path
        # TODO _ = self.branch_name
        # TODO _ = self.commit_message

    def __call__(self) -> None:
        logger.debug("git: %s", self.git_bin_path)
        logger.debug("rsync: %s", self.rsync_bin_path)
        self._ask_premiminary_prompts()
        logger.info("Pushing %s to %s", self.vanilla_dir, self.repository_dir)
        # TODO self._confirm_base_branch()
        # TODO self._create_branch()
        # TODO self._checkout_branch()
        self._run_rsync()
        # TODO self._check_status_and_adapt_gitignore (loop)
        # TODO self._add()
        # TODO self._commit()
        # TODO self._merge_if_required()
        raise NotImplementedError
