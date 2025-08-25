# MCP Server Test Script (PowerShell)
# Tests multi-model Bedrock support with MCP protocol

Write-Host "🚀 Testing Multi-Model MCP Server Implementation..." -ForegroundColor Green

# Test MCP Server endpoints
$apiUrl = Read-Host "Enter your API Gateway URL (e.g., https://abc123.execute-api.us-east-1.amazonaws.com/dev)"

if (-not $apiUrl) {
    Write-Host "❌ API URL is required" -ForegroundColor Red
    exit 1
}

Write-Host "📋 Testing MCP Protocol Implementation with Multi-Model Support..." -ForegroundColor Blue

# Test 1: Initialize
Write-Host "`n1. Testing MCP Initialize..." -ForegroundColor Cyan
$initBody = @{
    jsonrpc = "2.0"
    id = "1"
    method = "initialize"
    params = @{
        protocolVersion = "2024-11-05"
        capabilities = @{}
        clientInfo = @{
            name = "Multi-Model MCP Test Client"
            version = "2.0.0"
        }
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "$apiUrl/mcp" -Method Post -ContentType "application/json" -Body $initBody
    Write-Host "✅ Initialize successful" -ForegroundColor Green
    Write-Host "Server: $($response.result.serverInfo.name) v$($response.result.serverInfo.version)"
} catch {
    Write-Host "❌ Initialize failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 2: List Tools
Write-Host "`n2. Testing Tools List..." -ForegroundColor Cyan
$toolsBody = @{
    jsonrpc = "2.0"
    id = "2"
    method = "tools/list"
    params = @{}
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "$apiUrl/mcp" -Method Post -ContentType "application/json" -Body $toolsBody
    Write-Host "✅ Tools list successful" -ForegroundColor Green
    Write-Host "Available tools:"
    foreach ($tool in $response.result.tools) {
        Write-Host "  - $($tool.name): $($tool.description)"
    }
} catch {
    Write-Host "❌ Tools list failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 3: Chat with AI (New Tool Name)
Write-Host "`n3. Testing Chat with AI (New Tool Name)..." -ForegroundColor Cyan
$chatBody = @{
    jsonrpc = "2.0"
    id = "3"
    method = "tools/call"
    params = @{
        name = "chat_with_ai"
        arguments = @{
            message = "Hello, I need help with password reset. Testing the new chat_with_ai tool."
            conversation_id = "test_conv_001"
            user_id = "test_user_123"
        }
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "$apiUrl/mcp" -Method Post -ContentType "application/json" -Body $chatBody
    Write-Host "✅ Chat with AI successful" -ForegroundColor Green
    $chatResult = $response.result.content[0].text | ConvertFrom-Json
    Write-Host "Response: $($chatResult.response)"
    Write-Host "Conversation ID: $($chatResult.conversation_id)"
    Write-Host "Model Used: $($chatResult.model_id -or 'Default Bedrock Model')"
} catch {
    Write-Host "❌ Chat with AI failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 3.5: Test Backward Compatibility
Write-Host "`n3.5. Testing Backward Compatibility (Old Tool Name)..." -ForegroundColor Cyan
$chatOldBody = @{
    jsonrpc = "2.0"
    id = "3.5"
    method = "tools/call"
    params = @{
        name = "chat_with_nova"
        arguments = @{
            message = "Testing backward compatibility with the old chat_with_nova tool name."
            conversation_id = "test_conv_002"
            user_id = "test_user_123"
        }
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "$apiUrl/mcp" -Method Post -ContentType "application/json" -Body $chatOldBody
    Write-Host "✅ Backward compatibility successful" -ForegroundColor Green
    $chatResult = $response.result.content[0].text | ConvertFrom-Json
    Write-Host "Response: $($chatResult.response)"
    Write-Host "Note: Old tool name 'chat_with_nova' still works for backward compatibility"
} catch {
    Write-Host "❌ Backward compatibility failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 4: Sampling
Write-Host "`n4. Testing Sampling/CreateMessage..." -ForegroundColor Cyan
$samplingBody = @{
    jsonrpc = "2.0"
    id = "4"
    method = "sampling/createMessage"
    params = @{
        messages = @(
            @{
                role = "user"
                content = @{
                    type = "text"
                    text = "I'm having trouble logging into my account. Can you help me?"
                }
            }
        )
        maxTokens = 500
        temperature = 0.7
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "$apiUrl/mcp" -Method Post -ContentType "application/json" -Body $samplingBody
    Write-Host "✅ Sampling successful" -ForegroundColor Green
    Write-Host "Response: $($response.result.content.text)"
} catch {
    Write-Host "❌ Sampling failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 5: Resources
Write-Host "`n5. Testing Resources List..." -ForegroundColor Cyan
$resourcesBody = @{
    jsonrpc = "2.0"
    id = "5"
    method = "resources/list"
    params = @{}
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "$apiUrl/mcp" -Method Post -ContentType "application/json" -Body $resourcesBody
    Write-Host "✅ Resources list successful" -ForegroundColor Green
    Write-Host "Available resources:"
    foreach ($resource in $response.result.resources) {
        Write-Host "  - $($resource.uri): $($resource.name)"
    }
} catch {
    Write-Host "❌ Resources list failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Test 6: Prompts
Write-Host "`n6. Testing Prompts List..." -ForegroundColor Cyan
$promptsBody = @{
    jsonrpc = "2.0"
    id = "6"
    method = "prompts/list"
    params = @{}
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-RestMethod -Uri "$apiUrl/mcp" -Method Post -ContentType "application/json" -Body $promptsBody
    Write-Host "✅ Prompts list successful" -ForegroundColor Green
    Write-Host "Available prompts:"
    foreach ($prompt in $response.result.prompts) {
        Write-Host "  - $($prompt.name): $($prompt.description)"
    }
} catch {
    Write-Host "❌ Prompts list failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n🎉 Multi-Model MCP Protocol Testing Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Next Steps:" -ForegroundColor Yellow
Write-Host "1. Use the MCP client: python mcp_client.py"
Write-Host "2. Test WebSocket server: python mcp_server.py"
Write-Host "3. Test different models with test_events_models.json"
Write-Host "4. Run complete workflow tests with test_mcp_complete.json"
Write-Host "5. Integrate with MCP-compatible clients"
Write-Host ""
Write-Host "🤖 Supported Bedrock Models:" -ForegroundColor Magenta
Write-Host "Amazon Nova: nova-lite-v1:0, nova-micro-v1:0, nova-pro-v1:0"
Write-Host "Anthropic Claude: claude-3-5-sonnet, claude-3-5-haiku, claude-3-opus"
Write-Host "Meta Llama: llama3-2-90b, llama3-2-11b, llama3-2-3b"
Write-Host ""
Write-Host "🔧 Configure Model:" -ForegroundColor Cyan
Write-Host "Set BEDROCK_MODEL_ID environment variable or use SAM parameter:"
Write-Host "sam deploy --parameter-overrides BedrockModelId=anthropic.claude-3-5-sonnet-20241022-v2:0"
Write-Host ""
Write-Host "🔗 Endpoints:" -ForegroundColor Magenta
Write-Host "MCP Server: $apiUrl/mcp"
