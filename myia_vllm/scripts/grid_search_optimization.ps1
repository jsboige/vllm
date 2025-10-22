<#
.SYNOPSIS
    Script d'automatisation du Grid Search pour optimisation vLLM multi-tours

.DESCRIPTION
    Ce script automatise le test de 12 configurations stratégiques de vLLM pour identifier
    la configuration optimale pour les tâches agentiques multi-tours.
    
    Workflow pour chaque configuration :
    1. Backup de medium.yml
    2. Modification des paramètres vLLM
    3. Redéploiement du container Docker
    4. Vérification health (timeout 10 min)
    5. Exécution des tests de performance
    6. Sauvegarde des résultats structurés
    7. Génération du rapport comparatif final

.PARAMETER ConfigFile
    Chemin vers le fichier JSON contenant les configurations à tester.
    Défaut : "configs/grid_search_configs.json"

.PARAMETER Resume
    Reprendre un grid search interrompu depuis le dernier état sauvegardé.

.PARAMETER SkipBackup
    Ne pas créer de backup de medium.yml (DANGEREUX - déconseillé en production).

.PARAMETER Verbose
    Afficher les logs détaillés en temps réel.

.PARAMETER DryRun
    Mode simulation sans modifier réellement les fichiers ni redéployer les containers.

.EXAMPLE
    .\grid_search_optimization.ps1
    Lance le grid search complet avec les paramètres par défaut.

.EXAMPLE
    .\grid_search_optimization.ps1 -Resume
    Reprend un grid search interrompu depuis la dernière configuration testée.

.EXAMPLE
    .\grid_search_optimization.ps1 -DryRun -Verbose
    Simule le grid search avec logs détaillés sans modifier le système.

.NOTES
    Version: 1.0.0
    Date: 2025-10-17
    Auteur: Roo Code (Mode)
    Durée estimée: 3-4 heures pour le grid search complet (12 configurations)
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$ConfigFile = "configs/grid_search_configs.json",
    
    [Parameter(Mandatory=$false)]
    [switch]$Resume,
    
    [Parameter(Mandatory=$false)]
    [switch]$SkipBackup,
    
    [Parameter(Mandatory=$false)]
    [switch]$DryRun
)

# =============================================================================
# CONFIGURATION GLOBALE
# =============================================================================

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# Chemins relatifs au répertoire du script
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$MediumYmlPath = Join-Path $ProjectRoot "configs\docker\profiles\medium.yml"
$LogsDir = Join-Path $ProjectRoot "logs"
$ResultsDir = Join-Path $ProjectRoot "test_results"
$ProgressFile = Join-Path $ProjectRoot "grid_search_progress.json"

# Constantes de timeout
$DEPLOYMENT_TIMEOUT_SECONDS = 600  # 10 minutes
$HEALTH_CHECK_INTERVAL_SECONDS = 15
$TEST_KV_CACHE_TIMEOUT_SECONDS = 300  # 5 minutes
$TEST_TTFT_TIMEOUT_SECONDS = 180  # 3 minutes
$TEST_THROUGHPUT_TIMEOUT_SECONDS = 180  # 3 minutes

# Timestamp pour nommage des fichiers
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$MainLogFile = Join-Path $LogsDir "grid_search_$Timestamp.log"

# Couleurs pour les sorties console
$Colors = @{
    Info = "Cyan"
    Success = "Green"
    Warning = "Yellow"
    Error = "Red"
    Critical = "Magenta"
}

# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

function Write-ColorOutput {
    <#
    .SYNOPSIS
        Écrit un message coloré dans la console et le log principal.
    #>
    param(
        [Parameter(Mandatory=$false)]
        [AllowEmptyString()]
        [string]$Message = "",
        
        [Parameter(Mandatory=$false)]
        [ValidateSet("Info", "Success", "Warning", "Error", "Critical")]
        [string]$Level = "Info"
    )
    
    # Gérer les messages vides pour les lignes blanches
    if ([string]::IsNullOrEmpty($Message)) {
        Write-Host ""
        # Optionnel: écrire ligne vide dans le log aussi
        Add-Content -Path $MainLogFile -Value "" -ErrorAction SilentlyContinue
        return
    }
    
    $Color = $Colors[$Level]
    $Prefix = "[$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))] [$Level]"
    $FullMessage = "$Prefix $Message"
    
    Write-Host $FullMessage -ForegroundColor $Color
    
    # Écrire dans le log principal
    Add-Content -Path $MainLogFile -Value $FullMessage -ErrorAction SilentlyContinue
}

function Get-VllmContainerName {
    <#
    .SYNOPSIS
    Détecte automatiquement le nom du container vLLM medium
    
    .DESCRIPTION
    Recherche le container créé par Docker Compose avec le projet "myia_vllm"
    et le service "medium". Retourne le nom réel du container.
    
    .OUTPUTS
    String - Nom du container (ex: "myia_vllm-medium-qwen3")
    #>
    
    # Méthode 1 : Détection via labels Docker Compose (plus fiable)
    $containerName = docker ps --filter "label=com.docker.compose.project=myia_vllm" `
                                --filter "label=com.docker.compose.service=medium" `
                                --format "{{.Names}}" 2>$null | Select-Object -First 1
    
    if ($containerName) {
        return $containerName
    }
    
    # Méthode 2 : Fallback - Recherche par pattern dans le nom
    $containerName = docker ps --filter "name=medium" --format "{{.Names}}" 2>$null |
                     Where-Object { $_ -match "medium" } | Select-Object -First 1
    
    if ($containerName) {
        return $containerName
    }
    
    # Méthode 3 : Fallback final - Nom hardcodé (basé sur la convention Docker Compose actuelle)
    Write-ColorOutput "⚠️  Impossible de détecter automatiquement le container - Utilisation du nom par défaut" -Level Warning
    return "myia_vllm-medium-qwen3"
}

function Initialize-Environment {
    <#
    .SYNOPSIS
        Initialise l'environnement : crée les répertoires nécessaires, vérifie les prérequis.
    #>
    
    Write-ColorOutput "Initialisation de l'environnement..." -Level Info
    
    # Créer les répertoires s'ils n'existent pas
    @($LogsDir, $ResultsDir) | ForEach-Object {
        if (-not (Test-Path $_)) {
            New-Item -ItemType Directory -Path $_ -Force | Out-Null
            Write-ColorOutput "Répertoire créé : $_" -Level Info
        }
    }
    
    # Vérifier les prérequis
    $Prerequisites = @(
        @{ Name = "Docker"; Command = "docker info"; ErrorMsg = "Docker daemon non disponible" },
        @{ Name = "Docker Compose"; Command = "docker compose version"; ErrorMsg = "Docker Compose non installé" },
        @{ Name = "medium.yml"; Path = $MediumYmlPath; ErrorMsg = "Fichier medium.yml introuvable" },
        @{ Name = "Fichier configs"; Path = (Join-Path $ProjectRoot $ConfigFile); ErrorMsg = "Fichier de configurations introuvable" }
    )
    
    foreach ($prereq in $Prerequisites) {
        if ($prereq.Command) {
            try {
                $null = Invoke-Expression $prereq.Command 2>&1
                Write-ColorOutput "✓ $($prereq.Name) disponible" -Level Success
            }
            catch {
                Write-ColorOutput "✗ $($prereq.ErrorMsg)" -Level Critical
                throw "Prérequis manquant : $($prereq.Name)"
            }
        }
        elseif ($prereq.Path) {
            if (-not (Test-Path $prereq.Path)) {
                Write-ColorOutput "✗ $($prereq.ErrorMsg) : $($prereq.Path)" -Level Critical
                throw "Fichier manquant : $($prereq.Path)"
            }
            Write-ColorOutput "✓ $($prereq.Name) trouvé" -Level Success
        }
    }
    
    # Vérifier l'espace disque (minimum 5 GB)
    $Drive = (Get-Item $ProjectRoot).PSDrive
    $FreeSpaceGB = [math]::Round((Get-PSDrive $Drive.Name).Free / 1GB, 2)
    
    if ($FreeSpaceGB -lt 5) {
        Write-ColorOutput "Espace disque insuffisant : $FreeSpaceGB GB disponibles (minimum 5 GB requis)" -Level Critical
        throw "Espace disque insuffisant"
    }
    
    Write-ColorOutput "Espace disque disponible : $FreeSpaceGB GB" -Level Info
    Write-ColorOutput "Environnement initialisé avec succès" -Level Success
}

