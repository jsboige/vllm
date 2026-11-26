<#
  ddrive_sizes.ps1 - releve de taille par dossier d'un disque (siege po-2028:vllm)
  Lecture seule (robocopy /L = liste, aucune copie). La premiere version a disparu
  avec le retrait de wt-po2028-vllm-599 (26/11) ; la copie durable vit HORS de tout
  worktree (D:\vllm-data\bench\seat-po2028\) et le fichier est aussi commite dans le
  depot (myia_vllm/scripts/monitoring/).

  Modes :
    -Mode snapshot   ecrit <OutDir>\ddrive_sizes_<UTC>.txt
                     (niveau 1 = sous-dossiers de -Root ; niveau 2 = sous-dossiers de -Level2Root)
    -Mode diff       compare les deux derniers releves et rend l'ecart par dossier

  Pieges mesures les 25-26/11, encodes ici :
    - `du` sous Git Bash DROPPE des sous-dossiers => robocopy /L /E /XJ ;
    - le resume robocopy est en FRANCAIS (« Octets : ») et la colonne Ignore peut etre
      negative => regex -?\d+ sur la premiere valeur de la ligne ;
    - robocopy sort 1..7 en cas de succes => le code de sortie n'est pas une erreur ;
    - robocopy SUIVIT les jonctions NTFS sans /XJ => toujours /XJ ;
    - deux releves dans la meme minute s'ecrasient => nom a la seconde + garde de collision ;
    - le tri par NOM met `...Z_2.txt` AVANT `...Z.txt` (tri culturel) => -Mode diff
      ordonne par l'horodatage d'en-tete, suffixe de collision en depart d'egalite ;
    - le bilan additionnait les lignes L1 ET L2 (d:\dev compte alors deux fois) => bilan sur le niveau 1 seul ;
    - en PowerShell, -f est MOINS prioritaire que + => arguments du format entre parentheses.

  Exemples :
    pwsh -NoProfile -File ddrive_sizes.ps1 -Mode snapshot            # mesure 26/11 : 815 s sur 1,4 To, en arriere-plan
    pwsh -NoProfile -File ddrive_sizes.ps1 -Mode diff
