param(
    [string]$Distro = "Ubuntu-22.04",
    [string]$ProjectRoot = "/home/kardo/projects/rosbag-dashboard"
)

$ErrorActionPreference = "Stop"
$desktop = [Environment]::GetFolderPath("Desktop")
$powershellPath = Join-Path ([Environment]::SystemDirectory) "WindowsPowerShell\v1.0\powershell.exe"
$launcherPath = Join-Path $PSScriptRoot "Open-RosbagAnalyser.ps1"

$shell = New-Object -ComObject WScript.Shell
$modes = @(
    @{ Name = "Real data"; Argument = "real"; Description = "Open the local app with real recordings" },
    @{ Name = "Synthetic data"; Argument = "synthetic"; Description = "Open the same app with an in-memory synthetic archive" }
)

foreach ($mode in $modes) {
    $shortcutPath = Join-Path $desktop "ROS 2 Bag Analyser - $($mode.Name).lnk"
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $powershellPath
    $shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcherPath`" -Distro `"$Distro`" -ProjectRoot `"$ProjectRoot`" -Mode $($mode.Argument)"
    $shortcut.WorkingDirectory = $env:USERPROFILE
    $shortcut.Description = $mode.Description
    $shortcut.IconLocation = "$powershellPath,0"
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    Write-Output "Installed shortcut: $shortcutPath"
}
