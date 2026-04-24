gitsync
=======

Synchronize a vanilla directory to a git repository.

This is a command line tool intended to import a "non-git controlled" directory
to a git repository.

Invocation
----------

It shall be simply invoked from the command line (start with ``gitsync --help``).

Installation
------------

As any python package. We strongly encourage using ``uv tool``.

Requirements
------------

The following command line tools shall be available:

- ``git``
- ``rsync``

Limitations
-----------

Only local repositories are supported. Upgrading remote repositories shall be
done via local slave repository.

Risks
-----

The tool synchronizes using ``rsync --delete``. This might unexpectedly delete
unwanted files. The risk is limited by the fact that it is on a separated
branch.



Author
------

Michaël Hooreman