#>
[CmdletBinding()]
param(
  [ValidateSet('snapshot','diff')][string]$Mode = 'snapshot',
  [string]$OutDir = 'D:\vllm-data\bench\seat-po2028',
  [string]$Root = 'D:\',
  [string]$Level2Root = 'D:\dev',
  # en dessous de ce seuil un ecart n'est pas liste (bruit : logs, caches)
  [int]$MinDeltaMB = 16,
  # consommation de libre au-dela de laquelle le diff leve une alerte (Go/h)
  [double]$AlertGoPerHour = 20.0
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

function Get-DirBytes {
  param([string]$Path)
  # /L : liste seulement. /XJ : ne pas suivre les jonctions. /BYTES : valeurs brutes.
  $out = robocopy $Path 'NULL' /L /E /XJ /BYTES /NFL /NDL /NJH /NP /NC /R:0 /W:0 2>&1
  $line = $out | Where-Object { $_ -match '^\s*Octets\s*:' } | Select-Object -First 1
  if (-not $line) { $line = $out | Where-Object { $_ -match '^\s*Bytes\s*:' } | Select-Object -First 1 }
  if (-not $line) { return $null }
  $m = [regex]::Match($line, '-?\d+')
  if (-not $m.Success) { return $null }
  return [int64]$m.Value
}

function Get-LevelRows {
  param([string]$Prefix, [string]$Dir)
  $rows = New-Object System.Collections.Generic.List[string]
  $skipped = 0
  if (-not (Test-Path -LiteralPath $Dir)) { return @{ rows = $rows; skipped = $skipped; total = 0 } }
  $dirs = Get-ChildItem -LiteralPath $Dir -Directory -Force -ErrorAction SilentlyContinue
  foreach ($d in $dirs) {
    $b = Get-DirBytes -Path $d.FullName
    if ($null -eq $b) {
      $skipped++
      $rows.Add(("{0}`t{1}`t{2}" -f $Prefix, ($d.FullName.ToLowerInvariant() + '  [NON MESURABLE]'), -1))
      continue
    }
    $rows.Add(("{0}`t{1}`t{2}" -f $Prefix, $d.FullName.ToLowerInvariant(), $b))
    Write-Verbose ('{0} {1} ({2:N2} Go)' -f $Prefix, $d.Name, ($b / 1GB))
  }
  return @{ rows = $rows; skipped = $skipped; total = $dirs.Count }
}

function Read-Snapshot {
  param([System.IO.FileInfo]$F)
  $map = @{}; $free = $null; $utc = $null; $drv = $null
  foreach ($l in [System.IO.File]::ReadAllLines($F.FullName)) {
    if ($l -match '^### utc=(.+?) drive=(\w) free_bytes=(\d+)') {
      $utc = $Matches[1]; $drv = $Matches[2]; $free = [int64]$Matches[3]; continue
    }
    # forme anterieure (26/11 01:29Z, perdue avec le worktree 599) : drive D implicite
    if ($l -match '^### utc=(.+?) D_free_bytes=(\d+)') {
      $utc = $Matches[1]; $drv = 'D'; $free = [int64]$Matches[2]; continue
    }
    $p = $l -split "`t"
    # -1 = non mesurable : jamais compare (un ecart faux vaut moins qu'un ecart absent)
    if ($p.Count -eq 3 -and [int64]$p[2] -ge 0) { $map[$p[1]] = [pscustomobject]@{ Level = $p[0]; Bytes = [int64]$p[2] } }
  }
  return @{ map = $map; free = $free; utc = $utc; drive = $drv; name = $F.Name }
}

function Get-SnapshotTime {
  param([System.IO.FileInfo]$F)
  # L'horodatage d'EN-TETE fait foi ; $null s'il est absent (releve ignore par -Mode diff).
  $first = Get-Content -LiteralPath $F.FullName -TotalCount 1
  if ($first -match '^### utc=(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})') {
    return [DateTimeOffset]::Parse($Matches[1] + 'Z', [Globalization.CultureInfo]::InvariantCulture)
  }
  return $null
}

function Get-CollisionSuffix {
  param([string]$BaseName)
  # `..._2`, `..._10` : garde de collision du mode snapshot ; -1 = releve sans suffixe.
  if ($BaseName -match '_(\d+)$') { return [int]$Matches[1] }
  return -1
}

if ($Mode -eq 'snapshot') {
  $stamp = [DateTimeOffset]::UtcNow
  $drive = $Root.Substring(0, 1).ToUpperInvariant()
  $l1 = Get-LevelRows -Prefix 'L1' -Dir $Root
  $l2 = Get-LevelRows -Prefix 'L2' -Dir $Level2Root

  $free = [int64](Get-PSDrive -Name $drive).Free
  $stem = 'ddrive_sizes_{0}' -f ($stamp.ToString('yyyyMMddTHHmmssZ'))
  $path = Join-Path $OutDir ($stem + '.txt')
  # garde de collision : deux releves dans la meme seconde ne doivent pas s'ecraser
  $i = 1
  while (Test-Path -LiteralPath $path) { $i++; $path = Join-Path $OutDir ($stem + '_' + $i + '.txt') }

  $body = New-Object System.Collections.Generic.List[string]
  $body.Add(('### utc={0}Z drive={1} free_bytes={2}' -f ($stamp.ToString('yyyy-MM-dd HH:mm:ss')), $drive, $free))
  foreach ($r in $l1.rows) { $body.Add($r) }
  foreach ($r in $l2.rows) { $body.Add($r) }
  # UTF-8 sans BOM
  [System.IO.File]::WriteAllText($path, (($body -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))

  $gib = 1GB
  $sum1 = ($l1.rows | ForEach-Object { [int64](($_ -split "`t")[2]) } | Where-Object { $_ -ge 0 } | Measure-Object -Sum).Sum
  $sum2 = ($l2.rows | ForEach-Object { [int64](($_ -split "`t")[2]) } | Where-Object { $_ -ge 0 } | Measure-Object -Sum).Sum
  Write-Output ('snapshot written: {0}' -f $path)
  Write-Output ('rows={0} (niveau 1 : {1} dossier(s) dont {2} non mesurable(s) ; niveau 2 : {3} dossier(s) dont {4} non mesurable(s))' -f ($l1.rows.Count + $l2.rows.Count), $l1.total, $l1.skipped, $l2.total, $l2.skipped)
  Write-Output ('{0}: libre {1:N2} Go | niveau 1 = {2:N1} Go | niveau 2 = {3:N1} Go' -f $drive, ($free / $gib), ($sum1 / $gib), ($sum2 / $gib))
  exit 0
}

if ($Mode -eq 'diff') {
  # Ordre = horodatage d'en-tete, JAMAIS le nom : la garde de collision suffixe
  # `_2`, `_10`... et le tri culturel par nom place `...Z_2.txt` AVANT `...Z.txt`
  # (reproduit le 26/11 sur fixture) => les « deux derniers » etaient deux
  # releves de la meme seconde, sans debit, et le releve reellement precedent
  # n'etait jamais compare. A horodatage egal, le suffixe le plus haut a ete
  # ecrit en second.
  $all = @(Get-ChildItem -LiteralPath $OutDir -File -Filter 'ddrive_sizes_*.txt')
  $sorted = @(
    $all | ForEach-Object { [pscustomobject]@{ File = $_; Time = (Get-SnapshotTime -F $_) } } |
      Where-Object { $null -ne $_.Time } |
      Sort-Object -Property @{ Expression = 'Time'; Descending = $true },
                              @{ Expression = { Get-CollisionSuffix -BaseName $_.File.BaseName }; Descending = $true },
                              @{ Expression = { $_.File.Name }; Descending = $true }
  )
  if ($all.Count -gt $sorted.Count) {
    Write-Output ('### {0} releve(s) sans en-tete lisible ignore(s)' -f ($all.Count - $sorted.Count))
  }
  if ($sorted.Count -lt 2) { Write-Output ('diff impossible: {0} releve(s) lisible(s) dans {1}' -f $sorted.Count, $OutDir); exit 0 }
  $a = Read-Snapshot -F $sorted[0].File
  # Un deuxieme releve de la MEME seconde ne donne aucun debit (« moins de
  # 15 min ») et laissait le releve reellement precedent non compare : on prend
  # le plus recent dont l'horodatage DIFFERE (les suffixes de collision sautent).
  $prev = @($sorted | Select-Object -Skip 1 | Where-Object { $_.Time -ne $sorted[0].Time })
  if ($prev.Count -eq 0) {
    Write-Output 'diff impossible: un seul horodatage distinct parmi les releves lisibles'
    exit 0
  }
  if ($prev.Count -lt ($sorted.Count - 1)) {
    Write-Output ('### {0} releve(s) de la meme seconde que le dernier ignore(s) pour le debit' -f ($sorted.Count - 1 - $prev.Count))
  }
  $b = Read-Snapshot -F $prev[0].File
  $gib = 1GB
  $drv = if ($a.drive) { $a.drive } else { '?' }
  Write-Output ('### avant : {0} | utc={1} | libre {2:N2} Go' -f $b.name, $b.utc, ($b.free / $gib))
  Write-Output ('### apres : {0} | utc={1} | libre {2:N2} Go' -f $a.name, $a.utc, ($a.free / $gib))
  $alert = $false
  if ($null -ne $b.utc -and $null -ne $a.utc -and $null -ne $b.free -and $null -ne $a.free) {
    $tb = [DateTimeOffset]::Parse($b.utc.TrimEnd('Z') + 'Z')
    $ta = [DateTimeOffset]::Parse($a.utc.TrimEnd('Z') + 'Z')
    $mins = ($ta - $tb).TotalMinutes
    $dFree = ($a.free - $b.free) / $gib
    if ($mins -ge 15) {
      # consommation = du libre qui disparait ; negatif = de l'espace regagne
      $rate = -$dFree / ($mins / 60.0)
      Write-Output ('### {0}: libre {1:+0.00;-0.00} Go en {2:N0} min => consommation {3:+0.00;-0.00} Go/h (seuil d alerte {4:N0} Go/h)' -f $drv, $dFree, $mins, $rate, $AlertGoPerHour)
      $alert = ($rate -gt $AlertGoPerHour)
    } else {
      Write-Output ('### {0}: libre {1:+0.00;-0.00} Go en {2:N1} min (moins de 15 min : pas de debit)' -f $drv, $dFree, $mins)
    }
  }

  $min = [int64]$MinDeltaMB * 1MB
  # le niveau (L1/L2) est porte par la 1re colonne de chaque ligne du releve
  $keys = @($b.map.Keys) + @($a.map.Keys) | Sort-Object -Unique
  $delta = foreach ($k in $keys) {
    $bv = 0; $av = 0; $level = 'L1'
    if ($b.map.ContainsKey($k)) { $bv = $b.map[$k].Bytes; $level = $b.map[$k].Level }
    if ($a.map.ContainsKey($k)) { $av = $a.map[$k].Bytes; $level = $a.map[$k].Level }
    [pscustomobject]@{ Level = $level; Path = $k; Before = $bv; After = $av; Delta = $av - $bv }
  }
  $big = @($delta | Where-Object { [Math]::Abs($_.Delta) -ge $min })

  Write-Output ('--- croissance, top 20 (Go : delta, avant -> apres ; ecarts < {0} Mo non listes)' -f $MinDeltaMB)
  $big | Where-Object { $_.Delta -gt 0 } | Sort-Object Delta -Descending | Select-Object -First 20 |
    ForEach-Object { '{0,9:N2} {1,9:N2} -> {2,9:N2}  [{3}] {4}' -f ($_.Delta / $gib), ($_.Before / $gib), ($_.After / $gib), $_.Level, $_.Path }
  Write-Output '--- diminution, top 20'
  $big | Where-Object { $_.Delta -lt 0 } | Sort-Object Delta | Select-Object -First 20 |
    ForEach-Object { '{0,9:N2} {1,9:N2} -> {2,9:N2}  [{3}] {4}' -f ($_.Delta / $gib), ($_.Before / $gib), ($_.After / $gib), $_.Level, $_.Path }

  # Bilan sur le niveau 1 SEULEMENT : les lignes L2 sont deja contenues dans
  # l'agregat `d:\dev` et les additionner avec lui double-compte (1re mesure
  # reelle, 26/11 11:47Z : +36,22 Go annonces pour -18,58 Go reellement
  # perdus). Les listes par dossier gardent les deux niveaux, le bilan non ;
  # `libre` reste la reference physique.
  $lvl1 = @($big | Where-Object { $_.Level -eq 'L1' })
  $grown = ($lvl1 | Where-Object { $_.Delta -gt 0 } | Measure-Object Delta -Sum).Sum
  $shrunk = ($lvl1 | Where-Object { $_.Delta -lt 0 } | Measure-Object Delta -Sum).Sum
  Write-Output ('--- bilan niveau 1 des ecarts listes : +{0:N2} Go / {1:N2} Go => net {2:+0.00;-0.00} Go ; libre {3:+0.00;-0.00} Go' -f ($grown / $gib), ($shrunk / $gib), (($grown + $shrunk) / $gib), (($a.free - $b.free) / $gib))
  if ($alert) { Write-Output ('### ALERTE : consommation au-dela de {0:N0} Go/h' -f $AlertGoPerHour) }
  exit 0
}