# =============================================================================
# FONCTIONS DE GESTION DES CONFIGURATIONS
# =============================================================================

function Load-GridSearchConfigs {
    <#
    .SYNOPSIS
        Charge les configurations depuis le fichier JSON.
    .OUTPUTS
        PSCustomObject contenant les configurations et métadonnées.
    #>
    
    Write-ColorOutput "Chargement des configurations depuis $ConfigFile..." -Level Info
    
    $ConfigPath = Join-Path $ProjectRoot $ConfigFile
    
    try {
        $ConfigData = Get-Content -Path $ConfigPath -Raw | ConvertFrom-Json
        
        if (-not $ConfigData.configs) {
            throw "Fichier JSON invalide : propriété 'configs' manquante"
        }
        
        $ConfigCount = $ConfigData.configs.Count
        Write-ColorOutput "✓ $ConfigCount configurations chargées" -Level Success
        
        return $ConfigData
    }
    catch {
        Write-ColorOutput "Erreur lors du chargement des configurations : $_" -Level Critical
        throw
    }
}

function Backup-MediumConfig {
    <#
    .SYNOPSIS
        Crée un backup horodaté du fichier medium.yml.
    .OUTPUTS
        Chemin du fichier de backup créé.
    #>
    param(
        [Parameter(Mandatory=$false)]
        [string]$Suffix = "grid_search"
    )
    
    if ($SkipBackup) {
        Write-ColorOutput "⚠️  Backup désactivé (paramètre -SkipBackup)" -Level Warning
        return $null
    }
    
    $BackupPath = "$MediumYmlPath.backup_${Suffix}_$Timestamp"
    
    if ($DryRun) {
        Write-ColorOutput "[DRY-RUN] Création du backup : $BackupPath" -Level Info
        return $BackupPath
    }
    
    try {
        Copy-Item -Path $MediumYmlPath -Destination $BackupPath -Force
        Write-ColorOutput "✓ Backup créé : $BackupPath" -Level Success
        return $BackupPath
    }
    catch {
        Write-ColorOutput "Erreur lors de la création du backup : $_" -Level Critical
        throw
    }
}

function Update-MediumConfig {
    <#
    .SYNOPSIS
        Modifie le fichier medium.yml avec les paramètres d'une configuration.
    .DESCRIPTION
        Remplace les arguments vLLM dans la section command du service vllm-medium.
        Gère dynamiquement l'ajout/suppression de directives selon la configuration.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [PSCustomObject]$Config
    )
    
    Write-ColorOutput "Modification de medium.yml pour la config '$($Config.name)'..." -Level Info
    
    if ($DryRun) {
        Write-ColorOutput "[DRY-RUN] Modification de medium.yml (simulation)" -Level Info
        Write-ColorOutput "  - gpu_memory: $($Config.gpu_memory)" -Level Info
        Write-ColorOutput "  - prefix_caching: $($Config.prefix_caching)" -Level Info
        Write-ColorOutput "  - chunked_prefill: $($Config.chunked_prefill)" -Level Info
        Write-ColorOutput "  - max_num_seqs: $($Config.max_num_seqs)" -Level Info
        Write-ColorOutput "  - max_num_batched_tokens: $($Config.max_num_batched_tokens)" -Level Info
        return
    }
    
    try {
        # Lire le fichier YAML existant
        $YamlContent = Get-Content -Path $MediumYmlPath -Raw
        
        # Extraire la section command du service vllm-medium
        # Pattern pour identifier la section command: >
        $CommandPattern = '(?ms)(command:\s*>\s*\n)(.*?)(?=\n\s{0,2}\w+:|$)'
        
        if ($YamlContent -notmatch $CommandPattern) {
            throw "Impossible de trouver la section 'command:' dans medium.yml"
        }
        
        $CommandHeader = $Matches[1]
        $CommandArgs = $Matches[2]
        
        # Parser les arguments existants (lignes commençant par des espaces + tirets)
        $ArgLines = $CommandArgs -split '\n' | Where-Object { $_ -match '^\s+-\s+' }
        
        # Créer un dictionnaire des arguments actuels
        $CurrentArgs = @{}
        foreach ($line in $ArgLines) {
            if ($line -match '^\s+-\s+"?--([^"]+)"?\s*$') {
                $ArgName = $Matches[1]
                $CurrentArgs[$ArgName] = $line
            }
            elseif ($line -match '^\s+-\s+"?([^-][^"]*)"?\s*$') {
                # Valeur d'argument (ligne suivant un --arg)
                continue
            }
        }
        
        # Construire les nouveaux arguments en format texte libre (compatible avec 'command: >')
        $NewCommandLines = @()
        
        # Arguments de base (toujours présents) - FORMAT CORRIGÉ: texte libre sans tirets
        $NewCommandLines += '      --host 0.0.0.0'
        $NewCommandLines += '      --port ${VLLM_PORT_MEDIUM:-5002}'
        $NewCommandLines += '      --model Qwen/Qwen3-32B-AWQ'
        $NewCommandLines += '      --api-key ${VLLM_API_KEY_MEDIUM}'
        $NewCommandLines += '      --tensor-parallel-size 2'
        
        # gpu-memory-utilization
        $NewCommandLines += "      --gpu-memory-utilization $($Config.gpu_memory)"
        
        # Arguments critiques manquants pour baseline (toujours présents)
        $NewCommandLines += '      --max-model-len 131072'
        $NewCommandLines += '      --quantization awq_marlin'
        $NewCommandLines += '      --kv-cache-dtype fp8'
        $NewCommandLines += '      --dtype ${DTYPE_MEDIUM:-half}'
        $NewCommandLines += '      --enable-auto-tool-choice'
        $NewCommandLines += '      --tool-call-parser qwen3_xml'
        $NewCommandLines += '      --reasoning-parser qwen3'
        $NewCommandLines += '      --distributed-executor-backend=mp'
        $NewCommandLines += '      --rope_scaling ''{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":32768}'''
        $NewCommandLines += '      --swap-space 16'
        
        # enable-prefix-caching (si activé)
        if ($Config.prefix_caching -eq $true) {
            $NewCommandLines += '      --enable-prefix-caching'
        }
        
        # enable-chunked-prefill (si activé)
        if ($Config.chunked_prefill -eq $true) {
            $NewCommandLines += '      --enable-chunked-prefill'
        }
        
        # max-num-seqs (si spécifié)
        if ($Config.max_num_seqs -and $Config.max_num_seqs -ne "null") {
            $NewCommandLines += "      --max-num-seqs $($Config.max_num_seqs)"
        }
        
        # max-num-batched-tokens (si spécifié)
        if ($Config.max_num_batched_tokens -and $Config.max_num_batched_tokens -ne "null") {
            $NewCommandLines += "      --max-num-batched-tokens $($Config.max_num_batched_tokens)"
        }
        
        # Reconstituer la section command
        $NewCommand = $CommandHeader + ($NewCommandLines -join "`n")
        
        # Remplacer dans le contenu YAML
        $NewYamlContent = $YamlContent -replace $CommandPattern, $NewCommand
        
        # Écrire le nouveau fichier
        Set-Content -Path $MediumYmlPath -Value $NewYamlContent -NoNewline
        
        Write-ColorOutput "✓ medium.yml modifié avec succès" -Level Success
    }
    catch {
        Write-ColorOutput "Erreur lors de la modification de medium.yml : $_" -Level Error
        throw
    }
}

