import dataclasses
import pathlib

from . import logger


@dataclasses.dataclass(kw_only=True, frozen=True)
class Synchonizer:
    source_dir: pathlib.Path
    repository_dir: pathlib.Path

    def __call__(self) -> None:
        logger.info("Pushing %s to %s", self.source_dir, self.repository_dir)
        logger.fatal("TO DO")
        raise NotImplementedError
