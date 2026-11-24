# Creative Studio

Take a **Single photo**, choose a treatment, and wait for the shared preview to update. Use **Download photo**, **Download on phone**, or **Print** for the selected version. Tap **Original** to return to the camera JPEG. A render starts when selected and is reused for the same original and treatment version.

- **Portrait Atlas** keeps the main image intact within an editorial layout and ranks detail crops using image contrast and texture. Portrait and landscape photos use different layouts.
- **Parallel Portrait** aligns a silver-toned photograph with a color-relief version made from multiscale contours and offset color masks.
- **The Film Frame** uses a 2.39:1 image window, local color grading, deterministic grain, and a matte. Tall photos get extra framing space to retain the whole subject.
- **Classic Filter** keeps the original local preview’s image preparation, color grade, and JPEG settings.

**New Year Frames** groups the eight single-photo designs, including **Bright Blue · 2027**, **Vibrant Celebration · 2027**, and **Cozy Winter · 2027**. These three landscape designs retain the supplied 1536 × 1024 artwork and fit the photo to the right-hand opening. Their English and Turkish names and descriptions use the shared translation catalogs. The lettering in the supplied artwork stays unchanged.

Both **Hazar Frames** and **New Year Frames** show a sample thumbnail for every design, ordered portrait first and landscape second, with the existing order retained within each orientation. Opening a collection loads the thumbnails without rendering the customer's photo or changing the selection. The cached JPEG samples use bundled offline photography and the production renderer, preserve each print's aspect ratio, and have a maximum edge of 360 pixels. `/api/sessions/current/photos/creative/frames/{treatment}/preview` serves only these public samples; customer-photo previews still require the owning session.

Rebuild these three overlays with `.venv/Scripts/python scripts/prepare-new-year-single.py SOURCE_DIRECTORY`, where the directory contains the original supplied PNGs. The script preserves the original RGB pixels and applies the checked-in alpha masks in `scripts/new-year-single-masks/` for Bright Blue and Vibrant Celebration. **Cozy Winter is copied unchanged from its original RGBA PNG**, preserving the soft, semi-transparent glow along the inner edges and corners, including the faintest gradient values. It must never use a thresholded or generated replacement mask. Its render version is 2 so selecting it refreshes previously prepared results. The mask directory records the preparation details.

The Creative Studio migration adds `creative_results` and references for the existing phone and print queues. Creative JPEGs are stored in the processed folder. The original and legacy files stay in their existing locations. A saved Cinematic portrait from the earlier preview appears as Classic Filter in its active session, and existing QR links keep their configured expiry. The photo booth retains saved images for manual owner management.

**AI Preview** is informational. Classic Filter and the other three treatments run locally in Pillow without provider credentials. The former `PHOTOBOOTH_AI_MODE` setting can be removed from local configuration.

## Verify

- Run the backend renderer tests to check orientation, deterministic output, print sizes, and Classic Filter parity.
- Run the PostgreSQL and Angular suites to check retries, selected-result routing, access isolation, and the existing single-photo and filmstrip flows.
- In the booth, preview all four outputs and switch between the original and a treatment. Scan a phone QR on the local network and confirm that **Print** and **Download photo** use the same result shown in the preview.