function Restore-MediumConfig {
    <#
    .SYNOPSIS
        Restaure le fichier medium.yml depuis un backup.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$BackupPath
    )
    
    if (-not (Test-Path $BackupPath)) {
        Write-ColorOutput "Fichier de backup introuvable : $BackupPath" -Level Warning
        return
    }
    
    if ($DryRun) {
        Write-ColorOutput "[DRY-RUN] Restauration depuis : $BackupPath" -Level Info
        return
    }
    
    try {
        Copy-Item -Path $BackupPath -Destination $MediumYmlPath -Force
        Write-ColorOutput "✓ medium.yml restauré depuis : $BackupPath" -Level Success
    }
    catch {
        Write-ColorOutput "Erreur lors de la restauration : $_" -Level Error
        throw
    }
}

# =============================================================================
# FONCTIONS DE DÉPLOIEMENT DOCKER
# =============================================================================

function Deploy-VLLMService {
    <#
    .SYNOPSIS
        Redéploie le service vLLM avec la nouvelle configuration.
    .OUTPUTS
        Hashtable avec status, startup_time_seconds, logs
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$ConfigName
    )
    
    Write-ColorOutput "Déploiement du service vLLM pour la config '$ConfigName'..." -Level Info
    
    $Result = @{
        status = "unknown"
        startup_time_seconds = 0
        logs = @()
    }
    
    if ($DryRun) {
        Write-ColorOutput "[DRY-RUN] Déploiement simulé" -Level Info
        $Result.status = "success"
        $Result.startup_time_seconds = 10
        return $Result
    }
    
    $StartTime = Get-Date
    
    try {
        # Arrêter le service existant
        Write-ColorOutput "  → Arrêt du service vllm-medium..." -Level Info
        $DownOutput = docker compose -p myia_vllm --env-file "$ProjectRoot\.env" -f $MediumYmlPath down --remove-orphans 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            throw "Échec de docker compose down : $DownOutput"
        }
        
        # Démarrer le nouveau service
        Write-ColorOutput "  → Démarrage du service avec nouvelle configuration..." -Level Info
        $UpOutput = docker compose -p myia_vllm --env-file "$ProjectRoot\.env" -f $MediumYmlPath up -d 2>&1
        
        if ($LASTEXITCODE -ne 0) {
            $Result.status = "failed"
            $Result.logs = $UpOutput
            throw "Échec de docker compose up : $UpOutput"
        }
        
        $EndTime = Get-Date
        $Result.startup_time_seconds = [math]::Round(($EndTime - $StartTime).TotalSeconds, 2)
        $Result.status = "success"
        
        Write-ColorOutput "✓ Service déployé en $($Result.startup_time_seconds)s" -Level Success
        return $Result
    }
    catch {
        $Result.status = "failed"
        $Result.logs += $_.Exception.Message
        Write-ColorOutput "Erreur lors du déploiement : $_" -Level Error
        return $Result
    }
}
function Invoke-CleanupContainers {
    <#
    .SYNOPSIS
        Nettoie TOUS les containers vllm en garantissant qu'aucun orphelin ne subsiste.
    .DESCRIPTION
        Cette fonction assure un nettoyage complet et robuste des containers Docker,
        même en cas d'échec de docker compose down. Utilisée dans le bloc finally
        pour garantir un état propre après chaque configuration testée.
    #>
    param(
        [Parameter(Mandatory=$false)]
        [string]$Context = "cleanup"
    )
    
    Write-ColorOutput "[$Context] Nettoyage complet des containers..." -Level Info
    
    if ($DryRun) {
        Write-ColorOutput "[$Context] [DRY-RUN] Nettoyage simulé" -Level Info
        return $true
    }
    
    try {
        # Étape 1: docker compose down standard
        Write-ColorOutput "[$Context]   → docker compose down..." -Level Info
        $DownOutput = docker compose -p myia_vllm --env-file "$ProjectRoot\.env" -f $MediumYmlPath down --remove-orphans --volumes 2>&1
        
        # Étape 2: Vérifier qu'aucun container myia_vllm ne subsiste
        Write-ColorOutput "[$Context]   → Vérification containers orphelins..." -Level Info
        $RemainingContainers = docker ps -a --filter "name=myia_vllm" --format "{{.Names}}" 2>&1
        
        if ($RemainingContainers -and $RemainingContainers -match "myia_vllm") {
            Write-ColorOutput "[$Context]   ⚠️  Containers orphelins détectés - Suppression forcée..." -Level Warning
            
            $ContainerList = $RemainingContainers -split "`n" | Where-Object { $_ -match "myia_vllm" }
            foreach ($container in $ContainerList) {
                Write-ColorOutput "[$Context]     → Suppression forcée: $container" -Level Warning
                docker rm -f $container 2>&1 | Out-Null
            }
        }
        
        # Étape 3: Vérification finale
        $FinalCheck = docker ps -a --filter "name=myia_vllm" --format "{{.Names}}" 2>&1
        
        if ($FinalCheck -and $FinalCheck -match "myia_vllm") {
            Write-ColorOutput "[$Context]   ✗ ÉCHEC: Des containers subsistent encore!" -Level Error
            return $false
        }
        
        Write-ColorOutput "[$Context]   ✓ Nettoyage terminé - Aucun container orphelin" -Level Success
        return $true
    }
    catch {
        Write-ColorOutput "[$Context]   ✗ Erreur durant le nettoyage: $_" -Level Error
        return $false
    }
}


