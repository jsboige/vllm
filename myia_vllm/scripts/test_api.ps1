# Test API vLLM Medium
$headers = @{
    "Authorization" = "Bearer Y7PSM158SR952HCAARSLQ344RRPJTDI3"
    "Content-Type" = "application/json"
}

$body = @{
    model = "Qwen/Qwen3-32B-AWQ"
    messages = @(
        @{
            role = "user"
            content = "Respond with just OK"
        }
    )
    max_tokens = 5
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "http://localhost:5002/v1/chat/completions" -Method POST -Headers $headers -Body $body -TimeoutSec 10
    Write-Host "API Response: $($response.choices[0].message.content)" -ForegroundColor Green
    Write-Host "Model: $($response.model)" -ForegroundColor Cyan
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
}