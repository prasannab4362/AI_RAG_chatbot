import json
import re
import requests
import asyncio
from tools import web_search, write_file, search_documents

# The prompt template that teaches the Local LLM how to use tools and when to chat normally
SYSTEM_PROMPT = """You are a helpful AI assistant with tool-use capabilities.
You are running on a local LLM and can interact with the system and web via tools.

You have access to the following tools:
1. web_search: Searches the web for live info (weather, news, sports, or job openings on LinkedIn, Naukri, Indeed).
   Input: a search query string.
2. search_documents: Searches the database of uploaded files (PDFs, TXT, MD) to retrieve context.
   Input: a search query string.
3. write_file: Creates a new text file or resume inside the 'output' directory.
   Input: A JSON object with exactly two keys: "filename" (string) and "content" (string).

--- CONVERSATION GUIDELINES ---
- If the user's query is standard conversation (e.g., greetings like "hi", "hello", "how are you", or general chitchat), do NOT use the Thought/Action/Observation format. Just respond immediately, naturally, and helpfully as a friendly AI assistant.
- Only use the Thought/Action/Observation format below if you need to use a tool to solve the query.

--- TOOL CALLING FORMAT ---
To use a tool, you MUST output your response in this format:
Thought: [Describe your reasoning about what tool to call next]
Action: [tool_name]
Action Input: [the query string, or the JSON object for write_file]

Example of calling search:
Thought: I need to search the web for today's weather in Coimbatore.
Action: web_search
Action Input: weather in Coimbatore today

Example of writing a file:
Thought: I need to save the resume.
Action: write_file
Action Input: {"filename": "resume.md", "content": "# Resume\\n- Name: John Doe"}

Once you have gathered all information and have the final answer, output:
Thought: I have the final answer.
Answer: [Your complete final response to the user. Explain clearly what you did.]
"""

def parse_action_input(tool_name: str, input_str: str):
    """Parses tool inputs, handling JSON parsing for write_file."""
    input_str = input_str.strip()
    if tool_name == "write_file":
        try:
            # Try to load as JSON
            data = json.loads(input_str)
            return data.get("filename", "output.txt"), data.get("content", "")
        except Exception:
            # Fallback parsing in case the LLM didn't format JSON perfectly
            filename_match = re.search(r'"filename"\s*:\s*"([^"]+)"', input_str)
            content_match = re.search(r'"content"\s*:\s*"(.*)"', input_str, re.DOTALL)
            
            filename = filename_match.group(1) if filename_match else "generated_file.txt"
            content = content_match.group(1) if content_match else input_str
            
            # Clean up escape characters
            content = content.replace('\\n', '\n').replace('\\t', '\t').strip('" ')
            return filename, content
            
    return input_str

async def call_local_chat_llm(messages: list, model_name: str) -> str:
    """Calls Ollama chat endpoint to get the next agent step."""
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.1  # Low temperature for consistent tool calling
        }
    }
    
    try:
        # Run blocking request in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(url, json=payload, timeout=45)
        )
        if response.status_code == 200:
            return response.json().get("message", {}).get("content", "")
        else:
            return f"Error: Local LLM API returned HTTP {response.status_code}"
    except Exception as e:
        return f"Error connecting to local LLM: {str(e)}. Make sure Ollama is running (`ollama serve`)."

