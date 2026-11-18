# Stage 1 verification

The test commands are in the project README. Run the FastAPI API suite against the dedicated `photobooth_test` database, Angular component tests in Node, and the browser test against the built application running on loopback.

The backend tests exercise migrations, sessions across application restarts, isolation between browsers, local request protections, and administrator sign-out. The browser test checks that the customer workflow loads without off-machine network requests and that the unavailable camera state stays visible after reload.

The development database belongs to the local installation. It must be provisioned and checked separately from the disposable database used to verify this source package.

## Recorded checks

- Windows x64 with CPython 3.13.18, Node 24.21.0, and a separate loopback PostgreSQL 18.4 instance.
- Backend suite passed twice. Four tests covered state transitions, storage path handling, persistent sessions and administrator access. The final run reported one Starlette deprecation warning for its HTTPX test client.
- Angular production build and one Angular component test passed.
- The built UI was served by FastAPI. The welcome, session and administration routes returned HTML, and the database and storage readiness check returned ready.
- One Edge browser test passed. It started a session, showed the unavailable camera state, reloaded the session, finished it, and recorded no off-machine page requests.
- The test API and temporary PostgreSQL instance were stopped after verification.
- The installed project environment was upgraded to Windows x64 Python 3.15.2. All 32 locked dependencies matched, both backend unit tests passed, and the built UI, liveness, camera status, and storage readiness passed the smoke check. The original Python 3.13.18 environment is retained at `.tools/python-backups/venv-3.13.18` for rollback.

The existing PostgreSQL service still needs authorized local administrator credentials to provision the project role and its databases. The PostgreSQL integration tests were not rerun on Python 3.15.2.