function Wait-ContainerHealthy {
    <#
    .SYNOPSIS
        Attend que le container vllm-medium soit en état "healthy".
    .OUTPUTS
        Hashtable avec status, health_check_attempts, elapsed_seconds, error_message
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$ConfigName,
        
        [Parameter(Mandatory=$false)]
        [int]$TimeoutSeconds = $DEPLOYMENT_TIMEOUT_SECONDS
    )
    
    Write-ColorOutput "Vérification du health status du container (timeout: ${TimeoutSeconds}s)..." -Level Info
    
    $Result = @{
        status = "unknown"
        health_check_attempts = 0
        elapsed_seconds = 0
        error_message = ""
    }
    
    if ($DryRun) {
        Write-ColorOutput "[DRY-RUN] Vérification health simulée" -Level Info
        $Result.status = "healthy"
        $Result.health_check_attempts = 3
        $Result.elapsed_seconds = 45
        return $Result
    }
    
    $ContainerName = Get-VllmContainerName
    $StartTime = Get-Date
    $TimeoutTime = $StartTime.AddSeconds($TimeoutSeconds)
    
    while ((Get-Date) -lt $TimeoutTime) {
        $Result.health_check_attempts++
        
        # Vérifier l'état du container
        $ContainerInfo = docker ps -a --filter "name=$ContainerName" --format "{{.ID}}|{{.Status}}|{{.State}}" 2>&1
        
        if ($LASTEXITCODE -ne 0 -or -not $ContainerInfo) {
            Write-ColorOutput "  ⚠️  Container non trouvé (tentative $($Result.health_check_attempts))" -Level Warning
            Start-Sleep -Seconds $HEALTH_CHECK_INTERVAL_SECONDS
            continue
        }
        
        $Parts = $ContainerInfo -split '\|'
        $ContainerId = $Parts[0]
        $Status = $Parts[1]
        $State = $Parts[2]
        
        # Vérifier si le container est healthy
        if ($Status -match '\(healthy\)') {
            $EndTime = Get-Date
            $Result.status = "healthy"
            $Result.elapsed_seconds = [math]::Round(($EndTime - $StartTime).TotalSeconds, 2)
            Write-ColorOutput "✓ Container healthy après $($Result.elapsed_seconds)s ($($Result.health_check_attempts) tentatives)" -Level Success
            return $Result
        }
        
        # Vérifier si le container a crashé
        if ($State -eq "exited") {
            $Result.status = "crashed"
            $Result.error_message = "Container a terminé avec l'état: exited"
            
            # Capturer les logs du container
            $LogPath = Join-Path $LogsDir "grid_search_${ConfigName}_crash.txt"
            docker logs $ContainerName --tail 200 > $LogPath 2>&1
            
            Write-ColorOutput "✗ Container crashé - Logs sauvegardés dans : $LogPath" -Level Error
            return $Result
        }
        
        # Afficher la progression
        $ElapsedSeconds = [math]::Round(((Get-Date) - $StartTime).TotalSeconds, 0)
        Write-ColorOutput "  → Health check $($Result.health_check_attempts) : $Status ($ElapsedSeconds/$TimeoutSeconds s)" -Level Info
        
        Start-Sleep -Seconds $HEALTH_CHECK_INTERVAL_SECONDS
    }
    
    # Timeout atteint
    $Result.status = "timeout"
    $Result.elapsed_seconds = $TimeoutSeconds
    $Result.error_message = "Timeout de ${TimeoutSeconds}s dépassé"
    
    Write-ColorOutput "✗ Timeout dépassé après ${TimeoutSeconds}s" -Level Error
    
    # Capturer les logs en cas de timeout
    $LogPath = Join-Path $LogsDir "grid_search_${ConfigName}_timeout.txt"
    docker logs $ContainerName --tail 200 > $LogPath 2>&1
    Write-ColorOutput "Logs sauvegardés dans : $LogPath" -Level Info
    
    return $Result
}

# =============================================================================
# SUITE DE LA FONCTION DANS LA PARTIE 2...
# =============================================================================

# Le script sera divisé en plusieurs parties pour respecter la limite de longueur
# Partie 1: Configuration, utilitaires, gestion configs, déploiement (ci-dessus)
# Partie 2: Exécution tests, sauvegarde résultats, rapport comparatif (à suivre)
# Partie 3: Gestion resumption, workflow principal, point d'entrée (à suivre)

Write-ColorOutput "Script grid_search_optimization.ps1 - Partie 1 chargée" -Level Info

# =============================================================================
# FONCTIONS D'EXÉCUTION DES TESTS
# =============================================================================

function Invoke-PerformanceTests {
    <#
    .SYNOPSIS
        Exécute la suite complète de tests de performance pour une configuration.
    .OUTPUTS
        Hashtable avec les résultats de tous les tests
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$ConfigName
    )
    
    Write-ColorOutput "Exécution des tests de performance pour '$ConfigName'..." -Level Info
    
    $TestResults = @{
        kv_cache_acceleration = @{ status = "not_executed" }
        ttft_performance = @{ status = "not_found" }
        throughput_performance = @{ status = "not_found" }
    }
    
    if ($DryRun) {
        Write-ColorOutput "[DRY-RUN] Tests simulés" -Level Info
        $TestResults.kv_cache_acceleration = @{
            status = "success"
            ttft_cache_miss_ms = 1850
            ttft_cache_hit_ms = 950
            cache_acceleration = 1.95
            gain_percentage = 48.6
        }
        return $TestResults
    }
    
    # Test 1: KV Cache Acceleration (critique)
    $KVCacheScript = Join-Path $ScriptRoot "test_kv_cache_acceleration.ps1"
    
    if (Test-Path $KVCacheScript) {
        Write-ColorOutput "  → Test KV Cache Acceleration..." -Level Info
        
        try {
            $Job = Start-Job -ScriptBlock {
                param($Script, $LogsDir, $ConfigName)
                & $Script *>&1 | Tee-Object -FilePath "$LogsDir\grid_search_${ConfigName}_kv_cache.log"
            } -ArgumentList $KVCacheScript, $LogsDir, $ConfigName
            
            $Completed = Wait-Job $Job -Timeout $TEST_KV_CACHE_TIMEOUT_SECONDS
            
            if ($Completed) {
                $Output = Receive-Job $Job
                Remove-Job $Job -Force
                
                # Parser les métriques depuis la sortie
                $Metrics = Parse-KVCacheOutput -Output $Output
                
                if ($Metrics) {
                    $TestResults.kv_cache_acceleration = $Metrics
                    $TestResults.kv_cache_acceleration.status = "success"
                    
                    Write-ColorOutput "  ✓ KV Cache Test: MISS=$($Metrics.ttft_cache_miss_ms)ms, HIT=$($Metrics.ttft_cache_hit_ms)ms, Accel=x$($Metrics.cache_acceleration)" -Level Success
                }
                else {
                    $TestResults.kv_cache_acceleration.status = "parse_error"
                    Write-ColorOutput "  ⚠️  Impossible de parser les résultats du test KV Cache" -Level Warning
                }
            }
            else {
                Remove-Job $Job -Force
                $TestResults.kv_cache_acceleration.status = "timeout"
                Write-ColorOutput "  ✗ Timeout du test KV Cache ($TEST_KV_CACHE_TIMEOUT_SECONDS s)" -Level Error
            }
        }
        catch {
            $TestResults.kv_cache_acceleration.status = "error"
            $TestResults.kv_cache_acceleration.error_message = $_.Exception.Message
            Write-ColorOutput "  ✗ Erreur lors du test KV Cache : $_" -Level Error
        }
    }
    else {
        Write-ColorOutput "  ⚠️  Script test_kv_cache_acceleration.ps1 introuvable" -Level Warning
    }
    
    # Test 2: TTFT Performance (si script Python existe)
    $TTFTScript = Join-Path $ScriptRoot "test_performance_ttft.py"
    
    if (Test-Path $TTFTScript) {
        Write-ColorOutput "  → Test TTFT Performance..." -Level Info
        
        try {
            $Job = Start-Job -ScriptBlock {
                param($Script, $LogsDir, $ConfigName)
                python $Script *>&1 | Tee-Object -FilePath "$LogsDir\grid_search_${ConfigName}_ttft.log"
            } -ArgumentList $TTFTScript, $LogsDir, $ConfigName
            
            $Completed = Wait-Job $Job -Timeout $TEST_TTFT_TIMEOUT_SECONDS
            
            if ($Completed) {
                $Output = Receive-Job $Job
                Remove-Job $Job -Force
                
                $TestResults.ttft_performance.status = "success"
                $TestResults.ttft_performance.output = $Output -join "`n"
                Write-ColorOutput "  ✓ Test TTFT Performance terminé" -Level Success
            }
            else {
                Remove-Job $Job -Force
                $TestResults.ttft_performance.status = "timeout"
                Write-ColorOutput "  ✗ Timeout du test TTFT ($TEST_TTFT_TIMEOUT_SECONDS s)" -Level Error
            }
        }
        catch {
            $TestResults.ttft_performance.status = "error"
            $TestResults.ttft_performance.error_message = $_.Exception.Message
            Write-ColorOutput "  ✗ Erreur lors du test TTFT : $_" -Level Error
        }
    }
    
    # Test 3: Throughput Performance (si script Python existe)
    $ThroughputScript = Join-Path $ScriptRoot "test_performance_throughput.py"
    
    if (Test-Path $ThroughputScript) {
        Write-ColorOutput "  → Test Throughput Performance..." -Level Info
        
        try {
            $Job = Start-Job -ScriptBlock {
                param($Script, $LogsDir, $ConfigName)
                python $Script *>&1 | Tee-Object -FilePath "$LogsDir\grid_search_${ConfigName}_throughput.log"
            } -ArgumentList $ThroughputScript, $LogsDir, $ConfigName
            
            $Completed = Wait-Job $Job -Timeout $TEST_THROUGHPUT_TIMEOUT_SECONDS
            
            if ($Completed) {
                $Output = Receive-Job $Job
                Remove-Job $Job -Force
                
                $TestResults.throughput_performance.status = "success"
                $TestResults.throughput_performance.output = $Output -join "`n"
                Write-ColorOutput "  ✓ Test Throughput Performance terminé" -Level Success
            }
            else {
                Remove-Job $Job -Force
                $TestResults.throughput_performance.status = "timeout"
                Write-ColorOutput "  ✗ Timeout du test Throughput ($TEST_THROUGHPUT_TIMEOUT_SECONDS s)" -Level Error
            }
        }
        catch {
            $TestResults.throughput_performance.status = "error"
            $TestResults.throughput_performance.error_message = $_.Exception.Message
            Write-ColorOutput "  ✗ Erreur lors du test Throughput : $_" -Level Error
        }
    }
    
    return $TestResults
}