async def run_agent(query: str, chat_history: list, websocket, model_name: str = "llama3"):
    """
    Runs the ReAct loop using the chat API. Sends status updates and streaming final answer 
    tokens over the WebSocket connection.
    """
    # 1. Start with system prompt
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    
    # 2. Append conversation history (from previous turns)
    for msg in chat_history[-6:]:  # Limit history to last 6 messages
        messages.append({"role": msg["role"], "content": msg["content"]})
        
    # 3. Append current user query
    messages.append({"role": "user", "content": query})
    
    max_steps = 5
    step = 0
    
    # Copy messages to represent the current execution trajectory
    agent_messages = list(messages)
    
    while step < max_steps:
        step += 1
        
        # Notify user that LLM is thinking
        await websocket.send_json({"type": "status", "content": "Thinking..."})
        
        # Get LLM response for this step
        llm_response = await call_local_chat_llm(agent_messages, model_name)
        print(f"--- Step {step} LLM Output ---\n{llm_response}\n----------------------")
        
        # Parse Thought
        thought_match = re.search(r"Thought:\s*(.*?)(Action:|Answer:|$)", llm_response, re.DOTALL)
        thought_text = thought_match.group(1).strip() if thought_match else "Reasoning next steps..."
        
        # Send Thought to client
        await websocket.send_json({"type": "status", "content": f"Thought: {thought_text}"})
        
        # Check if the LLM chose to call a Tool
        action_match = re.search(r"Action:\s*(\w+)", llm_response)
        action_input_match = re.search(r"Action Input:\s*(.*)", llm_response, re.DOTALL)
        
        if action_match and action_input_match:
            tool_name = action_match.group(1).strip()
            tool_input_raw = action_input_match.group(1).strip()
            
            # Handle case where model outputs Action: None / Action: null
            if tool_name.lower() in ["none", "null", "no_tool", "notool"]:
                print(f"[Agent] Model selected '{tool_name}' (No action). Prompting for final Answer.")
                agent_messages.append({"role": "assistant", "content": llm_response})
                agent_messages.append({"role": "user", "content": "Observation: You selected no action. Please provide your final response to the user using the 'Answer:' prefix."})
                continue
            
            # Update user interface with Tool status
            await websocket.send_json({
                "type": "status", 
                "content": f"Running tool: {tool_name}..."
            })
            
            # Execute the appropriate tool
            observation = ""
            if tool_name == "web_search":
                search_query = parse_action_input(tool_name, tool_input_raw)
                observation = web_search(search_query)
            elif tool_name == "search_documents":
                doc_query = parse_action_input(tool_name, tool_input_raw)
                observation = search_documents(doc_query)
            elif tool_name == "write_file":
                filename, content = parse_action_input(tool_name, tool_input_raw)
                observation = write_file(filename, content)
            else:
                observation = f"Error: Tool '{tool_name}' is not recognized."
                
            # Log observation in console
            print(f"--- Step {step} Tool Result ({tool_name}) ---\n{observation[:200]}...\n----------------------")
            
            # Feed current step response and observation back to model
            agent_messages.append({"role": "assistant", "content": llm_response})
            agent_messages.append({"role": "user", "content": f"Observation: {observation}"})
            
            await asyncio.sleep(0.5)  # Short delay for visual effect in UI
            
        # Check if the LLM outputted a final Answer
        elif "Answer:" in llm_response:
            answer_part = llm_response.split("Answer:")[-1].strip()
            
            # Stream the final answer token-by-token (simulated for smooth UI rendering)
            await websocket.send_json({"type": "status", "content": "Complete!"})
            
            # Split by words to stream nicely
            words = answer_part.split(" ")
            for i, word in enumerate(words):
                space = " " if i > 0 else ""
                await websocket.send_json({"type": "token", "content": space + word})
                await asyncio.sleep(0.02)  # Adjust speed of streaming
                
            return answer_part
        else:
            # Fallback if LLM output didn't follow formatting rules
            await websocket.send_json({"type": "status", "content": "Finalizing answer..."})
            clean_response = re.sub(r"(Thought|Action|Action Input):.*", "", llm_response, flags=re.MULTILINE).strip()
            
            # Stream response
            words = clean_response.split(" ")
            for i, word in enumerate(words):
                space = " " if i > 0 else ""
                await websocket.send_json({"type": "token", "content": space + word})
                await asyncio.sleep(0.02)
                
            return clean_response
            
    # Timeout response
    error_msg = "Agent could not resolve an answer within the maximum number of steps."
    await websocket.send_json({"type": "token", "content": error_msg})
    return error_msg