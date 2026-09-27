param(
    [string]$Distro = "Ubuntu-22.04",
    [string]$ProjectRoot = "/home/kardo/projects/rosbag-dashboard"
)

$ErrorActionPreference = "Stop"
$desktop = [Environment]::GetFolderPath("Desktop")
$wslPath = Join-Path $env:WINDIR "System32\wsl.exe"

$shell = New-Object -ComObject WScript.Shell
$modes = @(
    @{ Name = "Real data"; Argument = "real"; Description = "Open the local app with real recordings" },
    @{ Name = "Synthetic data"; Argument = "synthetic"; Description = "Open the same app with an in-memory synthetic archive" }
)

foreach ($mode in $modes) {
    $shortcutPath = Join-Path $desktop "ROS 2 Bag Analyser - $($mode.Name).lnk"
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $wslPath
    $shortcut.Arguments = "-d `"$Distro`" --cd `"$ProjectRoot`" --exec ./dev open $($mode.Argument)"
    $shortcut.WorkingDirectory = $env:USERPROFILE
    $shortcut.Description = $mode.Description
    $shortcut.IconLocation = "$wslPath,0"
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    Write-Output "Installed shortcut: $shortcutPath"
}
