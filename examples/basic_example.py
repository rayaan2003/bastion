"""Minimal, dependency-free demo of the policy engine + guard.

Run: python examples/basic_example.py
"""

from bastion import Action, AuditLogger, PolicyEngine, Rule, guard
from bastion.approval import ConsoleApprovalHandler
from bastion.guard import BlockedByPolicy
from bastion.policy import arg_exceeds


def send_email(to: str, subject: str, body: str) -> str:
    return f"sent email to {to}: {subject}"


def delete_database(table_name: str) -> str:
    return f"deleted table {table_name}"


def transfer_funds(account: str, amount: float) -> str:
    return f"transferred ${amount} to {account}"


def main() -> None:
    policy = PolicyEngine()
    policy.add_rule(Rule(
        tool_pattern="delete_*",
        action=Action.BLOCK,
        reason="destructive database operations are never auto-allowed",
    ))
    policy.add_rule(Rule(
        tool_pattern="transfer_funds",
        action=Action.APPROVE,
        condition=arg_exceeds("amount", 500),
        reason="transfers over $500 require human approval",
    ))

    audit = AuditLogger(log_path="examples/demo_audit.jsonl")
    approval = ConsoleApprovalHandler()

    guarded_send_email = guard(send_email, policy=policy, audit=audit, approval_handler=approval)
    guarded_delete = guard(delete_database, policy=policy, audit=audit, approval_handler=approval)
    guarded_transfer = guard(transfer_funds, policy=policy, audit=audit, approval_handler=approval)

    print(guarded_send_email(to="a@b.com", subject="hi", body="hello"))

    try:
        guarded_delete(table_name="users")
    except BlockedByPolicy as e:
        print(f"blocked as expected: {e}")

    print("about to attempt a $600 transfer — this will prompt for approval in the terminal")
    try:
        print(guarded_transfer(account="acct_123", amount=600))
    except BlockedByPolicy as e:
        print(f"denied: {e}")

    print("\naudit trail written to examples/demo_audit.jsonl")


if __name__ == "__main__":
    main()
