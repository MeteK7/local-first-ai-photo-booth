# Stage 2 D5600 feasibility

## Prototype implementation

The prototype opens the D5600 through the Windows in-box Portable Devices class driver and issues PTP commands through the public WPD MTP extension API. The application owns the camera in a single local Python worker so it can bound a stalled driver call and reconnect on the next request. Nikon-specific operations are isolated from sessions and storage. The camera-specific operation identifiers and parameters are available in the [public libgphoto2 protocol reference](https://github.com/gphoto/libgphoto2/blob/master/camlibs/ptp2/ptp.h). The backend talks directly to Windows through comtypes.

- The physical D5600 reported ISO 100, an 18 mm focal length, and Large JPEG. At 5% battery the camera inhibited live view. With a charged battery it separately reported the lens and exposure-mode interlocks. Extending the lens and turning the dial to P cleared them. The booth displays instructions for those camera-reported conditions.
- In two Edge sessions, the physical D5600 supplied live view, focused during framing, fired after the countdown, and transferred a 6000×4000 JPEG. The first download matched the original file on disk byte for byte. The second capture used the opt-in hardware browser test. The session and administrator regression tests passed again after the camera changes.
- The D5600 captures to its SD card. The booth compares card object identifiers around the shutter request, then reads the new JPEG through Windows in bounded chunks. A retry waits for the file to finalize without refiring the shutter. The card retains the test exposures.
- Windows and the running booth detected the USB disconnect and rediscovered the D5600 after power cycling. A busy camera recovered after that power cycle. The later Epson test is recorded in [Stage 3 verification](stage3.md).
- The application keeps each original JPEG on disk and ties its metadata and download access to the active customer session in PostgreSQL. Preview and download stay on loopback.
- Five backend tests, two Angular tests, the production build, and the Edge session regression passed. The photo access test verifies that another browser and a finished session receive HTTP 404, and a repeated capture request returns the saved photo.
- Test on a neutral scene with a charged battery and Large JPEG selected. Start a booth session, confirm the live feed, run the countdown, then verify that the preview and download show the same image. Repeat in a new session, test USB reconnect while idle, and confirm a second browser session cannot open the first session’s photo.

To repeat the hardware test from the project root with the camera-enabled booth already running, use:

```powershell
$env:PHOTOBOOTH_HARDWARE_TESTS = '1'
npm --prefix .\frontend run e2e -- d5600.spec.ts
Remove-Item Env:PHOTOBOOTH_HARDWARE_TESTS
```

The test fires one shutter and stores the result in the running booth’s configured database and originals folder.

## Windows preflight

- Windows 11 Pro x64, build 22000, and CPython 3.15.2 x64.
- Windows had a previously registered `D5600` portable-device entry. It was absent during this check (`Present=False`, `CM_PROB_PHANTOM`). Repeat the check with the camera powered on and a USB data cable connected directly to the computer. Follow the connection guidance in the [D5600 reference manual](https://download.nikonimglib.com/archive3/T2D6s009HCPw03w5wYS97chunQ10/D5600RM_%28En%2904.pdf).
- All four backend foundation tests passed on `photobooth_test`, including session persistence, browser isolation, administrator access, and storage path handling. Starlette reported one TestClient deprecation warning. The running booth also returned HTTP 200 from `/api/health/ready` with database and storage ready.
- Windows reported the Epson queue as `EPSON L3350 Series` with `WorkOffline=True`. Recheck the queue when the booth has a captured JPEG for the print test.

```powershell
Get-PnpDevice -PresentOnly | Where-Object {
    $_.FriendlyName -match '\bD5600\b|\bNikon\b' -or $_.InstanceId -match '^USB\\VID_04B0'
} | Select-Object Status, Class, FriendlyName
```

## Optional Nikon SDK inquiry for later evaluation

Nikon lists the D5600 Camera Remote SDK and records 64-bit Windows 11 support for the Remote Module SDK. Nikon directs developers to the applicable agreement for license restrictions. The holder, redistribution, and confidentiality questions below are pending written clarification. [SDK catalog](https://sdk.nikonimaging.com/apply/) · [SDK FAQ and release notes](https://sdk.nikonimaging.com/information/en/)

Use [Nikon Türkiye support](https://www.nikon.com.tr/tr_TR/help-and-support/contact-us) or ask Nikon’s Turkish distributor to forward the inquiry to Nikon’s licensing team. The distributor publishes `info@karacasulu.com` for written inquiries. [Nikon global directory](https://www.nikon.com/network/turkey.html) · [Distributor contact details](https://www.karacasulu.com/iletisim/)

**Subject** — Licensing clarification for the Nikon D5600 Camera Remote SDK

> Hello,
>
> I am developing a photo booth application that controls a Nikon D5600 locally over USB on a Windows PC. I plan to prototype it as an individual and may later operate the product through a registered company at a small number of managed installations. Please route these questions to the team responsible for the D5600 Camera Remote SDK license.
>
> 1. Can I obtain the SDK as an individual to develop and test this product? If a company later takes over its development or operation, would it need a new agreement or Nikon’s written consent to a transfer?
> 2. Which SDK runtime files, if any, may the license holder install on multiple managed booth computers or bundle with the commercial application? Please identify any required notices, approvals, or separate agreements.
> 3. What does the agreement treat as confidential, and what approval is required before sharing covered documentation, headers, samples, binaries, or SDK-derived implementation details with a contractor or remote AI coding tool? The camera adapter runs locally. A separate customer-facing image transformation feature sends photographs and transformation requests to an image provider, independently of the camera adapter.
>
> Could you confirm the applicable agreement and its version or date and provide written guidance on these questions?
>
> Thank you.

### Physical test if the Nikon SDK is evaluated later

Use the designated license holder’s local SDK installation. Keep SDK materials and detailed SDK-derived diagnostics in the authorized local environment. Use the actual D5600 and record the camera firmware, lens, SDK release, and host architecture with the observed results.

| Check | Evidence to record |
| --- | --- |
| Discovery and ownership | Detect the D5600, open and close it, and reconnect. Check the response when the camera is already in use. |
| Capabilities and controls | Read body and lens information. Query allowed ISO, aperture, shutter speed, and exposure settings in relevant modes. Exercise writable controls and focus where supported, and restore the original settings. |
| Live view | Start and stop repeatedly. Record preview resolution, frame cadence, and any mode or time limits. Check that preview can resume after capture. |
| Capture and transfer | Trigger repeated single shots using the camera’s largest JPEG setting. Verify one complete, decodable file per successful capture with the dimensions expected for that camera setting. |
| Recovery | Disconnect USB during live view and during transfer. Check that operations fail within a bounded time, partial files stay out of results, and reconnecting allows a new capture. Check timeout recovery without automatically refiring the shutter when its prior outcome is uncertain. |

Compare a direct Python binding with a local native helper against the documented ABI, callback and threading requirements, and observed recovery behavior. Prefer the direct binding if it supports safe lifecycle management and bounded recovery on this host. Use a local helper if process isolation is required for native calls or recovery. Document the choice before wiring the adapter into FastAPI. Escalate missing live view or full-resolution transfer, or a license incompatible with the intended deployment, before selecting an alternative.
