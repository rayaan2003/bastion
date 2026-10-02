"""Block tool calls whose arguments contain PII/secrets, and scan LLM output
text directly with enforce_text_policy().

Run: python examples/pii_scanning_example.py
"""

from bastion import Action, PolicyEngine, Rule, contains_pii, enforce_text_policy, guard
from bastion.guard import BlockedByPolicy
from bastion.scanning import SensitiveContentBlocked


def log_customer_note(body: str) -> str:
    return f"logged: {body}"


def main() -> None:
    policy = PolicyEngine()
    policy.add_rule(Rule(
        tool_pattern="*",
        action=Action.BLOCK,
        condition=contains_pii(["ssn_us", "credit_card", "aws_secret_access_key"]),
        reason="tool call args contain PII/secrets",
    ))

    guarded_log = guard(log_customer_note, policy=policy)

    try:
        guarded_log(body="customer SSN is 123-45-6789, please follow up")
    except BlockedByPolicy as e:
        print(f"tool call blocked: {e}")

    print(guarded_log(body="customer asked about refund timelines"))

    # Scanning LLM output text directly (not a tool call) with enforce_text_policy
    llm_response = "Sure, here's the info: contact me at a@b.com for details."
    try:
        enforce_text_policy(llm_response, categories=["email"], on_detect="block")
    except SensitiveContentBlocked as e:
        print(f"LLM output blocked: {e}")

    redacted = enforce_text_policy(llm_response, categories=["email"], on_detect="redact")
    print(f"redacted LLM output: {redacted}")


if __name__ == "__main__":
    main()
