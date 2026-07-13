param (
    [string]$TargetText,
    [string]$ImagePath
)

if (-not $TargetText) {
    Write-Host "ERROR: TargetText parameter is required."
    exit 1
}

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Runtime.WindowsRuntime

# Reflection helper to await WinRT async operations synchronously in PowerShell
function Wait-WinRtTask {
    param(
        [System.Object]$WinRtTask,
        [System.Type]$ResultType
    )
    
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | 
        Where-Object { 
            $_.Name -eq 'AsTask' -and 
            $_.GetParameters().Count -eq 1 -and 
            $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' 
        })[0]
    
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

# 1. Obtain screen image bytes
if ($ImagePath) {
    if (-not (Test-Path $ImagePath)) {
        Write-Host "ERROR: ImagePath file not found: $ImagePath"
        exit 1
    }
    $bytes = [System.IO.File]::ReadAllBytes($ImagePath)
}
else {
    # Fallback to capturing primary screen
    try {
        $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
        $graphics = [System.Drawing.Graphics]::FromImage($bmp)
        $graphics.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bounds.Size)
        
        $ms = New-Object System.IO.MemoryStream
        $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $bytes = $ms.ToArray()
        
        $bmp.Dispose()
        $graphics.Dispose()
        $ms.Dispose()
    }
    catch {
        Write-Host "ERROR: Screen capture failed - $_"
        exit 1
    }
}

# 2. Convert to WinRT SoftwareBitmap
$stream = [Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]::new()
$writer = [Windows.Storage.Streams.DataWriter, Windows.Storage.Streams, ContentType = WindowsRuntime]::new($stream)
$writer.WriteBytes($bytes)
$storeTask = $writer.StoreAsync()
$awaiter = [System.WindowsRuntimeSystemExtensions]::GetAwaiter($storeTask)
$awaiter.GetResult() | Out-Null
$stream.Seek(0)

# Create decoder
$decoderOp = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime]::CreateAsync($stream)
$decoder = Wait-WinRtTask $decoderOp ([Windows.Graphics.Imaging.BitmapDecoder])

# Get SoftwareBitmap
$bitmapOp = $decoder.GetSoftwareBitmapAsync()
$softwareBitmap = Wait-WinRtTask $bitmapOp ([Windows.Graphics.Imaging.SoftwareBitmap])

# 3. Initialize OcrEngine
$ocrEngine = [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime]::TryCreateFromUserProfileLanguages()
if (-not $ocrEngine) {
    Write-Host "ERROR: Could not initialize native OCR Engine."
    exit 1
}

# 4. Recognize
$ocrOp = $ocrEngine.RecognizeAsync($softwareBitmap)
$ocrResult = Wait-WinRtTask $ocrOp ([Windows.Media.Ocr.OcrResult])

$stream.Dispose()

# 5. Search for TargetText (case-insensitive substring match)
$found = $false
foreach ($line in $ocrResult.Lines) {
    $lineText = $line.Text
    if ($lineText.ToLower().Contains($TargetText.ToLower())) {
        # Calculate bounding box of the line
        $minX = 999999
        $minY = 999999
        $maxX = 0
        $maxY = 0
        
        foreach ($word in $line.Words) {
            $r = $word.BoundingRect
            if ($r.X -lt $minX) { $minX = $r.X }
            if ($r.Y -lt $minY) { $minY = $r.Y }
            if (($r.X + $r.Width) -gt $maxX) { $maxX = $r.X + $r.Width }
            if (($r.Y + $r.Height) -gt $maxY) { $maxY = $r.Y + $r.Height }
        }
        
        $centerX = [int]($minX + ($maxX - $minX) / 2)
        $centerY = [int]($minY + ($maxY - $minY) / 2)
        
        Write-Host "SUCCESS: Found '$lineText' at ($centerX, $centerY)"
        $found = $true
        break
    }
}

if (-not $found) {
    Write-Host "NOTFOUND: Could not locate text '$TargetText' on screen."
}
