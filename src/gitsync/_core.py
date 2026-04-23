import dataclasses
import datetime
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
class ExistingBranches:
    default: str | None
    branches: tuple[str, ...]


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
        return typing.cast("pathlib.Path", ret)

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

    @functools.cached_property
    def vanilla_max_mtime(self) -> datetime.datetime:
        def path2timestamp(path: pathlib.Path) -> float:
            return path.stat().st_mtime

        def gen() -> typing.Iterator[float]:
            yield path2timestamp(self.vanilla_dir)
            for p in self.vanilla_dir.glob("**/*"):
                yield p.stat().st_mtime

        return datetime.datetime.fromtimestamp(max(gen()))  # noqa: DTZ006

    @functools.cached_property
    def new_branch_name(self) -> str:
        default = "".join([
            __name__.rsplit(".", 1)[0],
            self.vanilla_max_mtime.strftime("%Y%m%d%H%M%S")
        ])
        ret = click.prompt("Branch name", default=default, type=str)
        return typing.cast("str", ret)

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

    @functools.cached_property
    def base_branch(self) -> str:
        return typing.cast(
            "str",
            click.prompt(
                "Base branch",
                default=self.existing_branches.default,
                type=click.Choice(self.existing_branches.branches)
            )
        )

    def _ask_premiminary_prompts(self) -> None:
        _ = self.git_bin_path
        _ = self.rsync_bin_path
        _ = self.new_branch_name
        _ = self.base_branch
        # TODO _ = self.commit_message - Text editor
        click.confirm(
            f"OK to update {self.repository_dir} with {self.vanilla_dir}?",
            default=True, abort=True
        )

    @functools.cached_property
    def existing_branches(self) -> ExistingBranches:
        def gen_existing() -> typing.Generator[tuple[bool, str]]:
            lns = subprocess.run(  # noqa: S603
                [self.git_bin_path, "branch", "--all"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.repository_dir,
                check=True
            ).stdout.split("\n")
            for ln_ in lns:
                ln = ln_.strip()
                if not ln:
                    continue
                default = ln[0] == "*"
                if default:
                    ln = ln[1:]
                name = ln.strip()
                yield (default, name)

        tmp = tuple(gen_existing())
        defaults = [t[1] for t in tmp if t[0]]
        if len(defaults) != 1:
            logger.error(
                "Cannot guess current branch: %s. Setting to unknown.",
                defaults
            )
            default = None
        else:
            default = defaults[0]
        return ExistingBranches(
            default=default, branches=tuple(t[1] for t in tmp)
        )

    def __call__(self) -> None:
        self._ask_premiminary_prompts()
        logger.info(
            'Updating %s with %s using branch "%s" from "%s"',
            self.new_branch_name,
            self.base_branch
        )
        # TODO check that new branch does not exists
        # TODO self._go_to_base_branch()
        # TODO self._create_and_checkout_new_branch()
        self._run_rsync()
        # TODO self._check_status_and_adapt_gitignore (loop)
        # TODO self._add()
        # TODO self._commit()
        # TODO self._propose_to_merge()
        # TODO self._propose_to_tag()
        raise NotImplementedError
