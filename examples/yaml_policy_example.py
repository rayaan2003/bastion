"""Load a policy from a YAML file instead of hand-writing Rule() calls in Python.

Run: python examples/yaml_policy_example.py
"""

from pathlib import Path

from agentguard import AuditLogger, guard, load_policy_from_yaml
from agentguard.guard import BlockedByPolicy


def delete_database(table_name: str) -> str:
    return f"deleted table {table_name}"


def main() -> None:
    policy_path = Path(__file__).parent / "policy.yaml"
    policy = load_policy_from_yaml(policy_path)
    audit = AuditLogger(log_path="examples/yaml_demo_audit.jsonl")

    guarded_delete = guard(delete_database, policy=policy, audit=audit)

    try:
        guarded_delete(table_name="users")
    except BlockedByPolicy as e:
        print(f"blocked as expected (loaded from policy.yaml): {e}")


if __name__ == "__main__":
    main()
