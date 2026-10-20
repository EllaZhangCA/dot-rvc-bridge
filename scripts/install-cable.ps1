$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskRuntime = Join-Path $taskRoot 'runtime'
$taskDownload = Join-Path $taskRuntime 'downloads\VBCABLE_Driver_Pack45.zip'
$taskExtract = Join-Path $taskRuntime 'vb-cable'
New-Item -ItemType Directory -Path (Split-Path $taskDownload -Parent),$taskExtract -Force | Out-Null
if (-not (Test-Path -LiteralPath $taskDownload)) {
    Invoke-WebRequest 'https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip' -OutFile $taskDownload
}
if ((Get-FileHash -LiteralPath $taskDownload -Algorithm SHA256).Hash -ne 'B950E39F01AF1D04EA623C8F6D8EB9B6EA5C477C637295FABF20631C85116BFB') { throw 'Driver archive hash mismatch; inspect the official release before updating the pin.' }
Expand-Archive -LiteralPath $taskDownload -DestinationPath $taskExtract -Force
$taskInstaller = Join-Path $taskExtract 'VBCABLE_Setup_x64.exe'
$taskSignature = Get-AuthenticodeSignature -LiteralPath $taskInstaller
if ($taskSignature.Status -ne 'Valid' -or $taskSignature.SignerCertificate.Subject -notmatch 'BUREL VINCENT') { throw 'Unexpected installer signature.' }
Write-Output 'Confirm the Windows administrator prompt, then choose Install Driver. Reboot when convenient if requested.'
Start-Process -FilePath $taskInstaller -WorkingDirectory $taskExtract -Verb RunAs -WindowStyle Normal -Wait
Get-PnpDevice -Class AudioEndpoint | Where-Object FriendlyName -Match 'CABLE' | Format-Table Status,FriendlyName
