# Local Photo Booth

The photo booth runs Angular, FastAPI and PostgreSQL on the booth computer. The Windows prototype connects to a physical Nikon D5600 through Windows Portable Devices and offers Single Photo and Multi-Photo Studio.

Run the commands below from `C:\Projects\local-first-ai-photo-booth` in PowerShell. Use x64 Python 3.15. The project environment was verified with Python 3.15.2. The application requires a running local PostgreSQL server.

## Install the application dependencies

If `.venv\Scripts\python.exe` already exists, check its version and dependencies. If it reports Python 3.15 and the dependency check succeeds, continue to PostgreSQL setup.

```powershell
.\.venv\Scripts\python.exe --version
uv pip check --python .\.venv\Scripts\python.exe
```

For a fresh checkout, use [uv](https://docs.astral.sh/uv/) to create the environment and install the locked packages. If `.venv` uses another Python version, back it up before creating the new environment.

```powershell
uv venv --python 3.15 .venv
uv pip sync --python .\.venv\Scripts\python.exe .\backend\requirements.lock.txt
```

The source package includes the verified Angular build. To rebuild it, use npm with Node 24.15 or newer within the Node 24 series:

```powershell
npm --prefix .\frontend ci
npm --prefix .\frontend run build
```

The Python input constraints are in `backend/requirements.in`. The locked versions were verified on Windows x64 with Python 3.13.18 and again with Python 3.15.2.

## Set up local PostgreSQL

From the application root, run the following one-time provisioning step in your own PowerShell terminal. Substitute your local PostgreSQL administrator account for `postgres` if needed. The first prompt is for the PostgreSQL administrator. The second prompt asks you to choose a new password for the dedicated application role. Keep both out of chat, shell command arguments, and shared logs.

```powershell
psql -X -W -h 127.0.0.1 -U postgres -d postgres -f .\scripts\provision-postgres.sql
```

The script creates `photobooth_app`, `photobooth_dev` and `photobooth_test`. It stops if any of those names already exist. If setup was interrupted, inspect which project objects were created before retrying. Copy `.env.example` to `.env` and set `PHOTOBOOTH_DB_PASSWORD` locally to the application-role password. Quote a password containing spaces or comment characters according to dotenv syntax. Do not use the PostgreSQL administrator password in `.env`.

```powershell
Copy-Item .env.example .env
# Edit the role password before running these commands.
.\.venv\Scripts\python.exe -m alembic -c .\backend\alembic.ini upgrade head
Push-Location backend
..\.venv\Scripts\python.exe -m app.manage create-admin operator
Pop-Location
.\scripts\start.ps1
```

Open http://127.0.0.1:8000/ for the booth or http://127.0.0.1:8000/admin for administration. The admin command prompts for a distinct booth administrator password and saves its scrypt hash. Use `/api/health/live` to check the process and `/api/health/ready` to check schema and storage readiness.

## Take a photo

Use a charged battery and connect the D5600 directly to a Windows USB port using a data cable. Extend a retractable lens and set the camera’s mode dial to P, A, S, or M. Insert a writable SD card, select single-shot release and Large JPEG, and close other camera-control applications.

- **Single photo** takes one picture. Use **Download photo** before finishing the session.
- **Multi-Photo Studio** opens **Signature Strip** in the Classic Collection. Choose 2–6 photos and a vertical, horizontal, or grid layout. The Creative Collection offers **Between Frames** for two or three contrasting portraits, **Motion Study** for guided poses in three editorial layouts, and **Mini Scene** for a four-photo storyboard. In Motion Study, **Contact Stack** and **Match Cut** take four photos, and **Ascending Cut** takes four to six. Choose **Continue to camera** to start. Reopen an interrupted session to continue from its saved photos. The finished composition can be previewed, downloaded, sent to a phone, or printed.

**Time Sculpture** is available for fixed-camera setups. Set `PHOTOBOOTH_TIME_SCULPTURE_ENABLED=1` in the project’s `.env` and restart the booth. Use an evenly lit, clear background, fixed landscape framing, and fixed exposure, focus, and white balance. Capture the empty scene, then place the same subject fully inside each marked area in turn. If the scene fails the compositing checks, the booth presents the three poses as a sequence.

The D5600 saves each exposure on its SD card. The booth copies each original JPEG to the local originals folder and saves the composed filmstrip separately.

For a camera-free booth check, set `PHOTOBOOTH_CAMERA_ENABLED=0` for the server process. See `docs/testing/stage2-d5600.md` for camera diagnostics and `docs/testing/multi-photo-studio.md` for Signature Strip verification.

## Use Creative Studio

Take a **Single photo** and choose **Portrait Atlas**, **Parallel Portrait**, **The Film Frame**, or **Classic Filter** in **Creative Studio**. The booth renders each treatment locally from the same original. Choose **Original** to return to the camera JPEG. The download and print controls apply to the version in the preview. **AI Preview** shows **Coming Soon**. See `docs/testing/creative-studio.md` for the local rendering and verification details.

## Download on a phone

Choose **Download on phone** below the original, Multi-Photo Studio composition, or selected Creative Studio treatment. Scan the QR code with a phone on the same Wi-Fi. Each code downloads the version selected when the code was issued. A code expires after 10 minutes by default. Finishing the session keeps the link usable until expiry. Canceling the session invalidates the link.

Set `PHOTOBOOTH_DOWNLOAD_BIND` in the project’s `.env` to the booth’s private IPv4 address and subnet prefix, such as `192.168.1.20/24`. Restart the booth after changing it. The download listener defaults to port 8001. The booth and admin interface use loopback port 8000.

Set `PHOTOBOOTH_DOWNLOAD_TTL_MINUTES` to adjust expiry, or `PHOTOBOOTH_DOWNLOAD_PORT` to select the download port. See `docs/testing/stage4-qr.md` for verification details.

## Print a result

Choose **Print** below the original, Multi-Photo Studio composition, or selected Creative Studio treatment. The booth sends one copy of the selected version to the local Windows printer and shows the job status. A retry appears when the booth can confirm the job failed before it was submitted. If Windows reports an uncertain result, check the output tray or the Windows queue.

Set `PHOTOBOOTH_PRINTER_NAME` in the project’s `.env` to the installed Windows queue name and restart the booth. The Epson L3356 uses `EPSON L3350 Series` on the test workstation. Signature Strip uses a 2 × 6 in. target for vertical and 6 × 2 in. for horizontal. Grid and the Creative Collection use 6 × 4 in. The booth fits the target within the queue’s configured paper. See `docs/testing/multi-photo-studio.md` for the layout checks.

For frontend development, keep the API running and use `npm --prefix .\frontend start`. Angular proxies local API requests to port 8000. Set `PHOTOBOOTH_DATA_ROOT` to an absolute path in the local configuration to override the default `data` directory.

## Verify

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -m 'not postgres'
$env:PHOTOBOOTH_RUN_DB_TESTS = '1'
..\.venv\Scripts\python.exe -m pytest -m postgres
Remove-Item Env:PHOTOBOOTH_RUN_DB_TESTS
Pop-Location
npm --prefix .\frontend test
npm --prefix .\frontend run build
# Start scripts\start.ps1 in another PowerShell terminal first, using photobooth_test and PHOTOBOOTH_CAMERA_ENABLED=0.
npm --prefix .\frontend run e2e
```

PostgreSQL integration tests use the local `photobooth_test` database and apply the pending migrations. They do not empty or reset databases. For the browser test, set `PHOTOBOOTH_DB_NAME=photobooth_test` in the server terminal and use an isolated `PHOTOBOOTH_DATA_ROOT`. The browser test uses installed Microsoft Edge (set `PHOTOBOOTH_EDGE_PATH` if browser discovery fails), reloads a real customer session, and rejects non-local page requests.

See `docs/decisions/stage1.md` for the application and security boundaries.
