import os
from anthropic import Anthropic

def main():
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    msg = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=50,
        messages=[{"role": "user", "content": "Say hello in one sentence."}]
    )

    print(msg.content[0].text)

if __name__ == "__main__":
    main()