# Stage 6 · Local photo effect preview

Set `PHOTOBOOTH_AI_MODE=preview` in the booth's local `.env`, run `.\.venv\Scripts\python.exe -m alembic -c .\backend\alembic.ini upgrade head` from the project root, and restart the booth. Set `PHOTOBOOTH_AI_MODE=disabled` and restart to turn off processing. The default configuration is `disabled`.

1. Start a **Single photo** session and take a photo.
2. Open **AI photo preview** on the result. Select the consent checkbox under **Local test effect** and choose **Create test image**.
3. Wait for **Your photo effect is ready**. Use **Download effect**, **Download effect on phone**, or **Print effect** beneath the processed image. The original has its own download and print controls. Create the phone QR before finishing the session. The QR remains valid until it expires.

The Cinematic portrait test uses a fixed Pillow color grade. It runs in a background worker, stores job state in PostgreSQL, and saves its JPEG in `ai-generated`. Camera JPEGs stay in `originals`. Both results require the active session. If the local processor reports a failure, the customer can download the original or consent to try again. A job left in progress after a restart is marked interrupted once its five-minute timeout elapses. The test needs no network connection, provider credentials, or AI service.

Template names, descriptions, stored prompts and availability are managed locally. For example, update the seeded template from the project root:

```powershell
Push-Location .\backend
..\.venv\Scripts\python.exe -m app.manage set-ai-template cinematic-portrait --name 'Cinematic portrait' --enabled
Pop-Location
```

Prompts are saved for a future live provider. The fixed test effect uses the same color grade for every template.

## Verification

- PostgreSQL and FastAPI tests cover affirmative consent, asynchronous dispatch, metadata removal from the working copy, original preservation, session isolation, failure and explicit retry.
- Angular tests cover consent, polling and the finished image. The production Angular build passed.
- Edge verified the full preview and download workflow with a synthetic JPEG against the test database. The result persisted after reload, the original's checksum matched, and a separate session received a 404 for the result. The page made zero external requests. The existing browser session regression test also passed.
