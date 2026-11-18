# Epson feasibility and Classic filmstrip

## Epson L3356

Windows identified the USB printer through the `EPSON L3350 Series` queue. One verified booth JPEG was printed with the installed driver using the queue’s Letter default. The image was fitted inside a 6 × 4 in. area and centered in landscape. The job left the Windows queue and the operator confirmed the physical print was correct.

## Filmstrip behavior

- Existing sessions default to the single-photo experience after the additive migration.
- A Classic filmstrip session takes three photos with a three-second countdown before each. The browser waits for live view to return between photos. A reopened session uses its saved photo count. A successful shutter request can be retried with the same request ID to recover its result.
- PostgreSQL records the three originals as individual photos and one filmstrip result for the session. Pillow applies each source’s EXIF orientation and center-crops it into a square frame. The three frames are placed in capture order on a white 600 × 1800 JPEG at 300 dpi. The booth stores the result in the processed area and each source under originals.
- The active session cookie authorizes the filmstrip preview and download. Composition can be retried after all three originals are saved.

## Verification

Six Python tests and three Angular tests passed. The backend tests use `photobooth_test` and verify chronological frame order, original JPEG bytes, retry behavior, and access isolation. The production Angular build, database-backed Edge session regression, and both physical D5600 browser tests passed.

To run the opt-in physical checks against the already running camera-enabled booth:

```powershell
$env:PHOTOBOOTH_HARDWARE_TESTS = '1'
npm --prefix .\frontend run e2e -- d5600.spec.ts --workers=1
Remove-Item Env:PHOTOBOOTH_HARDWARE_TESTS
```

These tests fire four shutter releases across single-photo and filmstrip sessions and save the originals in the running booth’s configured data directory.
