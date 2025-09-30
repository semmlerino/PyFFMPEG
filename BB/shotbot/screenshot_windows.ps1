# PowerShell script to focus ShotBot window and capture screenshot
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Try to find and focus ShotBot window
Add-Type @"
    using System;
    using System.Runtime.InteropServices;
    public class WindowHelper {
        [DllImport("user32.dll")]
        public static extern bool SetForegroundWindow(IntPtr hWnd);

        [DllImport("user32.dll")]
        public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
    }
"@

# Try to find ShotBot window - search for any window containing "ShotBot"
$allWindows = Get-Process | Where-Object {$_.MainWindowTitle -like "*ShotBot*"}
if ($allWindows) {
    foreach ($proc in $allWindows) {
        if ($proc.MainWindowHandle -ne [IntPtr]::Zero) {
            [WindowHelper]::SetForegroundWindow($proc.MainWindowHandle) | Out-Null
            Start-Sleep -Milliseconds 500
            break
        }
    }
}

# Capture screenshot
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)

$outputPath = "C:\temp\shotbot_screenshot.png"
$bitmap.Save($outputPath)

$graphics.Dispose()
$bitmap.Dispose()

Write-Host "Screenshot saved to: $outputPath"