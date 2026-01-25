import argparse
import os
import subprocess

FILES_TO_CLEAN = ["services", "cli.py"]


def clean():
    # Install service dependencies for type checking
    print("Installing service dependencies...")
    services_dir = "services"
    if os.path.exists(services_dir):
        for service in os.listdir(services_dir):
            service_path = os.path.join(services_dir, service)
            requirements_path = os.path.join(service_path, "requirements.txt")
            if os.path.isfile(requirements_path):
                print(f"Installing dependencies for {service}...")
                subprocess.run(
                    [
                        "python3.14",
                        "-m",
                        "pip",
                        "install",
                        "-q",
                        "-r",
                        requirements_path,
                    ]
                )

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
    if os.path.exists(services_dir):
        for service in os.listdir(services_dir):
            service_path = os.path.join(services_dir, service)
            src_path = os.path.join(service_path, "src")
            if os.path.isdir(service_path) and os.path.exists(src_path):
                print(f"\nType checking {service} service...")
                subprocess.run(
                    ["mypy", "src", "--explicit-package-bases"], cwd=service_path
                )


def test():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", type=str, help="Command to run")
    parser.add_argument("pytest_args", nargs="*", help="Arguments to pass to pytest")
    args = parser.parse_args()

    # Build pytest command
    pytest_cmd = ["pytest", "-v"]

    # Add any additional pytest arguments
    if args.pytest_args:
        pytest_cmd.extend(args.pytest_args)

    subprocess.run(pytest_cmd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", type=str, help="Command to run")
    parser.add_argument("pytest_args", nargs="*", help="Arguments to pass to pytest")
    args, unknown = parser.parse_known_args()

    if args.command == "clean":
        clean()
    elif args.command == "test":
        # Build pytest command
        pytest_cmd = ["pytest", "-v"]

        # Add any additional pytest arguments from unknown args
        if unknown:
            pytest_cmd.extend(unknown)

        subprocess.run(pytest_cmd)
    else:
        print("Invalid command")


if __name__ == "__main__":
    main()
