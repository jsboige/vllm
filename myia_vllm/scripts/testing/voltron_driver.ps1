# === VOLTRON HARNESS — driver 0-token (po-2028, machine locale) ===
# Usage : . D:\vllm-data\bench\voltron_driver.ps1
# puis  : VTask classify $texte @{ classes = @("fondations","figure") }
# Doc   : myia_vllm/docs/voltron-harness-adoption.md (§6b) dans le dépôt vllm
$SVC = "http://127.0.0.1:5029"

function VTask($type, $data, $extra) {
  # Une tâche gatée. $extra = hashtable des champs du contrat.
  # classify : @{ classes = @("a","b") }            → answer = {classe, ligne_cle}
  # extract  : @{ fields = @("x"); verbatim = $true; instruction = "..." }
  # numbers  : @{ numbers = @("455"); report_prompt = "..." }
  # diff     : passe $a/$b au lieu de $data : VTask diff $null @{ a = ...; b = ... }
  $body = @{ type = $type } + $(if ($data) { @{ data = $data } } else { @{} }) + $extra |
    ConvertTo-Json -Depth 8 -Compress
  (Invoke-WebRequest -Uri "$SVC/v1/task" -Method POST -ContentType "application/json" `
    -Body $body -TimeoutSec 420).Content | ConvertFrom-Json
  # 420 s ≥ pire cas service (timeout hub 300 s + réparations) — à 180, le
  # client rendait « échec » pendant que la tâche aboutissait côté service
}

function VJob($name, $tasks) {
  # Série en fond (persistée sur disque après chaque tâche) : $tasks = tableau de hashtables.
  # Retourne job_id — relire plus tard : VJobRead <job_id>
  $body = @{ name = $name; tasks = $tasks } | ConvertTo-Json -Depth 8 -Compress
  (Invoke-WebRequest -Uri "$SVC/v1/jobs" -Method POST -ContentType "application/json" `
    -Body $body -TimeoutSec 60).Content | ConvertFrom-Json
}

function VJobRead($jobId) {
  (Invoke-WebRequest -Uri "$SVC/v1/jobs/$jobId" -TimeoutSec 30).Content | ConvertFrom-Json
}

# Champs de la réponse : .ok (bool) · .stage ("a" worker | "c" coordinateur 27B)
#                        .answer (livrable DÉJÀ gaté — c'est lui qu'on consomme)
#                        .detail (pourquoi pas si ok=false) · .turns · .dt_s
