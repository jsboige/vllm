#Requires -Version 5
[CmdletBinding()]
param (
    [string]
    $JsonPath = "myia_vllm/docs/archeology/MASTER_COMMIT_LIST_JSBOIGE.json",

    [string]
    $DestinationRoot = "myia_vllm/docs/archeology/restored_artifacts"
   )
   
   # Assurer que le répertoire de destination existe et est propre
   if (-not (Test-Path $DestinationRoot)) {
    New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
   }
   
   Write-Host "Chargement du fichier de commits depuis $JsonPath..."
   if (-not (Test-Path $JsonPath)) {
    Write-Error "Le fichier de commits '$JsonPath' n'a pas été trouvé."
    return
   }
   $commitsData = Get-Content -Path $JsonPath | ConvertFrom-Json
   
   # On ne filtre plus, on prend tout
   $commitsToProcess = $commitsData
   
   Write-Host "$($commitsToProcess.Count) commits à traiter."
   
   foreach ($commit in $commitsToProcess) {
    $sha = $commit.sha
    $commitDate = [datetime]$commit.date
    # Nouveau format de date incluant l'heure
    $dateStr = $commitDate.ToString("yyyy-MM-dd_HH-mm-ss")
    $shortSha = $sha.Substring(0, 7)
   
    $targetDir = Join-Path $DestinationRoot -ChildPath "$dateStr-($shortSha)"
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null

    Write-Host "Traitement du commit $shortSha du $dateStr..."

    try {
        $files = git show --pretty="" --name-status $sha | ForEach-Object {
            $parts = $_ -split '\s+'
            if ($parts.Count -ge 2) {
                [PSCustomObject]@{
                    Status = $parts[0]
                    Path   = $parts[1]
                }
            }
        }

        foreach ($file in $files) {
            if ($file.Status -in @('A', 'M')) {
                Write-Host "  - Restauration de $($file.Path) (Statut: $($file.Status))"
                $destinationPath = Join-Path $targetDir $file.Path
                $destinationSubDir = Split-Path -Path $destinationPath -Parent

                if (-not (Test-Path $destinationSubDir)) {
                    New-Item -ItemType Directory -Path $destinationSubDir -Force | Out-Null
                }

                # Utilisation de cmd /c pour une redirection de flux binaire fiable,
                # contournant les problèmes d'encodage de PowerShell 5.
                $gitCmd = "git show --binary ""$($sha):$($file.Path)"""
                cmd /c "$gitCmd > ""$destinationPath"""
            }
        }
    }
    catch {
        Write-Warning "Erreur lors du traitement du commit $sha. Il est peut-être corrompu ou inaccessible. $_"
    }
}

Write-Host "La restauration des artefacts est terminée."
