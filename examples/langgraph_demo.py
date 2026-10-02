"""LangGraph demo — a tiny agent with a guarded tool node.

Requires: pip install bastion[langgraph] langchain-openai (or any chat model)

Run: python examples/langgraph_demo.py
"""

from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph

from bastion import Action, AuditLogger, PolicyEngine, Rule
from bastion.integrations.langgraph import guarded_tool_node
from bastion.policy import any_arg_contains


@tool
def search_docs(query: str) -> str:
    """Search internal docs for a query."""
    return f"3 results for '{query}'"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email."""
    return f"sent to {to}"


@tool
def delete_user(user_id: str) -> str:
    """Delete a user account. Irreversible."""
    return f"deleted {user_id}"


def build_graph():
    policy = PolicyEngine()
    policy.add_rule(Rule(
        tool_pattern="delete_*",
        action=Action.BLOCK,
        reason="irreversible action, blocked by default policy",
    ))
    policy.add_rule(Rule(
        tool_pattern="send_email",
        action=Action.APPROVE,
        condition=any_arg_contains(["all-staff", "external"]),
        reason="broad-distribution emails require approval",
    ))

    audit = AuditLogger(log_path="examples/langgraph_audit.jsonl")
    tools = [search_docs, send_email, delete_user]
    tool_node = guarded_tool_node(tools, policy=policy, audit=audit)

    # Wire into a minimal graph. In a real app, an LLM node would decide which
    # tool to call; this demo skips the model and just shows the guard working
    # on the tool-execution edge, which is the integration point that matters.
    graph = StateGraph(MessagesState)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    return graph.compile()


if __name__ == "__main__":
    print("This demo shows how guarded_tool_node() plugs into a LangGraph "
          "StateGraph in place of the prebuilt ToolNode. See build_graph() "
          "for the wiring — attach a model node ahead of 'tools' for a full agent.")