function Parse-KVCacheOutput {
    <#
    .SYNOPSIS
        Parse la sortie du script test_kv_cache_acceleration.ps1 pour extraire les métriques.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string[]]$Output
    )
    
    $FullOutput = $Output -join "`n"
    
    # Patterns pour extraire les métriques
    $Patterns = @{
        ttft_miss = 'Premier message \(MISS\)\s*:\s*(\d+\.?\d*)\s*ms'
        ttft_hit = 'Messages suivants \(HIT\)\s*:\s*(\d+\.?\d*)\s*ms'
        acceleration = 'Accélération\s*:\s*x\s*(\d+\.?\d*)'
        gain = 'Gain.*?(\d+\.?\d*)\s*%'
    }
    
    try {
        $Metrics = @{}
        
        if ($FullOutput -match $Patterns.ttft_miss) {
            $Metrics.ttft_cache_miss_ms = [decimal]$Matches[1]
        }
        
        if ($FullOutput -match $Patterns.ttft_hit) {
            $Metrics.ttft_cache_hit_ms = [decimal]$Matches[1]
        }
        
        if ($FullOutput -match $Patterns.acceleration) {
            $Metrics.cache_acceleration = [decimal]$Matches[1]
        }
        
        if ($FullOutput -match $Patterns.gain) {
            $Metrics.gain_percentage = [decimal]$Matches[1]
        }
        
        # Vérifier que les métriques critiques sont présentes
        if ($Metrics.ttft_cache_miss_ms -and $Metrics.ttft_cache_hit_ms) {
            return $Metrics
        }
        
        return $null
    }
    catch {
        Write-ColorOutput "Erreur lors du parsing des métriques KV Cache : $_" -Level Warning
        return $null
    }
}

# =============================================================================
# FONCTIONS DE SAUVEGARDE DES RÉSULTATS
# =============================================================================

function Save-TestResults {
    <#
    .SYNOPSIS
        Sauvegarde les résultats structurés d'une configuration dans un fichier JSON.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [PSCustomObject]$Config,
        
        [Parameter(Mandatory=$true)]
        [hashtable]$DeploymentResult,
        
        [Parameter(Mandatory=$true)]
        [hashtable]$HealthCheckResult,
        
        [Parameter(Mandatory=$true)]
        [hashtable]$TestResults,
        
        [Parameter(Mandatory=$false)]
        [string[]]$Errors = @()
    )
    
    $ConfigName = $Config.name
    $ResultFile = Join-Path $ResultsDir "grid_search_results_${ConfigName}_$Timestamp.json"
    
    Write-ColorOutput "Sauvegarde des résultats dans $ResultFile..." -Level Info
    
    if ($DryRun) {
        Write-ColorOutput "[DRY-RUN] Sauvegarde simulée" -Level Info
        return
    }
    
    # Construire l'objet de résultats structuré
    $ResultObject = [PSCustomObject]@{
        config_name = $ConfigName
        timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssZ")
        config_params = [PSCustomObject]@{
            gpu_memory = $Config.gpu_memory
            prefix_caching = $Config.prefix_caching
            chunked_prefill = $Config.chunked_prefill
            max_num_seqs = $Config.max_num_seqs
            max_num_batched_tokens = $Config.max_num_batched_tokens
        }
        deployment = $DeploymentResult
        health_check = $HealthCheckResult
        tests = $TestResults
        errors = $Errors
    }
    
    try {
        $ResultObject | ConvertTo-Json -Depth 10 | Set-Content -Path $ResultFile -NoNewline
        Write-ColorOutput "✓ Résultats sauvegardés: $ResultFile" -Level Success
    }
    catch {
        Write-ColorOutput "Erreur lors de la sauvegarde des résultats : $_" -Level Error
    }
}

# =============================================================================
# FONCTIONS DE GÉNÉRATION DU RAPPORT COMPARATIF
# =============================================================================

