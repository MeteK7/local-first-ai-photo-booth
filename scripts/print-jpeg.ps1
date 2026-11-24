param(
    [Parameter(Mandatory)][ValidateSet('Submit','Status')][string]$Action,
    [Parameter(Mandatory)][string]$Printer,
    [Parameter(Mandatory)][string]$Document,
    [ValidateSet('Photo','Filmstrip','HorizontalStrip')][string]$Layout = 'Photo',
    [string]$ImagePath
)

$ErrorActionPreference = 'Stop'

function Write-Result([string]$State, [string]$Detail) {
    @{state = $State; detail = $Detail} | ConvertTo-Json -Compress
}

function Write-SpoolStatus {
    $job = Get-CimInstance Win32_PrintJob | Where-Object {
        $_.Document -eq $Document -and $_.Name -like "$([WildcardPattern]::Escape($Printer)),*"
    } | Select-Object -First 1
    if (-not $job) {
        Write-Result 'sent' 'Sent to the printer. Check the output tray.'
    } elseif ($job.StatusMask -band 0x104) {
        Write-Result 'unknown' 'Windows removed the job. Check the output tray or ask the booth operator.'
    } elseif ($job.StatusMask -band 0x80) {
        Write-Result 'sent' 'Sent to the printer. Check the output tray.'
    } elseif ($job.StatusMask -band 0x20) {
        Write-Result 'submitted' 'The printer is offline. Windows is holding this print job.'
    } elseif ($job.StatusMask -band 0x40) {
        Write-Result 'submitted' 'The printer needs paper. Windows is holding this print job.'
    } elseif ($job.StatusMask -band 0x607) {
        Write-Result 'submitted' 'The printer needs attention. Ask the booth operator to check the queue.'
    } elseif ($job.StatusMask -band 0x10) {
        Write-Result 'submitted' 'Printing in Windows...'
    } else {
        Write-Result 'submitted' 'Queued in Windows.'
    }
}

if ($Action -eq 'Status') {
    Write-SpoolStatus
    return
}

$submitting = $false
$image = $null
$print = $null
try {
    $queue = Get-CimInstance Win32_Printer | Where-Object Name -eq $Printer | Select-Object -First 1
    if (-not $queue) {
        Write-Result 'failed' 'The configured printer is unavailable. Ask the booth operator to check it.'
        return
    }
    if ($queue.WorkOffline -or $queue.PrinterStatus -eq 7 -or $queue.ExtendedPrinterStatus -in @(7,11)) {
        Write-Result 'failed' 'The printer is offline. Check its power and connection, then try again.'
        return
    }
    if ($queue.DetectedErrorState -eq 4) {
        Write-Result 'failed' 'The printer needs paper. Load paper, then try again.'
        return
    }
    if ($queue.ExtendedPrinterStatus -in @(6,8,9) -or $queue.DetectedErrorState -in @(6,7,8,9,10,11,12,13,14)) {
        Write-Result 'failed' 'The printer needs attention. Ask the booth operator to check it.'
        return
    }
    Add-Type -AssemblyName System.Drawing
    $image = [System.Drawing.Image]::FromFile($ImagePath)
    if ($image.PropertyIdList -contains 274) {
        $orientation = [BitConverter]::ToUInt16($image.GetPropertyItem(274).Value, 0)
        $rotations = @{
            2='RotateNoneFlipX'; 3='Rotate180FlipNone'; 4='Rotate180FlipX'
            5='Rotate90FlipX'; 6='Rotate90FlipNone'; 7='Rotate270FlipX'; 8='Rotate270FlipNone'
        }
        if ($rotations.ContainsKey([int]$orientation)) {
            $image.RotateFlip([System.Drawing.RotateFlipType]$rotations[[int]$orientation])
        }
    }
    $print = New-Object System.Drawing.Printing.PrintDocument
    $print.DocumentName = $Document
    $print.PrinterSettings.PrinterName = $Printer
    if (-not $print.PrinterSettings.IsValid) {
        Write-Result 'failed' 'The Windows printer driver is unavailable.'
        return
    }
    $print.PrinterSettings.Copies = 1
    $print.PrintController = New-Object System.Drawing.Printing.StandardPrintController
    $print.DefaultPageSettings.Landscape = $Layout -eq 'HorizontalStrip' -or ($Layout -eq 'Photo' -and $image.Width -gt $image.Height)
    $targetWidth = if ($Layout -eq 'Filmstrip') { 200 } elseif ($print.DefaultPageSettings.Landscape) { 600 } else { 400 }
    $targetHeight = if ($Layout -eq 'HorizontalStrip') { 200 } elseif ($print.DefaultPageSettings.Landscape) { 400 } else { 600 }
    $print.add_PrintPage({
        param($sender, $event)
        $clip = $event.Graphics.VisibleClipBounds
        # The print graphics use hundredths of an inch measured from the printable area.
        $widthLimit = [Math]::Min($targetWidth, $clip.Width)
        $heightLimit = [Math]::Min($targetHeight, $clip.Height)
        if ($widthLimit -le 0 -or $heightLimit -le 0) { throw 'Invalid printable area.' }
        $scale = [Math]::Min($widthLimit / $image.Width, $heightLimit / $image.Height)
        $width = $image.Width * $scale
        $height = $image.Height * $scale
        $area = [System.Drawing.RectangleF]::new(
            $clip.X + ($clip.Width - $width) / 2, $clip.Y + ($clip.Height - $height) / 2, $width, $height
        )
        $event.Graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $event.Graphics.DrawImage($image, $area)
        $event.HasMorePages = $false
    })
    $submitting = $true
    $print.Print()
    try {
        Write-SpoolStatus
    } catch {
        Write-Result 'submitted' 'Queued in Windows. Waiting for the printer status.'
    }
} catch {
    if ($submitting) {
        Write-Result 'unknown' 'Check the output tray or ask the booth operator to check the print queue.'
    } else {
        Write-Result 'failed' 'Windows could not prepare the print. Ask the booth operator to check the printer.'
    }
} finally {
    if ($print) { $print.Dispose() }
    if ($image) { $image.Dispose() }
}
