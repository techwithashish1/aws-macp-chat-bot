import json
import asyncio
import websockets
import boto3
import uuid
from datetime import datetime
import logging
from typing import Dict, Any, Optional, List
import traceback

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize AWS services
dynamodb = boto3.resource('dynamodb')
conversations_table = dynamodb.Table('MCPConversations')
bedrock_runtime = boto3.client('bedrock-runtime')

# Get model configuration from environment variables
import os
DEFAULT_MODEL = "amazon.nova-lite-v1:0"
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', DEFAULT_MODEL)

# MCP Protocol Constants
MCP_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"

class MCPServer:
    def __init__(self):
        self.clients = set()
        self.capabilities = {
            "tools": {},
            "resources": {},
            "prompts": {},
            "experimental": {
                "sampling": True
            }
        }
        
    async def handle_client(self, websocket, path):
        """Handle incoming MCP client connections"""
        logger.info(f"New MCP client connected from {websocket.remote_address}")
        self.clients.add(websocket)
        
        try:
            async for message in websocket:
                try:
                    await self.process_message(websocket, message)
                except Exception as e:
                    logger.error(f"Error processing message: {str(e)}")
                    await self.send_error(websocket, "internal_error", str(e))
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {websocket.remote_address} disconnected")
        finally:
            self.clients.discard(websocket)
    
    async def process_message(self, websocket, message: str):
        """Process incoming MCP messages"""
        try:
            data = json.loads(message)
            method = data.get("method")
            params = data.get("params", {})
            id_val = data.get("id")
            
            logger.info(f"Processing MCP method: {method}")
            
            if method == "initialize":
                await self.handle_initialize(websocket, params, id_val)
            elif method == "notifications/initialized":
                await self.handle_initialized(websocket)
            elif method == "tools/list":
                await self.handle_tools_list(websocket, id_val)
            elif method == "tools/call":
                await self.handle_tools_call(websocket, params, id_val)
            elif method == "resources/list":
                await self.handle_resources_list(websocket, id_val)
            elif method == "resources/read":
                await self.handle_resources_read(websocket, params, id_val)
            elif method == "prompts/list":
                await self.handle_prompts_list(websocket, id_val)
            elif method == "prompts/get":
                await self.handle_prompts_get(websocket, params, id_val)
            elif method == "sampling/createMessage":
                await self.handle_sampling_create_message(websocket, params, id_val)
            else:
                await self.send_error(websocket, "method_not_found", f"Unknown method: {method}", id_val)
                
        except json.JSONDecodeError:
            await self.send_error(websocket, "parse_error", "Invalid JSON")
        except Exception as e:
            logger.error(f"Error in process_message: {str(e)}")
            await self.send_error(websocket, "internal_error", str(e))
    
    async def handle_initialize(self, websocket, params: Dict, id_val: str):
        """Handle MCP initialize request"""
        client_info = params.get("clientInfo", {})
        protocol_version = params.get("protocolVersion", "")
        
        logger.info(f"Initialize request from {client_info.get('name', 'unknown')} v{client_info.get('version', 'unknown')}")
        
        response = {
            "jsonrpc": "2.0",
            "id": id_val,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": self.capabilities,
                "serverInfo": {
                    "name": "AWS MCP Customer Support Server",
                    "version": MCP_VERSION
                }
            }
        }
        
        await websocket.send(json.dumps(response))
    
    async def handle_initialized(self, websocket):
        """Handle MCP initialized notification"""
        logger.info("Client initialization completed")
    
    async def handle_tools_list(self, websocket, id_val: str):
        """Handle tools/list request"""
        tools = [
            {
                "name": "chat_with_ai",
                "description": f"Chat with {BEDROCK_MODEL_ID} AI assistant for customer support",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "The user's message"
                        },
                        "conversation_id": {
                            "type": "string",
                            "description": "Conversation ID for context tracking"
                        },
                        "user_id": {
                            "type": "string",
                            "description": "User identifier"
                        }
                    },
                    "required": ["message"]
                }
            },
            {
                "name": "get_conversation_history",
                "description": "Retrieve conversation history for a given conversation ID",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "conversation_id": {
                            "type": "string",
                            "description": "Conversation ID to retrieve history for"
                        }
                    },
                    "required": ["conversation_id"]
                }
            }
        ]
        
        response = {
            "jsonrpc": "2.0",
            "id": id_val,
            "result": {
                "tools": tools
            }
        }
        
        await websocket.send(json.dumps(response))
    
    async def handle_tools_call(self, websocket, params: Dict, id_val: str):
        """Handle tools/call request"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        try:
            if tool_name == "chat_with_ai" or tool_name == "chat_with_nova":  # Support both for backward compatibility
                result = await self.tool_chat_with_ai(arguments)
            elif tool_name == "get_conversation_history":
                result = await self.tool_get_conversation_history(arguments)
            else:
                await self.send_error(websocket, "invalid_request", f"Unknown tool: {tool_name}", id_val)
                return
            
            response = {
                "jsonrpc": "2.0",
                "id": id_val,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2)
                        }
                    ]
                }
            }
            
            await websocket.send(json.dumps(response))
            
        except Exception as e:
            logger.error(f"Error in tool call {tool_name}: {str(e)}")
            await self.send_error(websocket, "internal_error", str(e), id_val)
    
    async def tool_chat_with_ai(self, arguments: Dict) -> Dict:
        """Tool: Chat with configured Bedrock AI model"""
        message = arguments.get("message", "")
        conversation_id = arguments.get("conversation_id", str(uuid.uuid4()))
        user_id = arguments.get("user_id", "anonymous")
        
        # Get conversation history
        conversation_history = await self.get_conversation_history_from_db(conversation_id)
        
        # Generate response using Bedrock model
        response_text = await self.call_bedrock_model(message, conversation_history)
        
        # Store conversation
        await self.store_conversation(conversation_id, user_id, message, response_text)
        
        return {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "response": response_text,
            "timestamp": datetime.utcnow().isoformat(),
            "context": {
                "conversation_length": len(conversation_history) + 1,
                "model": BEDROCK_MODEL_ID
            }
        }
    
    async def tool_get_conversation_history(self, arguments: Dict) -> Dict:
        """Tool: Get conversation history"""
        conversation_id = arguments.get("conversation_id")
        
        if not conversation_id:
            raise ValueError("conversation_id is required")
        
        history = await self.get_conversation_history_from_db(conversation_id)
        
        return {
            "conversation_id": conversation_id,
            "history": history,
            "total_exchanges": len(history),
            "retrieved_at": datetime.utcnow().isoformat()
        }
    
    async def handle_resources_list(self, websocket, id_val: str):
        """Handle resources/list request"""
        resources = [
            {
                "uri": "conversation://history",
                "name": "Conversation History",
                "description": "Access to conversation history data",
                "mimeType": "application/json"
            }
        ]
        
        response = {
            "jsonrpc": "2.0",
            "id": id_val,
            "result": {
                "resources": resources
            }
        }
        
        await websocket.send(json.dumps(response))
    
    async def handle_resources_read(self, websocket, params: Dict, id_val: str):
        """Handle resources/read request"""
        uri = params.get("uri")
        
        if uri == "conversation://history":
            # Return recent conversations
            response_data = {
                "conversations": "Access conversation history via get_conversation_history tool",
                "available_methods": [
                    "Use chat_with_nova tool to start new conversations",
                    "Use get_conversation_history tool to retrieve specific conversation"
                ]
            }
        else:
            await self.send_error(websocket, "invalid_request", f"Unknown resource: {uri}", id_val)
            return
        
        response = {
            "jsonrpc": "2.0",
            "id": id_val,
            "result": {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(response_data, indent=2)
                    }
                ]
            }
        }
        
        await websocket.send(json.dumps(response))
    
    async def handle_prompts_list(self, websocket, id_val: str):
        """Handle prompts/list request"""
        prompts = [
            {
                "name": "customer_support",
                "description": "Customer support conversation prompt for Nova Lite",
                "arguments": [
                    {
                        "name": "customer_issue",
                        "description": "Description of the customer's issue",
                        "required": True
                    },
                    {
                        "name": "urgency",
                        "description": "Urgency level (low, medium, high)",
                        "required": False
                    }
                ]
            }
        ]
        
        response = {
            "jsonrpc": "2.0",
            "id": id_val,
            "result": {
                "prompts": prompts
            }
        }
        
        await websocket.send(json.dumps(response))
    
    async def handle_prompts_get(self, websocket, params: Dict, id_val: str):
        """Handle prompts/get request"""
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if prompt_name == "customer_support":
            customer_issue = arguments.get("customer_issue", "")
            urgency = arguments.get("urgency", "medium")
            
            prompt_text = f"""You are a helpful customer support assistant powered by {BEDROCK_MODEL_ID}. 
            
