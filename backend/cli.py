"""Terminal demo: python cli.py  (add --offline to skip all network calls)."""
import sys
import uuid

if "--offline" in sys.argv:
    import os
    os.environ["TRIPSYNC_OFFLINE"] = "1"

from langgraph.types import Command  # noqa: E402

from tripsync.graph import pending_interrupt, sqlite_graph  # noqa: E402


def run(graph, payload, config):
    for chunk in graph.stream(payload, config, stream_mode="updates"):
        for node, update in chunk.items():
            if node == "__interrupt__":
                continue
            for line in (update or {}).get("log", []):
                print("  ", line)


def main():
    graph = sqlite_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    print("TripSync — describe your trip (Ctrl+C to quit). After the plan, type edits like 'make day 2 lighter'.")
    while True:
        msg = input("\nyou> ").strip()
        if not msg:
            continue
        ask = pending_interrupt(graph, config)
        run(graph, Command(resume=msg) if ask else {"user_message": msg}, config)
        ask = pending_interrupt(graph, config)
        while ask and ask["type"] == "select":  # the terminal version takes the suggested places
            print("   (using the suggested places, stay and transport)")
            run(graph, Command(resume={"accept": True}), config)
            ask = pending_interrupt(graph, config)
        if ask:
            print("\ntripsync>", ask["question"])
        else:
            print("\n" + (graph.get_state(config).values.get("reply") or ""))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print()
