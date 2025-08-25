#!/usr/bin/env python3
"""
MCP Server Runner for AWS Lambda
This script adapts the MCP server to run in AWS Lambda environment
"""

import json
import asyncio
import boto3
import uuid
from datetime import datetime
import logging
from typing import Dict, Any, Optional, List

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS services
dynamodb = boto3.resource('dynamodb')
conversations_table = dynamodb.Table('MCPConversations')
bedrock_runtime = boto3.client('bedrock-runtime')

# MCP Protocol Constants
MCP_VERSION = "1.0.0"
PROTOCOL_VERSION = "2024-11-05"

# Get model configuration from environment variables
import os
DEFAULT_MODEL = "amazon.nova-lite-v1:0"
BEDROCK_MODEL_ID = os.environ.get('BEDROCK_MODEL_ID_ARN', DEFAULT_MODEL)

class MCPLambdaHandler:
    """MCP Server adapted for AWS Lambda"""
    
    def __init__(self):
        self.capabilities = {
            "tools": {},
            "resources": {},
            "prompts": {},
            "experimental": {
                "sampling": True
            }
        }
    
    def lambda_handler(self, event, context):
        """AWS Lambda handler for MCP requests"""
        try:
            # Parse the MCP request
            if 'body' in event:
                body = json.loads(event['body'])
            else:
                body = event
            
            method = body.get("method")
            params = body.get("params", {})
            id_val = body.get("id")
            
            logger.info(f"Processing MCP method: {method}")
            
            # Route to appropriate handler
            if method == "initialize":
                result = self.handle_initialize(params)
            elif method == "tools/list":
                result = self.handle_tools_list()
            elif method == "tools/call":
                result = asyncio.run(self.handle_tools_call(params))
            elif method == "resources/list":
                result = self.handle_resources_list()
            elif method == "resources/read":
                result = self.handle_resources_read(params)
            elif method == "prompts/list":
                result = self.handle_prompts_list()
            elif method == "prompts/get":
                result = self.handle_prompts_get(params)
            elif method == "sampling/createMessage":
                result = asyncio.run(self.handle_sampling_create_message(params))
            else:
                return self.create_error_response("method_not_found", f"Unknown method: {method}", id_val)
            
            # Create success response
            response = {
                "jsonrpc": "2.0",
                "id": id_val,
                "result": result
            }
            
            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps(response)
            }
            
        except Exception as e:
            logger.error(f"Error processing MCP request: {str(e)}")
            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*"
                },
                "body": json.dumps(self.create_error_response("internal_error", str(e), None))
            }
    
    def handle_initialize(self, params: Dict) -> Dict:
        """Handle MCP initialize request"""
        client_info = params.get("clientInfo", {})
        protocol_version = params.get("protocolVersion", "")
        
        logger.info(f"Initialize request from {client_info.get('name', 'unknown')} v{client_info.get('version', 'unknown')}")
        
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": self.capabilities,
            "serverInfo": {
                "name": "AWS MCP Customer Support Server",
                "version": MCP_VERSION
            }
        }
    
    def handle_tools_list(self) -> Dict:
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
        
        return {"tools": tools}
    
    async def handle_tools_call(self, params: Dict) -> Dict:
        """Handle tools/call request"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name == "chat_with_ai" or tool_name == "chat_with_nova":  # Support both for backward compatibility
            result = await self.tool_chat_with_ai(arguments)
        elif tool_name == "get_conversation_history":
            result = await self.tool_get_conversation_history(arguments)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }
            ]
        }
    
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
    
    def handle_resources_list(self) -> Dict:
        """Handle resources/list request"""
        resources = [
            {
                "uri": "conversation://history",
                "name": "Conversation History",
                "description": "Access to conversation history data",
                "mimeType": "application/json"
            }
        ]
        
        return {"resources": resources}
    
    def handle_resources_read(self, params: Dict) -> Dict:
        """Handle resources/read request"""
        uri = params.get("uri")
        
        if uri == "conversation://history":
            response_data = {
                "conversations": "Access conversation history via get_conversation_history tool",
                "available_methods": [
                    "Use chat_with_nova tool to start new conversations",
                    "Use get_conversation_history tool to retrieve specific conversation"
                ]
            }
        else:
            raise ValueError(f"Unknown resource: {uri}")
        
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(response_data, indent=2)
                }
            ]
        }
    
    def handle_prompts_list(self) -> Dict:
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
        
        return {"prompts": prompts}
    
    def handle_prompts_get(self, params: Dict) -> Dict:
        """Handle prompts/get request"""
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if prompt_name == "customer_support":
            customer_issue = arguments.get("customer_issue", "")
            urgency = arguments.get("urgency", "medium")
            
            prompt_text = f"""You are a helpful customer support assistant powered by Amazon Nova Lite. 
            
Customer Issue: {customer_issue}
Urgency Level: {urgency}

Please provide a helpful, empathetic, and professional response to address the customer's concern. 
Consider the urgency level in your response tone and suggested next steps."""

            return {
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
        else:
            raise ValueError(f"Unknown prompt: {prompt_name}")
    
    async def handle_sampling_create_message(self, params: Dict) -> Dict:
        """Handle sampling/createMessage request"""
        messages = params.get("messages", [])
        max_tokens = params.get("maxTokens", 500)
        temperature = params.get("temperature", 0.7)
        
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
        
        # Get response from Bedrock model
        response_text = await self.call_bedrock_model(user_message, [])
        
        return {
            "role": "assistant",
            "content": {
                "type": "text",
                "text": response_text
            },
            "model": BEDROCK_MODEL_ID,
            "stopReason": "endTurn"
        }
    
    async def call_bedrock_model(self, message: str, conversation_history: List[Dict]) -> str:
        """Call configured Bedrock model via AWS Bedrock"""
        try:
            # Build conversation context
            messages = self.build_conversation_context(message, conversation_history)
            
            # Prepare the request body (format may vary by model)
            # request_body = {
            #     "messages": messages,
            #     "max_tokens": 500,
            #     "temperature": 0.7,
            #     "top_p": 0.9
            # }

            max_tokens = 500
            request_body = {
                "inferenceConfig": {
                    "max_new_tokens": max_tokens
                },
                "messages": [
                    {
                        "role": "user",
                        "content": [{
                            "text": messages[-1]['content']
                        }]
                    }]
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
            logger.error(f"Error calling Bedrock model {BEDROCK_MODEL_ID}: {str(e)}")
            return f"I apologize, but I encountered an error while processing your request: {str(e)}"
    
    def build_conversation_context(self, current_message: str, conversation_history: List[Dict]) -> List[Dict]:
        """Build conversation context for Bedrock model"""
        messages = [{
            "role": "system",
            "content": f"You are a helpful customer support assistant powered by {BEDROCK_MODEL_ID}. You provide accurate, helpful, and empathetic responses to customer inquiries. Use the conversation history to maintain context and provide personalized assistance."
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
    
    def create_error_response(self, error_code: str, message: str, id_val: Optional[str] = None) -> Dict:
        """Create MCP error response"""
        error_response = {
            "jsonrpc": "2.0",
            "error": {
                "code": self.get_error_code(error_code),
                "message": message
            }
        }
        
        if id_val is not None:
            error_response["id"] = id_val
        
        return error_response
    
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

# Global handler instance
mcp_handler = MCPLambdaHandler()

def lambda_handler(event, context):
    """AWS Lambda entry point"""
    return mcp_handler.lambda_handler(event, context)
