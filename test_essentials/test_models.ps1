# Multi-Model Test Script for AWS MCP Chatbot
# Tests different Bedrock models to compare performance and capabilities

Write-Host "🤖 Testing Multi-Model Bedrock Support..." -ForegroundColor Green

# Get API endpoint
$apiUrl = Read-Host "Enter your API Gateway URL (e.g., https://abc123.execute-api.us-east-1.amazonaws.com/dev)"

if (-not $apiUrl) {
    Write-Host "❌ API URL is required" -ForegroundColor Red
    exit 1
}

# Test message for consistent comparison
$testMessage = "I'm having trouble with my account login. I've tried resetting my password twice but the emails aren't coming through. I need to access my account urgently for a business meeting tomorrow. Can you help me with alternative solutions?"

# Models to test (these should match your SAM deployment)
$models = @(
    @{
        name = "Amazon Nova Lite"
        id = "amazon.nova-lite-v1:0"
        description = "Fast, cost-effective (Default)"
        use_case = "Balanced workloads"
    },
    @{
        name = "Amazon Nova Micro"
        id = "amazon.nova-micro-v1:0"
        description = "Ultra-fast responses"
        use_case = "High-volume scenarios"
    },
    @{
        name = "Amazon Nova Pro"
        id = "amazon.nova-pro-v1:0"
        description = "High-quality responses"
        use_case = "Complex reasoning"
    },
    @{
        name = "Claude 3.5 Sonnet"
        id = "anthropic.claude-3-5-sonnet-20241022-v2:0"
        description = "Advanced reasoning"
        use_case = "Complex analysis"
    },
    @{
        name = "Claude 3.5 Haiku"
        id = "anthropic.claude-3-5-haiku-20241022-v1:0"
        description = "Fast responses"
        use_case = "Interactive chat"
    },
    @{
        name = "Llama 3.2 11B"
        id = "meta.llama3-2-11b-instruct-v1:0"
        description = "Balanced performance"
        use_case = "Open source preference"
    }
)

Write-Host "🧪 Testing $($models.Count) different Bedrock models..." -ForegroundColor Blue
Write-Host "Test Message: $testMessage" -ForegroundColor Gray
Write-Host ""

# Function to test a model
function Test-Model {
    param(
        [string]$ModelName,
        [string]$ModelId,
        [string]$Description,
        [string]$UseCase,
        [string]$Message,
        [string]$ApiUrl
    )
    
    Write-Host "🔧 Testing $ModelName ($ModelId)" -ForegroundColor Cyan
    Write-Host "   Description: $Description" -ForegroundColor Gray
    Write-Host "   Best for: $UseCase" -ForegroundColor Gray
    
    $startTime = Get-Date
    
    $chatBody = @{
        jsonrpc = "2.0"
        id = "model-test-$(Get-Random)"
        method = "tools/call"
        params = @{
            name = "chat_with_ai"
            arguments = @{
                message = $Message
                conversation_id = "model_test_$($ModelId.Replace('.', '_').Replace(':', '_').Replace('-', '_'))"
                user_id = "model_test_user"
            }
        }
    } | ConvertTo-Json -Depth 10
    
    try {
        $response = Invoke-RestMethod -Uri "$ApiUrl/mcp" -Method Post -ContentType "application/json" -Body $chatBody
        $endTime = Get-Date
        $duration = ($endTime - $startTime).TotalMilliseconds
        
        Write-Host "   ✅ SUCCESS - Response time: $([math]::Round($duration, 0))ms" -ForegroundColor Green
        
        $chatResult = $response.result.content[0].text | ConvertFrom-Json
        $responseText = $chatResult.response
        $wordCount = ($responseText -split '\s+').Count
        
        Write-Host "   📝 Response length: $wordCount words" -ForegroundColor Yellow
        Write-Host "   🎯 Response preview: $($responseText.Substring(0, [Math]::Min(100, $responseText.Length)))..." -ForegroundColor White
        
        # Return results for comparison
        return @{
            Model = $ModelName
            ModelId = $ModelId
            Success = $true
            ResponseTime = [math]::Round($duration, 0)
            WordCount = $wordCount
            Response = $responseText
        }
        
    } catch {
        $endTime = Get-Date
        $duration = ($endTime - $startTime).TotalMilliseconds
        
        Write-Host "   ❌ FAILED - Error after $([math]::Round($duration, 0))ms" -ForegroundColor Red
        Write-Host "   Error: $($_.Exception.Message)" -ForegroundColor Red
        
        return @{
            Model = $ModelName
            ModelId = $ModelId
            Success = $false
            ResponseTime = [math]::Round($duration, 0)
            Error = $_.Exception.Message
        }
    }
    
    Write-Host ""
}

