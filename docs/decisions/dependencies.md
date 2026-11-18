# Stage 1 dependency inventory

The version locks record the full resolved dependency graph for development. The principal packages and the licenses declared by their distributions are listed below. Review notices in platform-specific wheels before distributing a bundled runtime.

| Python package | Version tested | License |
|---|---|---|
| FastAPI | 0.162.0 | MIT |
| Uvicorn | 0.54.0 | BSD-3-Clause |
| SQLAlchemy | 2.1.6 | MIT |
| psycopg and psycopg-binary | 3.3.6 | LGPL-3.0-only |
| Alembic | 1.20.1 | MIT |
| pydantic-settings | 2.16.2 | MIT |
| pytest | 9.2.0 | MIT |
| HTTPX | 0.28.1 | BSD licensed |

The psycopg binary wheel includes its own PostgreSQL client library and notices. The source package does not bundle the Python environment or npm dependencies.

The Stage 2 Windows adapter uses [comtypes 1.5.0](https://pypi.org/project/comtypes/1.5.0/) to call the operating system’s [Windows Portable Devices API](https://learn.microsoft.com/en-us/windows/win32/wpd_sdk/supporting-mtp-extensions). comtypes has no required Python dependencies. Its [MIT license](https://github.com/enthought/comtypes/blob/main/LICENSE.txt) permits commercial use and redistribution with the copyright and permission notice included with any distributed copies or substantial portions.

Stage 3 uses [Pillow 13.0.0](https://pypi.org/project/Pillow/13.0.0/) for local JPEG orientation, resizing, and composition. Pillow publishes its own license and third-party notices. Include the applicable notices when distributing a bundled runtime. [Pillow license](https://github.com/python-pillow/Pillow/blob/13.0.0/LICENSE)

Stage 4 uses [qrcode 8.2](https://pypi.org/project/qrcode/8.2/) with the existing Pillow dependency to render PNGs locally. The package uses a BSD license and depends on the already pinned colorama on Windows. [qrcode license](https://github.com/lincolnloop/python-qrcode/blob/v8.2/LICENSE)

| Frontend package | Version tested | License |
|---|---|---|
| @angular/core | 22.2.4 | MIT |
| @angular/cli | 22.2.5 | MIT |
| @angular/build | 22.2.5 | MIT |
| rxjs | 7.8.2 | Apache-2.0 |
| typescript | 6.0.3 | Apache-2.0 |
| vitest | 5.0.5 | MIT |
| jsdom | 30.1.3 | MIT |
| @playwright/test | 1.64.1 | Apache-2.0 |
