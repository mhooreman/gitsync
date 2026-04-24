import dataclasses
import datetime
import enum
import functools
import os.path
import pathlib
import shutil
import subprocess  # noqa: S404
import tempfile
import typing

import click

from . import logger

if typing.TYPE_CHECKING:
    import io

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


def _rstripped_log_debug(msg: str, indent: str = "") -> None:
    s = msg.rstrip()
    if not s:
        return
    logger.debug("%s%s", indent, s)


def _run_command(
    args: tuple[str] | list[str],
    from_dir: pathlib.Path | None = None,
    out_callback: typing.Callable[[str], None] | None = None,
    *,
    check_exit_success: bool = False
) -> tuple[str, ...] | None:
    """Process an operating system command line.

    If out_callback is None, it returns the standard output and standard
    error merged together. If out_callbak is provided, it it executed
    on standard output and standard error lines as soon as they are received.

    Raises
    ------
    subprocess.CalledProcessError
        The command did not exit with status code 0 and check_exit_success
        is True

    """
    cwd = pathlib.Path.cwd() if from_dir is None else from_dir
    logger.debug("Command from %s: %s", cwd, " ".join(args))
    p = subprocess.Popen(  # noqa: S603
        args,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=cwd
    )

    ret: list[str] = []
    for line in typing.cast("io.TextIOWrapper", p.stdout):
        if out_callback is None:
            ret.append(line)
        else:
            out_callback(line)
    rc = p.wait()
    if check_exit_success and (rc != 0):
        raise subprocess.CalledProcessError(rc, args)
    if out_callback is not None:
        return None
    return tuple(ret)


def _editable_prompt(default: str) -> str:
    ret: str | None = None
    while ret is None:
        ret = click.edit(
            default,
            require_save=False  # without change, default is returned
        )
        if ret is not None:
            # Since require_save is False, it should never be None, but
            # this is not guaranteed in terms of typing.
            # Here, we strip the text if this is not None. If the resulting
            # string is empty, we set it to None
            ret = ret.strip()
            if not ret:
                ret = None
        if ret is None:
            # Here, if the message is None, we either force to have a
            # real value, or we cancel the execution.
            click.confirm(
                "Empty commit message. Fix it?", default=True, abort=True
            )
    return ret


class GitStatusLabel(enum.StrEnum):
    UNMODIFIED = "unmodified"
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    UNMERGED = "unmerged"
    UNTRACKED = "untracked"
    IGNORED = "ignored"
    UNKNOWN_MEANING = "unknown_meaning"


_GIT_STATUS_CODE_MAPPING: typing.Final[dict[str, GitStatusLabel]] = {
    "M": GitStatusLabel.MODIFIED,
    "A": GitStatusLabel.ADDED,
    "D": GitStatusLabel.DELETED,
    "R": GitStatusLabel.RENAMED,
    "C": GitStatusLabel.COPIED,
    "U": GitStatusLabel.UNMERGED,
    "?": GitStatusLabel.UNTRACKED,
    "!": GitStatusLabel.IGNORED,
    " ": GitStatusLabel.UNMODIFIED,
}


