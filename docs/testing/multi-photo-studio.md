# Multi-Photo Studio

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

## Creative Collection

- **Between Frames** uses two or three aligned photographs to emphasize contrast between expressions or poses. Pose prompts are optional and the result is an editorial diptych or triptych.
- **Motion Study** cues four to six stages of a small movement. The first countdown is three seconds. Further two-second countdowns begin once live view is available after each full-resolution transfer. The print follows the movement through staggered frames and gives the final pose more space.
- On the physical D5600, four back-to-back capture and transfer requests took 4.71–5.09 seconds each. Camera EXIF showed exposure intervals of 4.53–4.98 seconds. Motion Study uses guided poses with that transfer path. A future continuous-motion mode needs a verified burst path with ordered, recoverable transfer.
- Both compositions reuse the 1800 × 1200 JPEG and 6 × 4 in. print profile. They reuse the saved capture positions, cookie-scoped previews, LAN QR links, and one-copy print jobs. No schema migration is needed for these two versioned capture plans.
- Phase 2 passed 44 Python tests, six Angular tests, three Edge regressions, and two physical D5600 browser tests. The physical tests completed a three-shot Between Frames session and a four-shot Motion Study session. They checked the on-screen cues, ordered shutter requests, and byte equality across the preview, booth download, and LAN QR download. The database integration tests checked the 6 × 4 print profile and verified the same JPEG reaches the print adapter.
- To repeat the two physical runs, set `PHOTOBOOTH_HARDWARE_TESTS=1` and run `npm --prefix .\frontend run e2e -- d5600.spec.ts --grep 'delivers (Between Frames|Motion Study)' --workers=1` against the running booth. Set `PHOTOBOOTH_HARDWARE_QR_TESTS=1` to check the configured LAN download listener as well. The two runs fire seven shutter releases and preserve the originals in the booth's storage.

## Mini Scene and Time Sculpture

- **Mini Scene** guides the customer through setup, action, reaction, and ending. Each countdown starts on demand so the customer can prepare the next beat. The four-panel storyboard gives the action the largest frame.
- **Time Sculpture** requires a fixed landscape camera, plain background, steady light, and fixed focus, exposure, and white balance. The operator enables it with `PHOTOBOOTH_TIME_SCULPTURE_ENABLED=1`. The session saves one empty reference frame and one pose in each of three marked areas.
- The renderer checks the three poses against the reference at reduced resolution. It accounts for a small, uniform color or brightness offset when the two unoccupied areas agree, then checks framing, background stability, pose contrast, and changes beyond each marked area. It uses the posed exposures for the output and limits color matching and feathering to the joins. A padded mask protects pose tones while the color correction preserves fine background detail.
- Failed checks produce a labeled **Pose sequence** with all three subject frames. The original JPEGs remain in local storage. The booth, LAN QR download, and 6 × 4 print job use the same selected JPEG and carry the outcome through session reload. The additive migration records the fallback explanation.
- `test_time_sculpture.py` tests clean seams and the fallback for framing changes, lighting changes, missing contrast, and a pose that crosses its area. To repeat the physical Mini Scene browser test, use `PHOTOBOOTH_HARDWARE_TESTS=1` and run `npm --prefix .\frontend run e2e -- d5600.spec.ts --grep 'delivers Mini Scene' --workers=1`. This test takes four real photographs.
- Phase 3 passed 54 Python tests, seven Angular tests, four camera-free Edge regressions, and the physical Mini Scene browser test. The Mini Scene preview, booth download, and LAN QR download contained the same JPEG. Integration tests verify the 6 × 4 print handoff and matching JPEG delivery for both Time Sculpture outcomes.
- Two supervised D5600 Time Sculpture sessions saved four originals each. The first run retained its pose-sequence fallback after larger background changes. Small brightness offsets in the second run were corrected using the saved frames. The renderer produced a three-pose composite whose seam bands differed from the reference by less than one intensity level per RGB channel on average.
- A subsequent blend update reduced mean deviation from the reference by about 70% across the 200-pixel bands centered on the two joins in the same Nikon trial. Renderer tests cover local brightness changes near a join and preservation of low-contrast details next to a pose.
- The current blend retains the exposure interiors. On the same Nikon frames, mean deviation from the contributing photographs in the interior of each section was at most 1.1 intensity levels per RGB channel. Mean deviation from the empty reference within 50 pixels of either join was below one level per channel.