function New-ComparativeReport {
    <#
    .SYNOPSIS
        Génère un rapport comparatif Markdown avec tous les résultats du grid search.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [PSCustomObject]$ConfigData,
        
        [Parameter(Mandatory=$true)]
        [array]$AllResults
    )
    
    $ReportFile = Join-Path $ResultsDir "grid_search_comparative_report_$Timestamp.md"
    
    Write-ColorOutput "Génération du rapport comparatif..." -Level Info
    
    if ($DryRun) {
        Write-ColorOutput "[DRY-RUN] Génération du rapport simulée" -Level Info
        return
    }
    
    # Baseline de référence
    $Baseline = $ConfigData.baseline_metrics
    
    # Trier les résultats par accélération cache décroissante
    $SortedResults = $AllResults | Where-Object {
        $_.tests.kv_cache_acceleration.status -eq "success"
    } | Sort-Object {
        $_.tests.kv_cache_acceleration.cache_acceleration
    } -Descending
    
    # Construire le rapport Markdown
    $Report = @()
    $Report += "# Grid Search Comparative Report"
    $Report += ""
    $Report += "**Date de Génération** : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    $Report += "**Nombre de Configurations Testées** : $($AllResults.Count)"
    $Report += "**Configurations Réussies** : $($SortedResults.Count)"
    $Report += ""
    $Report += "---"
    $Report += ""
    $Report += "## Baseline de Référence"
    $Report += ""
    $Report += "| Métrique | Valeur |"
    $Report += "|----------|--------|"
    $Report += "| TTFT CACHE MISS | $($Baseline.ttft_miss_ms) ms |"
    $Report += "| TTFT CACHE HIT | $($Baseline.ttft_hit_ms) ms |"
    $Report += "| Cache Acceleration | x$($Baseline.cache_acceleration) |"
    $Report += "| Gain Percentage | $($Baseline.gain_percentage)% |"
    $Report += ""
    $Report += "---"
    $Report += ""
    $Report += "## Tableau Récapitulatif (Trié par Accélération Cache)"
    $Report += ""
    $Report += "| Rank | Config Name | GPU Mem | Prefix | Chunked | Max Seqs | TTFT MISS | TTFT HIT | Accel | Gain % | vs Baseline MISS | vs Baseline HIT |"
    $Report += "|------|-------------|---------|--------|---------|----------|-----------|----------|-------|--------|------------------|-----------------|"
    
    $Rank = 1
    foreach ($result in $SortedResults) {
        $config = $AllResults | Where-Object { $_.config_name -eq $result.config_name } | Select-Object -First 1
        $metrics = $result.tests.kv_cache_acceleration
        
        $gpuMem = $config.config_params.gpu_memory
        $prefix = if ($config.config_params.prefix_caching) { "✅" } else { "❌" }
        $chunked = if ($config.config_params.chunked_prefill) { "✅" } else { "❌" }
        $maxSeqs = if ($config.config_params.max_num_seqs) { $config.config_params.max_num_seqs } else { "-" }
        
        $ttftMiss = [math]::Round($metrics.ttft_cache_miss_ms, 0)
        $ttftHit = [math]::Round($metrics.ttft_cache_hit_ms, 0)
        $accel = [math]::Round($metrics.cache_acceleration, 2)
        $gain = [math]::Round($metrics.gain_percentage, 1)
        
        # Calculs vs baseline
        $vsMiss = [math]::Round((($ttftMiss - $Baseline.ttft_miss_ms) / $Baseline.ttft_miss_ms) * 100, 1)
        $vsHit = [math]::Round((($ttftHit - $Baseline.ttft_hit_ms) / $Baseline.ttft_hit_ms) * 100, 1)
        
        $vsMissFormatted = if ($vsMiss -gt 0) { "+$vsMiss%" } else { "$vsMiss%" }
        $vsHitFormatted = if ($vsHit -gt 0) { "+$vsHit%" } else { "$vsHit%" }
        
        $Report += "| $Rank | $($config.config_name) | $gpuMem | $prefix | $chunked | $maxSeqs | ${ttftMiss}ms | ${ttftHit}ms | x$accel | $gain% | $vsMissFormatted | $vsHitFormatted |"
        $Rank++
    }
    
    $Report += ""
    $Report += "---"
    $Report += ""
    $Report += "## Analyse des Résultats"
    $Report += ""
    
    # Configuration optimale identifiée
    if ($SortedResults.Count -gt 0) {
        $BestConfig = $SortedResults[0]
        $Report += "### 🏆 Configuration Optimale Identifiée"
        $Report += ""
        $Report += "**Nom** : ``$($BestConfig.config_name)``"
        $Report += ""
        $cacheAccelValue = [math]::Round($BestConfig.tests.kv_cache_acceleration.cache_acceleration, 2)
        $Report += "**Raison** : Meilleure accélération cache (x$cacheAccelValue)"
        $Report += ""
        
        # Calcul du gain vs baseline
        $ttftHitReduction = [math]::Round((1 - ($BestConfig.tests.kv_cache_acceleration.ttft_cache_hit_ms / $Baseline.ttft_hit_ms)) * 100, 1)
        $Report += "**Performance** :"
        $Report += "- TTFT CACHE HIT réduit de $ttftHitReduction% vs baseline"
        $Report += "- TTFT CACHE MISS : $([math]::Round($BestConfig.tests.kv_cache_acceleration.ttft_cache_miss_ms, 0)) ms"
        $Report += "- TTFT CACHE HIT : $([math]::Round($BestConfig.tests.kv_cache_acceleration.ttft_cache_hit_ms, 0)) ms"
        $Report += ""
    }
    
    # Échecs et anomalies
    $FailedConfigs = $AllResults | Where-Object {
        $_.tests.kv_cache_acceleration.status -ne "success"
    }
    
    if ($FailedConfigs.Count -gt 0) {
        $Report += "### ⚠️  Échecs et Anomalies"
        $Report += ""
        
        foreach ($failed in $FailedConfigs) {
            $Report += "- **$($failed.config_name)** : $($failed.tests.kv_cache_acceleration.status)"
            
            if ($failed.errors.Count -gt 0) {
                $Report += "  - Erreurs : $($failed.errors -join ', ')"
            }
        }
        
        $Report += ""
    }
    
    # Recommandation finale
    $Report += "### 💡 Recommandation Finale"
    $Report += ""
    
    if ($SortedResults.Count -gt 0) {
        $BestConfig = $SortedResults[0]
        $Report += "**Configuration Recommandée pour Production** : ``$($BestConfig.config_name)``"
        $Report += ""
        $Report += "**Justification** :"
        $finalCacheAccel = [math]::Round($BestConfig.tests.kv_cache_acceleration.cache_acceleration, 2)
        $Report += "- Accélération cache maximale (x$finalCacheAccel)"
        $Report += "- TTFT CACHE HIT optimisé pour agents multi-tours"
        $Report += "- Déploiement stable (health checks réussis)"
    }
    else {
        $Report += "**Aucune configuration optimale identifiée** - Tous les tests ont échoué."
    }
    
    $Report += ""
    $Report += "---"
    $Report += ""
    $Report += "**Fin du Rapport**"
    
    # Écrire le rapport
    try {
        $Report -join "`n" | Set-Content -Path $ReportFile -NoNewline
        Write-ColorOutput "✓ Rapport comparatif généré: $ReportFile" -Level Success
    }
    catch {
        Write-ColorOutput "Erreur lors de la génération du rapport : $_" -Level Error
    }
}

# =============================================================================
# PARTIE 2 TERMINÉE
# =============================================================================

Write-ColorOutput "Script grid_search_optimization.ps1 - Partie 2 chargée" -Level Info

# =============================================================================
# FONCTIONS DE GESTION DE L'ÉTAT DE PROGRESSION (RESUMPTION)
# =============================================================================

function Save-ProgressState {
    <#
    .SYNOPSIS
        Sauvegarde l'état actuel du grid search pour permettre la reprise ultérieure.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [string]$LastCompletedConfig,
        
        [Parameter(Mandatory=$true)]
        [int[]]$CompletedIndices
    )
    
    $ProgressData = [PSCustomObject]@{
        last_completed_config = $LastCompletedConfig
        completed_indices = $CompletedIndices
        timestamp = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssZ")
    }
    
    try {
        $ProgressData | ConvertTo-Json -Depth 5 | Set-Content -Path $ProgressFile -NoNewline
        Write-ColorOutput "✓ État de progression sauvegardé" -Level Info
    }
    catch {
        Write-ColorOutput "⚠️  Impossible de sauvegarder l'état de progression : $_" -Level Warning
    }
}

function Load-ProgressState {
    <#
    .SYNOPSIS
        Charge l'état de progression d'un grid search précédemment interrompu.
    .OUTPUTS
        PSCustomObject avec last_completed_config, completed_indices, timestamp
    #>
    
    if (-not (Test-Path $ProgressFile)) {
        return $null
    }
    
    try {
        $ProgressData = Get-Content -Path $ProgressFile -Raw | ConvertFrom-Json
        
        Write-ColorOutput "État de progression trouvé:" -Level Info
        Write-ColorOutput "  - Dernière config complétée : $($ProgressData.last_completed_config)" -Level Info
        Write-ColorOutput "  - Nombre de configs terminées : $($ProgressData.completed_indices.Count)" -Level Info
        Write-ColorOutput "  - Timestamp : $($ProgressData.timestamp)" -Level Info
        
        return $ProgressData
    }
    catch {
        Write-ColorOutput "⚠️  Impossible de charger l'état de progression : $_" -Level Warning
        return $null
    }
}

function Clear-ProgressState {
    <#
    .SYNOPSIS
        Supprime le fichier d'état de progression.
    #>
    
    if (Test-Path $ProgressFile) {
        try {
            Remove-Item -Path $ProgressFile -Force
            Write-ColorOutput "✓ État de progression nettoyé" -Level Info
        }
        catch {
            Write-ColorOutput "⚠️  Impossible de supprimer l'état de progression : $_" -Level Warning
        }
    }
}

