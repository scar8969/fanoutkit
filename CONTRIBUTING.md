# Contributing to message-pusher

Thanks for taking the time. This is the short version of how changes land here.

## Getting set up

```sh
git clone <your-fork> a2_message_pusher && cd a2_message_pusher
python -m venv .venv
. .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install
make test
```

If `make test` passes on a clean checkout, your environment is correct.

## Workflow

1. Open an issue describing the change, or comment on an existing one. Small
   fixes can skip this step.
2. Branch from `main`: `fix/<topic>`, `feat/<topic>` or `chore/<topic>`.
3. Make the change in small commits.
4. Run `make check` before opening the pull request. It runs the same gate CI
   runs: lint, types, and tests with coverage.
5. Open the pull request and fill in the template. Describe the failure mode you
   are fixing, not just the diff.

## Commit messages

Conventional Commits:

```
<type>(<scope>): <imperative summary, 50 characters or fewer>

<body: why, not what. Wrap at 72 columns.>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`,
`build`, `ci`, `chore`. The scope is usually the module, for example
`config` or `http`.

## Standards

- **Types.** `mypy --strict` must pass. Prefer a narrow type over `Any`; if
  `Any` is unavoidable, say why in a comment.
- **Style.** `ruff` decides. Do not argue with the formatter in review; change
  the configuration in a separate pull request if the rule is wrong.
- **Tests.** Every bug fix gets a regression test that fails before the fix. New
  behaviour gets a contract test. Tests must not depend on network access or on
  wall-clock ordering.
- **Errors.** Raise an `AppError` subclass with a stable `code` when a caller
  can act on the failure. Let genuine bugs propagate.
- **Logging.** Log events, not prose: `log.info("event_name", extra={...})`.
  Never log secrets or full request bodies.
- **Configuration.** A new setting goes in `config.Settings`, in
  `.env.example`, and in the README table. A setting that is not documented
  does not exist.

## Adding an endpoint

1. Add the route to the application modules.
2. Add its path and methods to `openapi/a2_message_pusher.yaml`. The spec is the
   contract; an undocumented route is a defect.
3. Decide its authentication story explicitly. If it is public, say so in review.
4. Add a test covering the success path and at least one failure path.

## What will get a pull request sent back

- A new top-level module instead of a module inside `src/message_pusher/`.
- An absolute import where a relative one is required.
- A new dependency without a justification in the description.
- Suppressing a failure: `except Exception: pass`, a widened type-ignore
  comment, or a skipped test without a linked issue.
- Prose in a log message where an event name is required.

## Reporting a security issue

Do not use the issue tracker. See [SECURITY.md](SECURITY.md).