Customer Issue: {customer_issue}
Urgency Level: {urgency}

Please provide a helpful, empathetic, and professional response to address the customer's concern. 
Consider the urgency level in your response tone and suggested next steps."""

            response = {
                "jsonrpc": "2.0",
                "id": id_val,
                "result": {
                    "description": "Customer support prompt for Nova Lite",
                    "messages": [
                        {
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": prompt_text
                            }
                        }
                    ]
                }
            }
        else:
            await self.send_error(websocket, "invalid_request", f"Unknown prompt: {prompt_name}", id_val)
            return
        
        await websocket.send(json.dumps(response))
    
    async def handle_sampling_create_message(self, websocket, params: Dict, id_val: str):
        """Handle sampling/createMessage request"""
        messages = params.get("messages", [])
        max_tokens = params.get("maxTokens", 500)
        temperature = params.get("temperature", 0.7)
        
        try:
            # Extract the last user message
            user_message = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content")
                    if isinstance(content, list):
                        for item in content:
                            if item.get("type") == "text":
                                user_message = item.get("text", "")
                                break
                    elif isinstance(content, str):
                        user_message = content
                    break
            
            if not user_message:
                raise ValueError("No user message found in sampling request")
            
            # Generate conversation ID for this sampling request
            conversation_id = str(uuid.uuid4())
            
            # Get response from Bedrock model
            response_text = await self.call_bedrock_model(user_message, [])
            
            response = {
                "jsonrpc": "2.0",
                "id": id_val,
                "result": {
                    "role": "assistant",
                    "content": {
                        "type": "text",
                        "text": response_text
                    },
                    "model": BEDROCK_MODEL_ID,
                    "stopReason": "endTurn"
                }
            }
            
            await websocket.send(json.dumps(response))
            
        except Exception as e:
            logger.error(f"Error in sampling/createMessage: {str(e)}")
            await self.send_error(websocket, "internal_error", str(e), id_val)
    
    async def call_bedrock_model(self, message: str, conversation_history: List[Dict]) -> str:
        """Call configured Bedrock model via AWS Bedrock"""
        try:
            # Build conversation context
            messages = self.build_conversation_context(message, conversation_history)
            
            # Prepare the request body (format may vary by model)
            request_body = {
                "messages": messages,
                "max_tokens": 500,
                "temperature": 0.7,
                "top_p": 0.9
            }
            
            logger.info(f"Calling Bedrock model: {BEDROCK_MODEL_ID}")
            
            # Call Bedrock Runtime with configurable model
            response = bedrock_runtime.invoke_model(
                modelId=BEDROCK_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_body)
            )
            
            # Parse the response
            response_body = json.loads(response['body'].read())
            
            # Extract the generated text (format may vary by model)
            if 'output' in response_body and 'message' in response_body['output']:
                # Nova format
                return response_body['output']['message']['content'][0]['text']
            elif 'content' in response_body:
                # Claude format
                if isinstance(response_body['content'], list):
                    return response_body['content'][0].get('text', '')
                return str(response_body['content'])
            elif 'completion' in response_body:
                # Legacy format
                return response_body['completion']
            else:
                logger.error(f"Unexpected response format from {BEDROCK_MODEL_ID}: {response_body}")
                return "I apologize, but I received an unexpected response format. Please try again."
                
        except Exception as e:
            logger.error(f"Error calling Nova Lite: {str(e)}")
            return f"I apologize, but I encountered an error while processing your request: {str(e)}"
    
    def build_conversation_context(self, current_message: str, conversation_history: List[Dict]) -> List[Dict]:
        """Build conversation context for Nova Lite"""
        messages = [{
            "role": "system",
            "content": "You are a helpful customer support assistant powered by Amazon Nova Lite. You provide accurate, helpful, and empathetic responses to customer inquiries. Use the conversation history to maintain context and provide personalized assistance."
        }]
        
        # Add recent conversation history (limit to last 10 exchanges)
        recent_history = conversation_history[-10:] if len(conversation_history) > 10 else conversation_history
        
        for item in recent_history:
            messages.append({"role": "user", "content": item.get('query', '')})
            messages.append({"role": "assistant", "content": item.get('response', '')})
        
        # Add current message
        messages.append({"role": "user", "content": current_message})
        
        return messages
    
    async def get_conversation_history_from_db(self, conversation_id: str) -> List[Dict]:
        """Retrieve conversation history from DynamoDB"""
        try:
            response = conversations_table.query(
                KeyConditionExpression='conversation_id = :cid',
                ExpressionAttributeValues={':cid': conversation_id},
                ScanIndexForward=True
            )
            return response.get('Items', [])
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {str(e)}")
            return []
    
    async def store_conversation(self, conversation_id: str, user_id: str, query: str, response: str):
        """Store conversation turn in DynamoDB"""
        try:
            conversations_table.put_item(
                Item={
                    'conversation_id': conversation_id,
                    'timestamp': datetime.utcnow().isoformat(),
                    'user_id': user_id,
                    'query': query,
                    'response': response,
                    'turn_id': str(uuid.uuid4())
                }
            )
        except Exception as e:
            logger.error(f"Error storing conversation: {str(e)}")
    
    async def send_error(self, websocket, error_code: str, message: str, id_val: Optional[str] = None):
        """Send MCP error response"""
        error_response = {
            "jsonrpc": "2.0",
            "error": {
                "code": self.get_error_code(error_code),
                "message": message
            }
        }
        
        if id_val is not None:
            error_response["id"] = id_val
        
        await websocket.send(json.dumps(error_response))
    
    def get_error_code(self, error_type: str) -> int:
        """Get numeric error codes for MCP errors"""
        error_codes = {
            "parse_error": -32700,
            "invalid_request": -32600,
            "method_not_found": -32601,
            "invalid_params": -32602,
            "internal_error": -32603
        }
        return error_codes.get(error_type, -32603)

async def main():
    """Start the MCP server"""
    server = MCPServer()
    
    logger.info("Starting MCP Server on localhost:8765")
    
    async with websockets.serve(server.handle_client, "localhost", 8765):
        logger.info("MCP Server is running and waiting for connections...")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