@dataclasses.dataclass(kw_only=True, frozen=True)
class GitFileStatus:
    name: str
    previous_name: str | None
    status_code: str = dataclasses.field(repr=False)
    statuses: tuple[GitStatusLabel, ...] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        def gen_status() -> typing.Generator[GitStatusLabel]:
            for c in list(self.status_code.strip()):
                yield _GIT_STATUS_CODE_MAPPING.get(
                    c, GitStatusLabel.UNKNOWN_MEANING
                )
        object.__setattr__(self, "statuses", tuple(gen_status()))

    @classmethod
    def from_gitstatus_line(cls, line: str) -> typing.Self:
        c = line[:2]
        p = line[3:].strip()
        s = " -> "
        if s in p:
            f, t = [x.strip() for x in p.split("->")]
        else:
            t = p.strip()
            f = None
        return cls(name=t, previous_name=f, status_code=c.strip())


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
    def new_branch(self) -> str:
        while True:
            default = "".join([
                __name__.rsplit(".", 1)[0],
                self.vanilla_max_mtime.strftime("%Y%m%d%H%M%S")
            ])
            ret = typing.cast(
                "str",
                click.prompt("Branch name", default=default, type=str)
            )
            if ret not in self.existing_branches.branches:
                break
            click.confirm(
                f"Branch {ret} already exists, needs to be changed. Continue?",
                default=True, abort=True
            )
        return ret

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

    @functools.cached_property
    def commit_message(self) -> str:
        lu = self.vanilla_max_mtime.isoformat()
        nm = __name__.rsplit(".", 1)[0]
        default = "\n".join([
            f"{nm} {lu}",
            "",
            f"Vanilla input: {self.vanilla_dir}",
            f"Last vanilla change: {lu}",
            "",
            "# This is the commit message that you can edit.",
            "# Everything after '#' will be removed.",
            "#",
            "# vim: filetype=gitcommit"
        ])
        msg = _editable_prompt(default)
        lines = [l.strip().split("#", 1)[0] for l in msg.split("\n")]
        while lines[0] == "":
            lines = lines[1:]
        while lines[-1] == "":
            lines = lines[:-1]
        return "\n".join(lines)

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

    def _ask_premiminary_prompts(self) -> None:
        _ = self.git_bin_path
        _ = self.rsync_bin_path
        _ = self.new_branch
        _ = self.base_branch
        _ = self.commit_message

    def _ask_confirmation(self) -> None:
        click.echo(f"Vanilla directory: {self.vanilla_dir}")
        click.echo(f"Repostory directory: {self.repository_dir}")
        click.echo(f"Branch: {self.base_branch} -> {self.new_branch}")
        click.echo(f"Last vanilla file updated on: {self.vanilla_max_mtime}")
        click.echo(f"Commit message:\n{self.commit_message}")
        click.confirm("Please confirm", default=True, abort=True)

    def _go_to_base_branch(self) -> None:
        logger.info("Checking out branch %s", self.base_branch)
        _run_command(
            ["git", "checkout", self.base_branch],
            from_dir=self.repository_dir,
            out_callback=functools.partial(_rstripped_log_debug, indent="    ")
        )

    def _create_and_checkout_new_branch(self) -> None:
        logger.info(
            "Creating and cheking out new branch %s", self.new_branch
        )
        _run_command(
            ["git", "checkout", "-b", self.new_branch],
            from_dir=self.repository_dir,
            out_callback=functools.partial(_rstripped_log_debug, indent="    ")
        )

    def _run_rsync(self) -> None:
        logger.info("Synchronizing vanilla content to repository")
        args = ["rsync", "--verbose", "--archive", "--delete"]
        for x in _RSYNC_EXCLUDE:
            args += ["--exclude", x]

        # Forcing addition of the terminal / on the vanilla, so that
        # rsync will dive into it instead of copying it
        vanilla_term_sep = str(self.vanilla_dir.resolve()) + os.path.sep
        args += [vanilla_term_sep, "."]
        _run_command(
            args, from_dir=self.repository_dir,
            out_callback=functools.partial(_rstripped_log_debug, indent="    ")
        )

    @property
    def _current_repository_files_status(self) -> tuple[GitFileStatus, ...]:
        logger.info("Extracting repository files status")
        lines = _run_command(
            ["git", "status", "--porcelain"], from_dir=self.repository_dir
        )
        if lines is None:
            msg = "Git status provided no result"
            raise ValueError(msg)
        return tuple(GitFileStatus.from_gitstatus_line(line) for line in lines)

    def _confirm_changed_files(self) -> bool:
        def gen_msg() -> typing.Generator[str]:
            yield "Files status:"
            for f in self._current_repository_files_status:
                yield f"    - {f}"

        logger.info("Asking confirmation for changed files")
        click.echo("\n".join(gen_msg()))
        return click.confirm(
            "Continue (if no, edit .gitignore)", default=True, abort=False
        )

    def _edit_gitignore(self) -> None:
        gitignore_path = self.repository_dir.joinpath(".gitignore")
        logger.info("Editing %s", gitignore_path)
        click.confirm("Edit .gitignore (or exit)", default=True, abort=True)
        try:
            default = gitignore_path.read_text()
        except FileNotFoundError:
            default = ""
        gitignore_path.write_text(_editable_prompt(default))

    def _add_and_commit(self) -> None:
        logger.info("Staging and comitting changes")
        f = functools.partial(
            _run_command,
            from_dir=self.repository_dir,
            out_callback=functools.partial(_rstripped_log_debug, indent="    ")
        )
        f(["git", "add", "--all"])
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt"
        ) as tmpf:
            tmpf.write(self.commit_message)
            tmpf.flush()
            f(["git", "commit", "-F", tmpf.name])

    def __call__(self) -> None:
        self._ask_premiminary_prompts()
        self._ask_confirmation()
        self._go_to_base_branch()
        self._create_and_checkout_new_branch()
        self._run_rsync()
        while self._confirm_changed_files() is False:
            self._edit_gitignore()
        self._add_and_commit()
