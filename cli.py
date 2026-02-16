import argparse
import subprocess
import sys

from commands import pod
from commands.clean import clean


def main() -> None:
    parser = argparse.ArgumentParser(description="Math Tutor CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("clean", help="Run isort + black + mypy on all code")
    subparsers.add_parser("test", help="Run pytest (pass extra args after --)")

    pod_parser = subparsers.add_parser("pod", help="Manage dev RunPod GPU pod")
    pod_sub = pod_parser.add_subparsers(dest="pod_action", help="Pod actions")
    pod_sub.add_parser("start", help="Create pod with 3 vLLM instances")
    pod_sub.add_parser("stop", help="Destroy pod and delete .env.dev")

    args, unknown = parser.parse_known_args()

    if args.command == "clean":
        clean()
    elif args.command == "test":
        pytest_cmd = ["pytest", "-n", "auto"]
        if unknown:
            pytest_cmd.extend(unknown)
        result = subprocess.run(pytest_cmd)
        sys.exit(result.returncode)
    elif args.command == "pod":
        actions = {
            "start": pod.start,
            "stop": pod.terminate,
        }
        action = actions.get(args.pod_action or "")
        if action:
            action()
        else:
            pod_parser.print_help()
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
