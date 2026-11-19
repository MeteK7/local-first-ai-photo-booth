# Multi-Photo Studio · Signature Strip

## Behavior and compatibility

- The setup screen displays 2–6 captures and previews the frame positions for each layout. FastAPI supplies these previews from the same geometry that Pillow uses for the final composition.
- PostgreSQL stores a versioned capture plan on the session and records the position of each saved frame. A repeated request for a saved position returns that original. The previous filmstrip session and result IDs still work, with a three-shot vertical default and the existing download filename.
- The renderer respects source orientation and preserves the original bytes. It fits the full image inside new layouts where filling the frame would remove more than one third of the source. The default three-shot vertical strip uses its historical square crops.
- The result is one JPEG at 300 dpi. Preview, booth download, phone delivery, and printing use that file. The Windows driver centers it in the requested print area and scales it down if the configured paper’s printable area is smaller.

| Layout | JPEG dimensions | Print target |
| --- | --- | --- |
| Vertical | 600 × 1800 px | 2 × 6 in. portrait |
| Horizontal | 1800 × 600 px | 6 × 2 in. landscape |
| Grid | 1800 × 1200 px | 6 × 4 in. landscape |

## Verification

- The local regression run passed 37 Python tests, five Angular tests, and two Edge tests. The production build passed. The layout picker was also checked at 360, 800, and 1280 px.
- The D5600 completed three vertical captures, two horizontal captures, and two grid captures. Each test used full-resolution 6000 × 4000 originals. All three browser downloads and LAN QR downloads matched the preview JPEG. Two originals from an earlier run were retained after autofocus interrupted the sequence.
- The operator confirmed that the Epson printed the three numbered layout samples in frame order, centered and fully visible.
- Run the backend regression suite with the existing PostgreSQL test database. It covers the count and layout matrix, orientation, saved-frame replay, legacy behavior, and byte equality across preview, booth download, phone download, and the printer adapter input.
- Run the Angular tests, production build, and Edge tests. The camera-free Edge check selects a six-shot grid and reopens the active session. The opt-in `d5600.spec.ts` checks the three-shot vertical default with the physical camera.
- On the booth, capture a default vertical strip and one configured horizontal or grid composition. Use a phone on the same Wi-Fi to scan the result’s QR code. Send one copy of each layout to the Epson and check the frame order, centering, orientation, and printable margins on paper. Earlier vertical-strip output is recorded in [Stage 5](stage5-printing.md).
