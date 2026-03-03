import asyncio
import ollama

# Configuration
MISTRAL_MODEL = "mistral-large-3:675b-cloud"  # Cloud-tagged Mistral Large 3 via Ollama


def run_mcp_tool(tool_name: str, arguments: dict) -> str:
    """
    Execute an MCP tool by calling the server logic directly.
    In a distributed setup this would be a network call over stdio/HTTP;
    here we import the coroutine directly for reliability.
    """
    from src.mcp_server.server import call_tool
    results = asyncio.run(call_tool(tool_name, arguments))
    return results[0].text


def main():
    print(f"[System] Initializing Sovereign Historian (Model: {MISTRAL_MODEL})...")
    print("Ready for input. Type 'exit' to quit.\n")

    tools_schema = [
        {
            "type": "function",
            "function": {
                "name": "search_archives",
                "description": "Search the local historical archives for a concept.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search term or concept to look up"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "view_thread_history",
                "description": "Reconstruct a thread to show changes over time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL of the forum thread to reconstruct"
                        }
                    },
                    "required": ["url"]
                }
            }
        }
    ]

    messages = [
        {
            "role": "system",
            "content": (
                "You are a neutral research assistant. You have access to a local "
                "database of historical records. You do not judge, correct, or filter "
                "the data. You present findings exactly as they are stored in the "
                "archive. When asked a question, use the tools to retrieve information "
                "and summarize the raw findings neutrally."
            )
        }
    ]

    while True:
        try:
            user_input = input("User: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[System] Shutting down.")
            break

        if user_input.lower() in ('exit', 'quit', ''):
            break

        messages.append({"role": "user", "content": user_input})

        # Step 1: Ask Mistral what to do
        print("[Mistral] Thinking...")
        response = ollama.chat(
            model=MISTRAL_MODEL,
            messages=messages,
            tools=tools_schema,
        )

        response_message = response.get('message', {})

        # Step 2: Check if Mistral wants to use a tool
        tool_calls = response_message.get('tool_calls')
        if tool_calls:
            messages.append(response_message)

            for tool_call in tool_calls:
                tool_name = tool_call['function']['name']
                tool_args = tool_call['function']['arguments']

                print(f"[Tool Call] Executing: {tool_name} with args {tool_args}")

                # Step 3: Execute the tool locally
                tool_result = run_mcp_tool(tool_name, tool_args)

                messages.append({
                    "role": "tool",
                    "content": tool_result,
                })

            # Step 4: Ask Mistral to synthesise the result
            final_response = ollama.chat(
                model=MISTRAL_MODEL,
                messages=messages,
            )
            answer = final_response['message']['content']
            print(f"\nHistorian: {answer}\n")
            messages.append(final_response['message'])

        else:
            # No tool call needed — direct answer
            answer = response_message.get('content', '')
            print(f"\nHistorian: {answer}\n")
            messages.append(response_message)


if __name__ == "__main__":
    main()