# =============================================================================
# WORKFLOW PRINCIPAL - BOUCLE D'EXÉCUTION DES CONFIGURATIONS
# =============================================================================

function Invoke-GridSearchWorkflow {
    <#
    .SYNOPSIS
        Workflow principal du grid search : teste chaque configuration séquentiellement.
    #>
    param(
        [Parameter(Mandatory=$true)]
        [PSCustomObject]$ConfigData,
        
        [Parameter(Mandatory=$false)]
        [PSCustomObject]$ProgressState = $null
    )
    
    $Configs = $ConfigData.configs
    $TotalConfigs = $Configs.Count
    $AllResults = @()
    
    # Déterminer l'index de démarrage (pour resumption)
    $StartIndex = 0
    $CompletedIndices = @()
    
    if ($ProgressState) {
        $CompletedIndices = [int[]]$ProgressState.completed_indices
        $StartIndex = ($CompletedIndices | Measure-Object -Maximum).Maximum + 1
        
        Write-ColorOutput "Reprise depuis l'index $StartIndex ($(($TotalConfigs - $StartIndex)) configs restantes)" -Level Info
    }
    
    # Créer le backup initial de medium.yml
    $BackupPath = Backup-MediumConfig
    
    try {
        # Boucle sur chaque configuration
        for ($i = $StartIndex; $i -lt $TotalConfigs; $i++) {
            $Config = $Configs[$i]
            $ConfigName = $Config.name
            $ConfigNum = $i + 1
            
            Write-ColorOutput "" -Level Info
            Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Info
            Write-ColorOutput "CONFIGURATION $ConfigNum/$TotalConfigs : $ConfigName" -Level Info
            Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Info
            Write-ColorOutput "" -Level Info
            
            $ConfigErrors = @()
            
            # Étape 1: Modification de medium.yml
            try {
                Update-MediumConfig -Config $Config
            }
            catch {
                $ConfigErrors += "Échec modification medium.yml : $_"
                Write-ColorOutput "✗ Configuration $ConfigName échouée (modification YAML)" -Level Error
                
                # Sauvegarder résultat d'échec et continuer
                $FailedResult = [PSCustomObject]@{
                    config_name = $ConfigName
                    config_params = [PSCustomObject]@{
                        gpu_memory = $Config.gpu_memory
                        prefix_caching = $Config.prefix_caching
                        chunked_prefill = $Config.chunked_prefill
                        max_num_seqs = $Config.max_num_seqs
                        max_num_batched_tokens = $Config.max_num_batched_tokens
                    }
                    deployment = @{ status = "not_attempted" }
                    health_check = @{ status = "not_attempted" }
                    tests = @{ kv_cache_acceleration = @{ status = "not_executed" } }
                    errors = $ConfigErrors
                }
                $AllResults += $FailedResult
                continue
            }
            
            # Étape 2: Redéploiement du service
            $DeploymentResult = Deploy-VLLMService -ConfigName $ConfigName
            
            if ($DeploymentResult.status -ne "success") {
                $ConfigErrors += "Échec déploiement Docker : $($DeploymentResult.logs -join '; ')"
                Write-ColorOutput "✗ Configuration $ConfigName échouée (déploiement)" -Level Error
                
                # Tentative de restauration baseline pour stabiliser le système
                if ($BackupPath) {
                    Write-ColorOutput "Tentative de restauration de la baseline..." -Level Warning
                    try {
                        Restore-MediumConfig -BackupPath $BackupPath
                        Deploy-VLLMService -ConfigName "baseline_recovery" | Out-Null
                    }
                    catch {
                        Write-ColorOutput "⚠️  Échec de restauration baseline : $_" -Level Warning
                    }
                }
                
                $FailedResult = [PSCustomObject]@{
                    config_name = $ConfigName
                    config_params = [PSCustomObject]@{
                        gpu_memory = $Config.gpu_memory
                        prefix_caching = $Config.prefix_caching
                        chunked_prefill = $Config.chunked_prefill
                        max_num_seqs = $Config.max_num_seqs
                        max_num_batched_tokens = $Config.max_num_batched_tokens
                    }
                    deployment = $DeploymentResult
                    health_check = @{ status = "not_attempted" }
                    tests = @{ kv_cache_acceleration = @{ status = "not_executed" } }
                    errors = $ConfigErrors
                }
                $AllResults += $FailedResult
                continue
            }
            
            # Étape 3: Vérification health du container
            $HealthCheckResult = Wait-ContainerHealthy -ConfigName $ConfigName
            
            if ($HealthCheckResult.status -ne "healthy") {
                $ConfigErrors += "Health check échoué : $($HealthCheckResult.error_message)"
                Write-ColorOutput "✗ Configuration $ConfigName échouée (health check)" -Level Error
                
                $FailedResult = [PSCustomObject]@{
                    config_name = $ConfigName
                    config_params = [PSCustomObject]@{
                        gpu_memory = $Config.gpu_memory
                        prefix_caching = $Config.prefix_caching
                        chunked_prefill = $Config.chunked_prefill
                        max_num_seqs = $Config.max_num_seqs
                        max_num_batched_tokens = $Config.max_num_batched_tokens
                    }
                    deployment = $DeploymentResult
                    health_check = $HealthCheckResult
                    tests = @{ kv_cache_acceleration = @{ status = "not_executed" } }
                    errors = $ConfigErrors
                }
                $AllResults += $FailedResult
                continue
            }
            
            # Étape 4: Exécution des tests de performance
            $TestResults = Invoke-PerformanceTests -ConfigName $ConfigName
            
            # Étape 5: Sauvegarde des résultats
            Save-TestResults -Config $Config -DeploymentResult $DeploymentResult -HealthCheckResult $HealthCheckResult -TestResults $TestResults -Errors $ConfigErrors
            
            # Construire l'objet de résultat complet
            $ConfigResult = [PSCustomObject]@{
                config_name = $ConfigName
                config_params = [PSCustomObject]@{
                    gpu_memory = $Config.gpu_memory
                    prefix_caching = $Config.prefix_caching
                    chunked_prefill = $Config.chunked_prefill
                    max_num_seqs = $Config.max_num_seqs
                    max_num_batched_tokens = $Config.max_num_batched_tokens
                }
                deployment = $DeploymentResult
                health_check = $HealthCheckResult
                tests = $TestResults
                errors = $ConfigErrors
            }
            
            $AllResults += $ConfigResult
            
            # Sauvegarder l'état de progression
            $CompletedIndices += $i
            Save-ProgressState -LastCompletedConfig $ConfigName -CompletedIndices $CompletedIndices
            
            Write-ColorOutput "✓ Configuration $ConfigName terminée avec succès" -Level Success
        }
        
        Write-ColorOutput "" -Level Info
        Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Success
        Write-ColorOutput "GRID SEARCH TERMINÉ - Génération du rapport comparatif..." -Level Success
        Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Success
        Write-ColorOutput "" -Level Info
        
        # Générer le rapport comparatif final
        New-ComparativeReport -ConfigData $ConfigData -AllResults $AllResults
        
        # Nettoyer l'état de progression
        Clear-ProgressState
        
        # Restaurer la configuration baseline finale
        if ($BackupPath) {
            Write-ColorOutput "Restauration de la configuration baseline originale..." -Level Info
            Restore-MediumConfig -BackupPath $BackupPath
        }
        
        return $AllResults
    }
    catch {
        Write-ColorOutput "Erreur critique durant le grid search : $_" -Level Critical
        
        # Tentative de restauration en cas d'erreur critique
        if ($BackupPath) {
            Write-ColorOutput "Tentative de restauration d'urgence..." -Level Critical
            try {
                Restore-MediumConfig -BackupPath $BackupPath
                Write-ColorOutput "✓ Configuration baseline restaurée" -Level Success
            }
            catch {
                Write-ColorOutput "✗ Échec de restauration : $_" -Level Critical
            }
        }
        
        throw
    }
    finally {
        # CLEANUP GARANTI - Exécuté TOUJOURS, même en cas d'erreur ou d'interruption
        Write-ColorOutput "" -Level Info
        Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Info
        Write-ColorOutput "CLEANUP FINAL GARANTI" -Level Info
        Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Info
        
        # Nettoyer tous les containers vllm, même orphelins
        $CleanupSuccess = Invoke-CleanupContainers -Context "FINALLY"
        
        if (-not $CleanupSuccess) {
            Write-ColorOutput "⚠️  ATTENTION: Le cleanup final a rencontré des problèmes" -Level Warning
            Write-ColorOutput "    Vérifiez manuellement l'état des containers avec:" -Level Warning
            Write-ColorOutput "    docker ps -a --filter 'name=myia_vllm'" -Level Warning
        }
        
        Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Info
        Write-ColorOutput "" -Level Info
    }
}

