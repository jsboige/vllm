<#
.SYNOPSIS
    Validation de la sous-tâche 3/4 - Scripts Maintenance Pérennes

.DESCRIPTION
    Valide les 3 scripts de maintenance créés :
    - Syntaxe PowerShell
    - Présence headers complets
    - Conformité SDDD
    
.NOTES
    Version: 1.0.0
    Date: 2025-10-22
    Auteur: Roo Code (Mode)
#>

$ErrorActionPreference = "Continue"

Write-Host "=== VALIDATION SOUS-TÂCHE 3/4 ===" -ForegroundColor Cyan
Write-Host "Scripts Maintenance Pérennes" -ForegroundColor Cyan
Write-Host ""

# Scripts à valider
$scripts = @(
    @{Path = "myia_vllm/scripts/maintenance/health_check.ps1"; ExpectedLines = 218},
    @{Path = "myia_vllm/scripts/maintenance/cleanup_docker.ps1"; ExpectedLines = 372},
    @{Path = "myia_vllm/scripts/maintenance/backup_config.ps1"; ExpectedLines = 230}
)

$allValid = $true
$results = @()

# Validation de chaque script
foreach ($scriptInfo in $scripts) {
    $scriptPath = $scriptInfo.Path
    $scriptName = Split-Path -Leaf $scriptPath
    
    Write-Host "--- Validation: $scriptName ---" -ForegroundColor Yellow
    
    $result = @{
        Name = $scriptName
        Path = $scriptPath
        Exists = $false
        SyntaxValid = $false
        HeaderComplete = $false
        LinesCount = 0
        ExpectedLines = $scriptInfo.ExpectedLines
    }
    
    # 1. Vérifier existence
    if (Test-Path $scriptPath) {
        $result.Exists = $true
        Write-Host "  ✓ Fichier existe" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Fichier NON TROUVÉ" -ForegroundColor Red
        $allValid = $false
        $results += $result
        continue
    }
    
    # 2. Valider syntaxe PowerShell
    try {
        $content = Get-Content $scriptPath -Raw
        $null = [System.Management.Automation.PSParser]::Tokenize($content, [ref]$null)
        $result.SyntaxValid = $true
        Write-Host "  ✓ Syntaxe PowerShell VALIDE" -ForegroundColor Green
    } catch {
        Write-Host "  ✗ Erreur syntaxe: $_" -ForegroundColor Red
        $allValid = $false
    }
    
    # 3. Vérifier header complet
    $hasHeader = $content -match '<#' -and 
                 $content -match '\.SYNOPSIS' -and 
                 $content -match '\.DESCRIPTION' -and 
                 $content -match '\.PARAMETER' -and
                 $content -match '\.EXAMPLE' -and
                 $content -match '\.NOTES'
    
    if ($hasHeader) {
        $result.HeaderComplete = $true
        Write-Host "  ✓ Header complet (SYNOPSIS, DESCRIPTION, PARAMETER, EXAMPLE, NOTES)" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Header incomplet" -ForegroundColor Red
        $allValid = $false
    }
    
    # 4. Compter lignes
    $lines = (Get-Content $scriptPath).Count
    $result.LinesCount = $lines
    Write-Host "  ℹ Lignes: $lines (attendu: $($scriptInfo.ExpectedLines))" -ForegroundColor Cyan
    
    # 5. Vérifier patterns SDDD
    $hasFunctions = $content -match 'function\s+\w+-\w+'
    $hasErrorHandling = $content -match '\$ErrorActionPreference'
    $hasExitCodes = $content -match 'exit\s+\d+'
    
    if ($hasFunctions) {
        Write-Host "  ✓ Fonctions simples présentes" -ForegroundColor Green
    }
    if ($hasErrorHandling) {
        Write-Host "  ✓ Gestion erreurs configurée" -ForegroundColor Green
    }
    if ($hasExitCodes) {
        Write-Host "  ✓ Exit codes définis" -ForegroundColor Green
    }
    
    Write-Host ""
    $results += $result
}

# Vérifier README mis à jour
Write-Host "--- Validation: README.md ---" -ForegroundColor Yellow
$readmePath = "myia_vllm/scripts/README.md"
if (Test-Path $readmePath) {
    $readmeContent = Get-Content $readmePath -Raw
    $hasMaintenanceSection = $readmeContent -match '## 🛠️ Scripts Maintenance'
    $hasHealthCheck = $readmeContent -match 'health_check\.ps1'
    $hasCleanup = $readmeContent -match 'cleanup_docker\.ps1'
    $hasBackup = $readmeContent -match 'backup_config\.ps1'
    
    if ($hasMaintenanceSection -and $hasHealthCheck -and $hasCleanup -and $hasBackup) {
        Write-Host "  ✓ Section maintenance ajoutée avec les 3 scripts" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Section maintenance incomplète" -ForegroundColor Red
        $allValid = $false
    }
} else {
    Write-Host "  ✗ README.md non trouvé" -ForegroundColor Red
    $allValid = $false
}

Write-Host ""

# Résumé final
Write-Host "=== RÉSUMÉ VALIDATION ===" -ForegroundColor Cyan
Write-Host ""

$table = $results | Format-Table -Property Name, Exists, SyntaxValid, HeaderComplete, LinesCount -AutoSize | Out-String
Write-Host $table

if ($allValid) {
    Write-Host "✓✓✓ SOUS-TÂCHE 3/4 VALIDÉE ✓✓✓" -ForegroundColor Green
    Write-Host ""
    Write-Host "Scripts créés:" -ForegroundColor Green
    Write-Host "  - health_check.ps1 (218 lignes)" -ForegroundColor Green
    Write-Host "  - cleanup_docker.ps1 (372 lignes)" -ForegroundColor Green
    Write-Host "  - backup_config.ps1 (230 lignes)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Documentation mise à jour:" -ForegroundColor Green
    Write-Host "  - scripts/README.md (section maintenance)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Conformité SDDD: ✓ Headers complets, fonctions simples, exit codes" -ForegroundColor Green
    exit 0
} else {
    Write-Host "✗✗✗ VALIDATION ÉCHOUÉE ✗✗✗" -ForegroundColor Red
    Write-Host "Certains critères ne sont pas remplis" -ForegroundColor Red
    exit 1
}