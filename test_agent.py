import asyncio
import os
import json
import sys
# Fix Windows console encoding issues when printing UTF-8 search results
sys.stdout.reconfigure(encoding='utf-8')
from tools import web_search, write_file, search_documents
from agent import run_agent

# Mock WebSocket to capture agent output in terminal
class MockWebSocket:
    async def send_json(self, data):
        data_type = data.get("type")
        content = data.get("content", "")
        
        if data_type == "status":
            print(f"[STATUS] {content}")
        elif data_type == "token":
            # Print streaming tokens inline
            print(content, end="", flush=True)
        elif data_type == "error":
            print(f"\n[ERROR] {content}")

async def test_all():
    print("==================================================")
    print("STARTING BOT INTEGRATION TESTS")
    print("==================================================")
    
    mock_ws = MockWebSocket()
    history = []
    
    # Test 1: LinkedIn Resume Generation
    print("\n--- 1. Testing LinkedIn Search & Resume Writer ---")
    print("Query: 'Find the LinkedIn profile of www.linkedin.com/in/prasannabalaji18 and write a tailored resume to prasanna_resume.md'")
    try:
        print("\n--- Agent Execution Trace ---")
        answer_linkedin = await run_agent(
            query="Find the LinkedIn profile of www.linkedin.com/in/prasannabalaji18 and write a tailored resume to prasanna_resume.md",
            chat_history=history,
            websocket=mock_ws,
            model_name="qwen2.5:7b"
        )
        print("\n\n--- LinkedIn Test Completed ---")
        print(answer_linkedin)
        
        # Verify if file was created
        resume_path = os.path.join("output", "prasanna_resume.md")
        if os.path.exists(resume_path):
            print(f"\n[VERIFIED] File created successfully at {resume_path}!")
        else:
            print(f"\n[ERROR] Resume file was NOT created at {resume_path}")
    except Exception as e:
        print(f"\nLinkedIn Test Failed: {str(e)}")
        
    print("\n" + "="*50)
    
    # Test 2: Sports History & Prediction
    print("\n--- 2. Testing Sports History & Prediction ---")
    print("Query: 'What is the schedule of Manchester United vs Liverpool today? Look up match results from 3 years ago, 5 years ago, and make a prediction for today.'")
    try:
        print("\n--- Agent Execution Trace ---")
        answer_sports = await run_agent(
            query="What is the schedule of Manchester United vs Liverpool today? Look up match results from 3 years ago, 5 years ago, and make a prediction for today.",
            chat_history=history,
            websocket=mock_ws,
            model_name="qwen2.5:7b"
        )
        print("\n\n--- Sports Test Completed ---")
        print(answer_sports)
    except Exception as e:
        print(f"\nSports Test Failed: {str(e)}")

    print("\n==================================================")
    print("ALL TESTS COMPLETED")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(test_all())
