import asyncio
import websockets
import json
import uuid
from typing import Dict, Any

class MCPClient:
    def __init__(self, server_uri: str = "ws://localhost:8765"):
        self.server_uri = server_uri
        self.websocket = None
        self.request_id = 0
        self.pending_requests = {}
        
    async def connect(self):
        """Connect to MCP server"""
        self.websocket = await websockets.connect(self.server_uri)
        print(f"Connected to MCP server at {self.server_uri}")
        
        # Start listening for responses
        asyncio.create_task(self.listen_for_responses())
        
        # Initialize the connection
        await self.initialize()
    
    async def disconnect(self):
        """Disconnect from MCP server"""
        if self.websocket:
            await self.websocket.close()
            print("Disconnected from MCP server")
    
    async def listen_for_responses(self):
        """Listen for responses from the server"""
        try:
            async for message in self.websocket:
                response = json.loads(message)
                
                if "id" in response:
                    # This is a response to a request
                    request_id = response["id"]
                    if request_id in self.pending_requests:
                        future = self.pending_requests.pop(request_id)
                        future.set_result(response)
                else:
                    # This is a notification
                    print(f"Received notification: {response}")
        except websockets.exceptions.ConnectionClosed:
            print("Connection to server closed")
        except Exception as e:
            print(f"Error listening for responses: {e}")
    
    async def send_request(self, method: str, params: Dict = None) -> Dict:
        """Send a request to the MCP server"""
        self.request_id += 1
        request_id = str(self.request_id)
        
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        }
        
        # Create future for response
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        # Send request
        await self.websocket.send(json.dumps(request))
        
        # Wait for response
        try:
            response = await asyncio.wait_for(future, timeout=30.0)
            return response
        except asyncio.TimeoutError:
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]
            raise Exception(f"Request {method} timed out")
    
    async def send_notification(self, method: str, params: Dict = None):
        """Send a notification to the MCP server"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        
        await self.websocket.send(json.dumps(notification))
    
    async def initialize(self):
        """Initialize the MCP connection"""
        params = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "experimental": {}
            },
            "clientInfo": {
                "name": "AWS MCP Customer Support Client",
                "version": "1.0.0"
            }
        }
        
        response = await self.send_request("initialize", params)
        
        if "error" in response:
            raise Exception(f"Initialization failed: {response['error']}")
        
        # Send initialized notification
        await self.send_notification("notifications/initialized")
        
        print("MCP client initialized successfully")
        return response["result"]
    
    async def list_tools(self):
        """List available tools"""
        response = await self.send_request("tools/list")
        
        if "error" in response:
            raise Exception(f"Failed to list tools: {response['error']}")
        
        return response["result"]["tools"]
    
    async def call_tool(self, tool_name: str, arguments: Dict):
        """Call a specific tool"""
        params = {
            "name": tool_name,
            "arguments": arguments
        }
        
        response = await self.send_request("tools/call", params)
        
        if "error" in response:
            raise Exception(f"Tool call failed: {response['error']}")
        
        return response["result"]
    
    async def chat_with_nova(self, message: str, conversation_id: str = None, user_id: str = "client_user"):
        """Convenience method to chat with Nova Lite"""
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        arguments = {
            "message": message,
            "conversation_id": conversation_id,
            "user_id": user_id
        }
        
        result = await self.call_tool("chat_with_nova", arguments)
        
        # Extract the actual response from the tool result
        content = result.get("content", [])
        if content and len(content) > 0:
            response_data = json.loads(content[0]["text"])
            return response_data
        
        return result
    
    async def get_conversation_history(self, conversation_id: str):
        """Get conversation history"""
        arguments = {
            "conversation_id": conversation_id
        }
        
        result = await self.call_tool("get_conversation_history", arguments)
        
        # Extract the actual response from the tool result
        content = result.get("content", [])
        if content and len(content) > 0:
            response_data = json.loads(content[0]["text"])
            return response_data
        
        return result
    
    async def list_resources(self):
        """List available resources"""
        response = await self.send_request("resources/list")
        
        if "error" in response:
            raise Exception(f"Failed to list resources: {response['error']}")
        
        return response["result"]["resources"]
    
    async def read_resource(self, uri: str):
        """Read a specific resource"""
        params = {
            "uri": uri
        }
        
        response = await self.send_request("resources/read", params)
        
        if "error" in response:
            raise Exception(f"Failed to read resource: {response['error']}")
        
        return response["result"]
    
    async def list_prompts(self):
        """List available prompts"""
        response = await self.send_request("prompts/list")
        
        if "error" in response:
            raise Exception(f"Failed to list prompts: {response['error']}")
        
        return response["result"]["prompts"]
    
    async def get_prompt(self, prompt_name: str, arguments: Dict = None):
        """Get a specific prompt"""
        params = {
            "name": prompt_name,
            "arguments": arguments or {}
        }
        
        response = await self.send_request("prompts/get", params)
        
        if "error" in response:
            raise Exception(f"Failed to get prompt: {response['error']}")
        
        return response["result"]
    
    async def create_message(self, messages: list, max_tokens: int = 500, temperature: float = 0.7):
        """Create a message using sampling"""
        params = {
            "messages": messages,
            "maxTokens": max_tokens,
            "temperature": temperature
        }
        
        response = await self.send_request("sampling/createMessage", params)
        
        if "error" in response:
            raise Exception(f"Failed to create message: {response['error']}")
        
        return response["result"]

async def interactive_client():
    """Interactive MCP client for testing"""
    client = MCPClient()
    
    try:
        await client.connect()
        
        print("\n=== MCP Client Connected ===")
        print("Available commands:")
        print("1. chat <message> - Chat with Nova Lite")
        print("2. history <conversation_id> - Get conversation history")
        print("3. tools - List available tools")
        print("4. resources - List available resources")
        print("5. prompts - List available prompts")
        print("6. quit - Exit")
        print()
        
        conversation_id = str(uuid.uuid4())
        print(f"Starting new conversation: {conversation_id}")
        print()
        
        while True:
            try:
                command = input("MCP> ").strip()
                
                if command.startswith("chat "):
                    message = command[5:]
                    print(f"Sending message: {message}")
                    
                    result = await client.chat_with_nova(message, conversation_id)
                    print(f"Response: {result.get('response', 'No response')}")
                    print(f"Conversation length: {result.get('context', {}).get('conversation_length', 0)}")
                    print()
                
                elif command.startswith("history "):
                    conv_id = command[8:] or conversation_id
                    print(f"Getting history for conversation: {conv_id}")
                    
                    result = await client.get_conversation_history(conv_id)
                    print(f"History: {json.dumps(result, indent=2)}")
                    print()
                
                elif command == "tools":
                    tools = await client.list_tools()
                    print("Available tools:")
                    for tool in tools:
                        print(f"  - {tool['name']}: {tool['description']}")
                    print()
                
                elif command == "resources":
                    resources = await client.list_resources()
                    print("Available resources:")
                    for resource in resources:
                        print(f"  - {resource['uri']}: {resource['name']}")
                    print()
                
                elif command == "prompts":
                    prompts = await client.list_prompts()
                    print("Available prompts:")
                    for prompt in prompts:
                        print(f"  - {prompt['name']}: {prompt['description']}")
                    print()
                
                elif command == "quit":
                    break
                
                else:
                    print("Unknown command. Type 'quit' to exit.")
            
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
    
    except Exception as e:
        print(f"Failed to connect: {e}")
    
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(interactive_client())
