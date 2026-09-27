param(
    [ValidateSet("real", "synthetic")]
    [string]$Mode = "real",
    [string]$Distro = "Ubuntu-22.04",
    [string]$ProjectRoot = "/home/kardo/projects/rosbag-dashboard",
    [string]$Url
)

$ErrorActionPreference = "Stop"

try {
    if ($Url) {
        $address = [Uri]$Url
        if (!$address.IsAbsoluteUri -or !$address.IsLoopback -or $address.Scheme -notin @("http", "https")) {
            throw "The application URL must use HTTP or HTTPS on loopback."
        }
        $candidates = @(
            (Join-Path ([Environment]::GetFolderPath("ProgramFiles")) "Google\Chrome\Application\chrome.exe"),
            (Join-Path ([Environment]::GetFolderPath("ProgramFilesX86")) "Google\Chrome\Application\chrome.exe"),
            (Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Google\Chrome\Application\chrome.exe")
        )
        $chrome = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if (!$chrome) { throw "Google Chrome was not found. Install Chrome and try again." }
        $start = New-Object System.Diagnostics.ProcessStartInfo
        $start.FileName = $chrome
        $start.Arguments = "--new-tab $($address.AbsoluteUri)"
        $start.UseShellExecute = $false
        [System.Diagnostics.Process]::Start($start) | Out-Null
        Write-Output "Opened Chrome at $($address.AbsoluteUri)"
    } else {
        # Some Windows environments omit .EXE from PATHEXT. Correct only this
        # launcher's environment so PowerShell invokes WSL as an executable.
        if (($env:PATHEXT -split ";") -notcontains ".EXE") {
            $env:PATHEXT = "$env:PATHEXT;.EXE"
        }
        $wsl = Join-Path ([Environment]::SystemDirectory) "wsl.exe"
        # Let PowerShell pass individual arguments; WSL's handling of the
        # shortcut's raw quoted command line can preserve distro quotes.
        & $wsl --distribution $Distro --cd $ProjectRoot --exec "$ProjectRoot/dev" open $Mode
        if ($LASTEXITCODE -ne 0) { throw "The $Mode application launcher exited with code $LASTEXITCODE. See the error above." }
    }
} catch {
    Write-Host "ROS 2 Bag Analyser: $($_.Exception.Message)" -ForegroundColor Red
    if (!$Url) { Read-Host "Press Enter to close" | Out-Null }
    exit 1
}
