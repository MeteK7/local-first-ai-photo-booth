# Stage 4 local QR downloads

## Behavior

- The result screen can issue a QR code for a single original JPEG or a Classic filmstrip. The booth checks the active session’s ownership and saves a SHA-256 digest of the random token in PostgreSQL. Each token identifies one result.
- Links are valid for 10 minutes by default. A completed session’s issued link lasts until its expiry. A canceled session’s links return HTTP 404. Expired links are cleaned up when a new link is issued.
- A dedicated listener in the booth process accepts HTTP downloads from the configured private IPv4 subnet. It runs on port 8001 by default and exposes the token download route. The kiosk and administration use the loopback listener. Bearer URLs are excluded from the LAN listener’s request logs. Responses use attachment disposition and no-store caching.
- Configure the current address and prefix with `PHOTOBOOTH_DOWNLOAD_BIND`. Use a trusted Wi-Fi network for the prototype. Update the bind setting and restart the booth if the computer’s Wi-Fi address changes.

## Verification

- Seven backend tests passed, including expiry, canceled and completed sessions, download ownership, client subnet filtering, and blocked admin routes.
- Three Angular tests, the production build, and the existing Edge session regression passed. In Edge, both result screens generated a readable QR image and served the exact test JPEG over the real Wi-Fi listener from a separate browser context. The administration routes returned HTTP 404 on the download address. The booth port was unreachable at the Wi-Fi address.
- The operator scanned the sample QR code on a physical phone on the same Wi-Fi and confirmed that the test JPEG downloaded. The phone test succeeded with the workstation’s existing firewall configuration.
