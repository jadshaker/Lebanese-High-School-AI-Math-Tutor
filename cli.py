import argparse
import os
import subprocess

FILES_TO_CLEAN = ["services", "cli.py"]


def clean():
    # Format all files
    subprocess.run(
        [
            "autoflake",
            "--remove-all-unused-imports",
            "--remove-unused-variables",
            "--recursive",
            *FILES_TO_CLEAN,
            "-i",
            "--exclude=__init__.py",
        ]
    )
    subprocess.run(["isort", *FILES_TO_CLEAN, "--profile", "black"])
    subprocess.run(["black", *FILES_TO_CLEAN])

    # Type check cli.py
    subprocess.run(["mypy", "cli.py"])

    # Type check each service from within its directory
    services_dir = "services"
    if os.path.exists(services_dir):
        for service in os.listdir(services_dir):
            service_path = os.path.join(services_dir, service)
            src_path = os.path.join(service_path, "src")
            if os.path.isdir(service_path) and os.path.exists(src_path):
                print(f"\nType checking {service} service...")
                subprocess.run(
                    ["mypy", "src", "--explicit-package-bases"], cwd=service_path
                )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", type=str, help="Command to run")
    args = parser.parse_args()
    if args.command == "clean":
        clean()
    else:
        print("Invalid command")


if __name__ == "__main__":
    main()
