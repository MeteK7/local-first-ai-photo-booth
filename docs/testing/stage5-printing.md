# Stage 5 local printing

## Behavior

- Print is available for the current session’s original photo or composed filmstrip. PostgreSQL records the job, the selected result, and the status reported by Windows. The customer can finish the session once the job is accepted by the booth.
- Each result can send one copy. Repeated requests return the same job. A confirmed failure before submission can be retried. If the worker is interrupted during submission, it records an uncertain outcome and leaves the operator to check the printer.
- The Windows adapter uses the installed printer driver and `PrintDocument`. It applies JPEG orientation, centers the image, and fits it within the printer’s printable area. The maximum sizes are 6 × 4 in. for a photo and 2 × 6 in. for a portrait filmstrip. Both layouts use the queue’s paper settings.
- The booth shows when Windows has accepted or handed off the job. Physical print delivery is confirmed by checking the tray. An offline queue or a paper error gets a customer-facing status.

## Verification

- Eight backend tests and three Angular tests passed. They cover ownership, safe retries, repeat requests, interrupted submissions, and the customer-facing offline state.
- The production build and Edge session regression passed. The Windows adapter reported the configured printer as unavailable when tested against a nonexistent queue.
- From the booth’s result screens in Edge, the Windows Epson queue accepted one photo and one filmstrip. Both showed the handoff status after reload and returned the original job on a repeated request.
- The operator confirmed both physical prints on the Epson L3356. The whole photo was centered in landscape, and all three filmstrip frames were centered in portrait.
