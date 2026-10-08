# 1. Adopt a src/ layout with an explicit runtime state directory

- Status: accepted
- Date: 2026-10-08
- Deciders: maintainers

## Context

The service began as a loose collection of top-level Python modules imported by
bare name: `from models import db`, `from web.app import ...`. That works
only while the working directory happens to be the project root. It breaks under
a test runner that changes directory, under a packaging step, and whenever an
unrelated installed distribution happens to share a module name. The modules also
created the database and logs relative to the current working directory, which
makes a read-only container filesystem impossible.

## Decision

1. Move all importable code under `src/message_pusher/` and rewrite every local
   import to a relative one.
2. Ship the code as an installable distribution defined in `pyproject.toml`.
3. Put every mutable path under a single data directory, selected by `DATA_DIR`
   and defaulting to `<root>/var`. `paths.py` resolves it and nothing else
   computes a path at import time.
4. Configure logging before the application object is constructed, so no early
   message escapes the configured handlers.

## Consequences

**Positive**

- `pip install -e .` makes the code importable from anywhere, so tests no
  longer depend on the working directory.
- Name collisions with the standard library or third-party distributions become
  structurally impossible.
- The container can run with a read-only root filesystem; only the mounted data
  volume is writable.
- Relative imports make internal coupling visible in review. A cross-package
  import is now a deliberate, visible act rather than an accident.

**Negative**

- Tooling that relied on top-level module names (for example `python -m web.app`)
  must be updated. `wsgi.py` is kept as a shim to soften this.
- Every module moved in one large change, which makes that commit hard to
  bisect. Mitigated by migrating the test suite in the same change.

## Alternatives considered

- **Keep flat modules and add `sys.path` manipulation.** Cheap, but it hides
  the real problem and breaks as soon as two such projects share an environment.
- **Namespace packages without a distribution.** Solves imports but not
  installation, and leaves the build story undefined.
- **Keep runtime state beside the code and mount the whole tree writable.**
  Forces a writable image and mixes state into the artifact being versioned.
