$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path reports | Out-Null
$version = '3.3.1'
$file = "TurboVNC-$version-x64.exe"
$expected = 'cb16f343ae39aac6fd8a6eb1c107e932bb2ff03419cb861d019cfb240896df1a'
$url = "https://github.com/TurboVNC/turbovnc/releases/download/$version/$file"
$dest = Join-Path $env:RUNNER_TEMP $file
Invoke-WebRequest -Uri $url -OutFile $dest -MaximumRedirection 10
$actual = (Get-FileHash $dest -Algorithm SHA256).Hash.ToLowerInvariant()
"Expected SHA256: $expected; actual: $actual" | Out-File reports/install.log
if ($actual -ne $expected) { throw 'Checksum mismatch' }
$p = Start-Process $dest -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -Wait -PassThru
"Installer exit: $($p.ExitCode)" | Out-File reports/install.log -Append
if ($p.ExitCode -ne 0) { throw "Install failed: $($p.ExitCode)" }
if (-not (Test-Path "$env:ProgramFiles\TurboVNC\vncviewer.bat")) { throw 'Viewer not found' }
