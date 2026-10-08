# Security policy -- message-pusher

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |

## Reporting a vulnerability

Report privately through GitHub's "Report a vulnerability" flow on the
repository's Security tab. Do not open a public issue for a suspected
vulnerability.

Include the affected version, a minimal reproduction, the impact you believe it
has, and any proof of concept. Expect an acknowledgement within three working
days and a remediation plan within ten.

## Threat model

### What this service protects

- **Configuration secrets.** `SECRET_KEY` and database credentials are read
  from the environment, are never rendered by `/version`, and are redacted by
  `Settings.as_dict()`. The container refuses to start in production without
  `SECRET_KEY`.
- **Error detail.** Unhandled exceptions return a generic `500`. The traceback
  is written to the log with a correlation id, not to the response body.
- **Response hardening.** Security headers are applied centrally to every
  response, error responses included, so a new route cannot forget them.
- **Resource exhaustion through large bodies.** `MAX_CONTENT_LENGTH` caps
  request bodies and produces `413` with the standard envelope.
- **Container surface.** Multi-stage build, unprivileged uid 1001, all
  capabilities dropped, `no-new-privileges`, read-only root filesystem, and a
  writable volume only for `DATA_DIR`.

### What this service does not protect

These are deliberate scope decisions, not oversights. Each one means the control
belongs somewhere else in the deployment:

- **Authentication and authorization** are present only where the route table
  says so. A route without a guard is public. Put an authenticating proxy in
  front of the service if that is not acceptable.
- **Transport security.** TLS is terminated upstream. HSTS is emitted only when
  `APP_ENV=production`, and only if the upstream actually speaks HTTPS.
- **Rate limiting** is the caller's problem unless a route implements it.
- **Multi-tenancy.** There is one database and no tenant column. Do not share an
  instance between untrusted parties.
- **Supply-chain verification.** Dependencies are pinned by range, not by hash,
  and no SBOM is published.

### Trust boundaries

1. Reverse proxy to application: headers from upstream are trusted, including
   `X-Request-ID`.
2. Application to database: credentials come from the environment.
3. Application to third-party APIs: the service makes outbound calls where the
   domain modules require them. Their responses are untrusted input and are parsed
   defensively, with explicit timeouts so a hung upstream cannot pin a worker.

## Hardening checklist for deployments

- [ ] `SECRET_KEY` is unique per environment and stored in a secret manager.
- [ ] `APP_ENV=production` (enables HSTS, disables debug).
- [ ] TLS terminated upstream and the origin is not directly reachable.
- [ ] The service runs as a non-root user with no added capabilities.
- [ ] `DATA_DIR` is on a volume and the root filesystem is read-only.
- [ ] `/metrics` and `/version` are not exposed to the public internet.
- [ ] Logs are shipped off the host before the disk fills.
- [ ] Dependency updates are reviewed and `pip-audit` is wired into CI.

## Security-relevant configuration

| Variable             | Security effect                                       |
| -------------------- | ----------------------------------------------------- |
| `SECRET_KEY`         | Session and CSRF signing. Required in production.      |
| `APP_ENV`            | `production` enables HSTS and forbids the dev secret.  |
| `DEBUG`              | Must be `false` in production; the debugger is an RCE. |
| `MAX_CONTENT_LENGTH` | Caps request bodies.                                  |
| `LOG_JSON`           | Structured logs make tampering and PII easier to audit. |