# Test all models
$results = @()
foreach ($model in $models) {
    $result = Test-Model -ModelName $model.name -ModelId $model.id -Description $model.description -UseCase $model.use_case -Message $testMessage -ApiUrl $apiUrl
    $results += $result
    Start-Sleep -Seconds 2  # Brief pause between tests
}

# Display summary
Write-Host "📊 MODEL COMPARISON SUMMARY" -ForegroundColor Green
Write-Host "=" * 80
Write-Host ""

# Successful tests
$successfulTests = $results | Where-Object { $_.Success -eq $true }
if ($successfulTests.Count -gt 0) {
    Write-Host "✅ SUCCESSFUL TESTS:" -ForegroundColor Green
    $successfulTests | Sort-Object ResponseTime | ForEach-Object {
        Write-Host "   $($_.Model): $($_.ResponseTime)ms, $($_.WordCount) words" -ForegroundColor White
    }
    Write-Host ""
    
    # Performance analysis
    $fastestModel = $successfulTests | Sort-Object ResponseTime | Select-Object -First 1
    $slowestModel = $successfulTests | Sort-Object ResponseTime | Select-Object -Last 1
    $mostVerboseModel = $successfulTests | Sort-Object WordCount -Descending | Select-Object -First 1
    $mostConciseModel = $successfulTests | Sort-Object WordCount | Select-Object -First 1
    
    Write-Host "🏆 PERFORMANCE HIGHLIGHTS:" -ForegroundColor Yellow
    Write-Host "   Fastest Response: $($fastestModel.Model) ($($fastestModel.ResponseTime)ms)" -ForegroundColor Cyan
    Write-Host "   Most Detailed: $($mostVerboseModel.Model) ($($mostVerboseModel.WordCount) words)" -ForegroundColor Cyan
    Write-Host "   Most Concise: $($mostConciseModel.Model) ($($mostConciseModel.WordCount) words)" -ForegroundColor Cyan
    Write-Host ""
}

# Failed tests
$failedTests = $results | Where-Object { $_.Success -eq $false }
if ($failedTests.Count -gt 0) {
    Write-Host "❌ FAILED TESTS:" -ForegroundColor Red
    $failedTests | ForEach-Object {
        Write-Host "   $($_.Model): $($_.Error)" -ForegroundColor Red
    }
    Write-Host ""
}

# Recommendations
Write-Host "💡 RECOMMENDATIONS:" -ForegroundColor Magenta
Write-Host ""
if ($successfulTests.Count -gt 0) {
    $avgResponseTime = ($successfulTests | Measure-Object -Property ResponseTime -Average).Average
    $fastModels = $successfulTests | Where-Object { $_.ResponseTime -lt $avgResponseTime }
    $detailedModels = $successfulTests | Sort-Object WordCount -Descending | Select-Object -First 2
    
    Write-Host "   For HIGH-VOLUME scenarios (speed priority):" -ForegroundColor Yellow
    $fastModels | ForEach-Object {
        Write-Host "     • $($_.Model) - $($_.ResponseTime)ms response time" -ForegroundColor White
    }
    Write-Host ""
    
    Write-Host "   For COMPLEX QUERIES (detail priority):" -ForegroundColor Yellow
    $detailedModels | ForEach-Object {
        Write-Host "     • $($_.Model) - $($_.WordCount) words average" -ForegroundColor White
    }
    Write-Host ""
}

Write-Host "🔧 TO SWITCH MODELS:" -ForegroundColor Cyan
Write-Host "   sam deploy --parameter-overrides BedrockModelId=MODEL_ID" -ForegroundColor White
Write-Host ""
Write-Host "🎯 Test completed! Use these results to choose the best model for your use case." -ForegroundColor Green
