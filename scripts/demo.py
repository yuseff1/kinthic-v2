from __future__ import annotations

DEMO_STEPS = [
    {
        "scene": "Open",
        "prompt": "",
        "notes": "Show the setup gate or onboarding screen with provider choice and safe defaults visible.",
    },
    {
        "scene": "First prompt",
        "prompt": "Analyze this repo and build a knowledge graph of the architecture.",
        "notes": "Capture the empty state starter prompt and the first streamed answer.",
    },
    {
        "scene": "Risk follow-up",
        "prompt": "Find one contradiction or risk in this project and explain it.",
        "notes": "Cut to the monologue panel while KINTHIC reasons.",
    },
    {
        "scene": "Governed action",
        "prompt": "Propose one safe improvement and ask before acting.",
        "notes": "Show the operator approval queue before any action is approved.",
    },
    {
        "scene": "Proof",
        "prompt": "",
        "notes": "Switch to graph and operator views so nodes, approvals, and usage visibly update.",
    },
]


def main() -> None:
    print("\nKinthic demo walkthrough\n")
    for index, step in enumerate(DEMO_STEPS, start=1):
        print(f"{index}. {step['scene']}")
        if step["prompt"]:
            print(f"   Prompt: {step['prompt']}")
        print(f"   Capture: {step['notes']}")


if __name__ == "__main__":
    main()
