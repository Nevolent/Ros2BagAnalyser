param(
    [string]$Distro = "Ubuntu-22.04",
    [string]$ProjectRoot = "/home/kardo/projects/rosbag-dashboard"
)

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "ROS 2 Bag Analyser.lnk"
$wslPath = Join-Path $env:WINDIR "System32\wsl.exe"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $wslPath
$shortcut.Arguments = "-d $Distro --cd `"$ProjectRoot`" --exec ./dev open"
$shortcut.WorkingDirectory = $env:USERPROFILE
$shortcut.Description = "Start ROS 2 Bag Analyser and open it in the browser"
$shortcut.IconLocation = "$wslPath,0"
$shortcut.WindowStyle = 7
$shortcut.Save()

Write-Output "Installed shortcut: $shortcutPath"