# =============================================================================
# POINT D'ENTRÉE PRINCIPAL DU SCRIPT
# =============================================================================

try {
    Write-ColorOutput "" -Level Info
    Write-ColorOutput "╔═══════════════════════════════════════════════════════════════╗" -Level Info
    Write-ColorOutput "║   GRID SEARCH OPTIMIZATION - vLLM Multi-Tours Configuration  ║" -Level Info
    Write-ColorOutput "╚═══════════════════════════════════════════════════════════════╝" -Level Info
    Write-ColorOutput "" -Level Info
    
    # Étape 1: Initialisation de l'environnement
    Initialize-Environment
    
    # Étape 2: Chargement des configurations
    $ConfigData = Load-GridSearchConfigs
    $TotalConfigs = $ConfigData.configs.Count
    
    # Étape 3: Gestion de la resumption
    $ProgressState = $null
    
    if ($Resume) {
        $ProgressState = Load-ProgressState
        
        if (-not $ProgressState) {
            Write-ColorOutput "⚠️  Aucun état de progression trouvé - Démarrage complet" -Level Warning
        }
    }
    
    # Étape 4: Affichage du résumé pré-exécution
    Write-ColorOutput "" -Level Info
    Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Info
    Write-ColorOutput "RÉSUMÉ DU GRID SEARCH" -Level Info
    Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Info
    Write-ColorOutput "Configurations à tester  : $TotalConfigs" -Level Info
    Write-ColorOutput "Fichier de configuration : $ConfigFile" -Level Info
    Write-ColorOutput "Fichier medium.yml       : $MediumYmlPath" -Level Info
    Write-ColorOutput "Répertoire logs          : $LogsDir" -Level Info
    Write-ColorOutput "Répertoire résultats     : $ResultsDir" -Level Info
    
    if ($DryRun) {
        Write-ColorOutput "" -Level Warning
        Write-ColorOutput "MODE DRY-RUN ACTIVÉ - Aucune modification réelle ne sera effectuée" -Level Warning
    }
    
    if ($ProgressState) {
        $RemainingConfigs = $TotalConfigs - $ProgressState.completed_indices.Count
        Write-ColorOutput "" -Level Info
        Write-ColorOutput "MODE REPRISE ACTIVÉ" -Level Info
        Write-ColorOutput "Configs déjà terminées   : $($ProgressState.completed_indices.Count)" -Level Info
        Write-ColorOutput "Configs restantes        : $RemainingConfigs" -Level Info
    }
    
    Write-ColorOutput "" -Level Info
    Write-ColorOutput "Durée estimée            : 3-4 heures ($(6 * $TotalConfigs) à $(11 * $TotalConfigs) minutes)" -Level Info
    Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Info
    Write-ColorOutput "" -Level Info
    
    # Étape 5: Confirmation utilisateur (sauf en mode DryRun)
    if (-not $DryRun) {
        Write-Host "Appuyez sur ENTRÉE pour démarrer le grid search, ou CTRL+C pour annuler..." -ForegroundColor Yellow
        $null = Read-Host
    }
    
    # Étape 6: Lancement du workflow principal
    Write-ColorOutput "" -Level Info
    Write-ColorOutput "DÉMARRAGE DU GRID SEARCH..." -Level Success
    Write-ColorOutput "" -Level Info
    
    $AllResults = Invoke-GridSearchWorkflow -ConfigData $ConfigData -ProgressState $ProgressState
    
    # Étape 7: Résumé final
    Write-ColorOutput "" -Level Success
    Write-ColorOutput "╔═══════════════════════════════════════════════════════════════╗" -Level Success
    Write-ColorOutput "║                    GRID SEARCH TERMINÉ                        ║" -Level Success
    Write-ColorOutput "╚═══════════════════════════════════════════════════════════════╝" -Level Success
    Write-ColorOutput "" -Level Success
    
    $SuccessfulConfigs = $AllResults | Where-Object { $_.tests.kv_cache_acceleration.status -eq "success" }
    $FailedConfigs = $AllResults | Where-Object { $_.tests.kv_cache_acceleration.status -ne "success" }
    
    Write-ColorOutput "Configurations testées    : $($AllResults.Count)" -Level Info
    Write-ColorOutput "Configurations réussies   : $($SuccessfulConfigs.Count)" -Level Success
    Write-ColorOutput "Configurations échouées   : $($FailedConfigs.Count)" -Level Warning
    Write-ColorOutput "" -Level Info
    Write-ColorOutput "Rapport comparatif généré : test_results/grid_search_comparative_report_$Timestamp.md" -Level Success
    Write-ColorOutput "Log principal             : logs/grid_search_$Timestamp.log" -Level Info
    
    if ($SuccessfulConfigs.Count -gt 0) {
        $BestConfig = $SuccessfulConfigs | Sort-Object { $_.tests.kv_cache_acceleration.cache_acceleration } -Descending | Select-Object -First 1
        Write-ColorOutput "" -Level Info
        Write-ColorOutput "🏆 Configuration optimale identifiée : $($BestConfig.config_name)" -Level Success
        Write-ColorOutput "   Accélération cache : x$([math]::Round($BestConfig.tests.kv_cache_acceleration.cache_acceleration, 2))" -Level Success
        Write-ColorOutput "   TTFT CACHE HIT     : $([math]::Round($BestConfig.tests.kv_cache_acceleration.ttft_cache_hit_ms, 0)) ms" -Level Success
    }
    
    Write-ColorOutput "" -Level Info
    Write-ColorOutput "✓ Grid search terminé avec succès" -Level Success
    
    exit 0
}
catch {
    Write-ColorOutput "" -Level Critical
    Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Critical
    Write-ColorOutput "ERREUR CRITIQUE - GRID SEARCH INTERROMPU" -Level Critical
    Write-ColorOutput "═══════════════════════════════════════════════════════════════" -Level Critical
    Write-ColorOutput "" -Level Critical
    Write-ColorOutput "Erreur : $_" -Level Critical
    Write-ColorOutput "Stack Trace : $($_.ScriptStackTrace)" -Level Critical
    Write-ColorOutput "" -Level Critical
    Write-ColorOutput "Pour reprendre le grid search après correction :" -Level Info
    Write-ColorOutput "  .\grid_search_optimization.ps1 -Resume" -Level Info
    Write-ColorOutput "" -Level Critical
    
    exit 1
}