import asyncio
import os
import json
import sys

# Fix console encoding for Windows
sys.stdout.reconfigure(encoding='utf-8')

from agent import run_agent

# Mock WebSocket to log agent thoughts and collect tokens
class CapturingWebSocket:
    def __init__(self):
        self.log_lines = []
        self.response_tokens = []

    async def send_json(self, data):
        data_type = data.get("type")
        content = data.get("content", "")
        
        if data_type == "status":
            print(f"  [STATUS] {content}")
            self.log_lines.append(f"[STATUS] {content}")
        elif data_type == "token":
            print(content, end="", flush=True)
            self.response_tokens.append(content)
        elif data_type == "error":
            print(f"\n  [ERROR] {content}")
            self.log_lines.append(f"[ERROR] {content}")

    def get_full_response(self):
        return "".join(self.response_tokens)

async def run_scenario(test_num, title, query):
    print("\n" + "="*60)
    print(f"TEST {test_num}: {title}")
    print(f"Query: '{query}'")
    print("="*60)
    
    ws = CapturingWebSocket()
    history = []
    
    try:
        print("--- Execution Trace ---")
        final_answer = await run_agent(
            query=query,
            chat_history=history,
            websocket=ws,
            model_name="qwen2.5:7b",
            web_search_enabled=True
        )
        print("\n\n--- Final Response ---")
        print(final_answer)
        
        return {
            "status": "success",
            "query": query,
            "trace": ws.log_lines,
            "answer": final_answer
        }
    except Exception as e:
        print(f"\n[CRITICAL FAILURE] Test {test_num} crashed: {str(e)}")
        return {
            "status": "failure",
            "query": query,
            "error": str(e)
        }

async def main():
    scenarios = [
        (1, "Sports Schedule & Prediction", "What is the schedule of Manchester United vs Liverpool today? Look up match results from 3 years ago, 5 years ago, and make a prediction for today."),
        (2, "Coimbatore News (Last 2-3 days)", "What is the latest news in Coimbatore from the last 2-3 days?"),
        (3, "LinkedIn Resume Generation", "Find the LinkedIn profile for www.linkedin.com/in/prasannabalaji18 and write a tailored resume to prasanna_resume.md"),
        (4, "Job Search & Skill Analysis", "Search for Python Developer job openings in Bangalore or Coimbatore and give me a list of openings with a brief analysis of the required skills."),
        (5, "Coimbatore Weather & Recommendation", "What is the weather today in Coimbatore and what should I wear?")
    ]
    
    results = {}
    for num, title, query in scenarios:
        results[title] = await run_scenario(num, title, query)
        await asyncio.sleep(2)  # Delay between runs
        
    # Save results to output/test_results.json
    os.makedirs("output", exist_ok=True)
    with open(os.path.join("output", "test_results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    print("\n" + "="*60)
    print("ALL 5 SCENARIO TESTS COMPLETED. RESULTS SAVED TO output/test_results.json")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
