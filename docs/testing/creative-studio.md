# Creative Studio

Take a **Single photo**, choose a treatment, and wait for the shared preview to update. Use **Download photo**, **Download on phone**, or **Print** for the selected version. Tap **Original** to return to the camera JPEG. A render starts when selected and is reused for the same original and treatment version.

- **Portrait Atlas** keeps the main image intact within an editorial layout and ranks detail crops using image contrast and texture. Portrait and landscape photos use different layouts.
- **Parallel Portrait** aligns a silver-toned photograph with a color-relief version made from multiscale contours and offset color masks.
- **The Film Frame** uses a 2.39:1 image window, local color grading, deterministic grain, and a matte. Tall photos get extra framing space to retain the whole subject.
- **Classic Filter** keeps the original local preview’s image preparation, color grade, and JPEG settings.

The Creative Studio migration adds `creative_results` and references for the existing phone and print queues. Creative JPEGs are stored in the processed folder. The original and legacy files stay in their existing locations. A saved Cinematic portrait from the earlier preview appears as Classic Filter in its active session, and existing QR links keep their configured expiry. The photo booth retains saved images for manual owner management.

**AI Preview** is informational. Classic Filter and the other three treatments run locally in Pillow without provider credentials. The former `PHOTOBOOTH_AI_MODE` setting can be removed from local configuration.

## Verify

- Run the backend renderer tests to check orientation, deterministic output, print sizes, and Classic Filter parity.
- Run the PostgreSQL and Angular suites to check retries, selected-result routing, access isolation, and the existing single-photo and filmstrip flows.
- In the booth, preview all four outputs and switch between the original and a treatment. Scan a phone QR on the local network and confirm that **Print** and **Download photo** use the same result shown in the preview.
