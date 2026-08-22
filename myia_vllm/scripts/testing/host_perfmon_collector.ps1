# Host-side counter collector for the machine-throughput investigation (2026-08-22).
# Locale-neutral (WMI formatted-data classes; typeperf/Get-Counter English paths fail on French hosts).
# Usage: powershell -NoProfile -File host_perfmon_collector.ps1 [-OutputPath <csv>] [-Minutes <n>]
#        Run in background WHILE benching (ab_bench.py legs), then correlate per-phase.
# NOTE: launching via a tool with a 2-min command timeout kills it early — pass a >=10 min timeout
# or run from a terminal. Top-procs are per-process CPU cores (delta of cumulative CPU seconds).
param(
  [string]$OutputPath = "$PWD\host_perfmon_round.csv",
  [int]$Minutes = 30
)
$out = $OutputPath
[System.IO.File]::WriteAllText($out, "epoch,cpu_total,cores_busy,disk_r_bps,disk_w_bps,disk_q,commit_pct,top_procs`n", [System.Text.UTF8Encoding]::new($false))
$end = (Get-Date).AddMinutes($Minutes)
$ncpu = [Environment]::ProcessorCount
$prev = $null
$prevT = $null
while ((Get-Date) -lt $end) {
  try {
    $epoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $cpu = (Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'").PercentProcessorTime
    $d = Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk -Filter "Name='_Total'"
    $mem = Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
    $commit = $mem.PercentCommittedBytesInUse

    $now = @{}
    $nowT = Get-Date
    foreach ($p in Get-Process) {
      try { if ($p.CPU -ne $null) { $now[[string]$p.Id] = @{ n = $p.ProcessName; c = [double]$p.CPU } } } catch {}
    }
    $top = ""
    if ($prev -ne $null) {
      $dt = ($nowT - $prevT).TotalSeconds
      if ($dt -gt 0) {
        $deltas = foreach ($k in $now.Keys) {
          if ($prev.ContainsKey($k)) {
            $dd = $now[$k].c - $prev[$k].c
            if ($dd -gt 0.05) { [PSCustomObject]@{ n = $now[$k].n; cores = $dd / $dt } }
          }
        }
        $top = ($deltas | Sort-Object cores -Descending | Select-Object -First 5 | ForEach-Object { "$($_.n):$([math]::Round($_.cores,2))" }) -join " "
      }
    }
    $prev = $now; $prevT = $nowT
    $cores = [math]::Round($ncpu * $cpu / 100.0, 2)
    $line = "$epoch,$cpu,$cores,$($d.DiskReadBytesPersec),$($d.DiskWriteBytesPersec),$($d.CurrentDiskQueueLength),$commit,`"$top`""
    [System.IO.File]::AppendAllText($out, $line + "`n", [System.Text.UTF8Encoding]::new($false))
  } catch {}
  Start-Sleep -Seconds 3
}
