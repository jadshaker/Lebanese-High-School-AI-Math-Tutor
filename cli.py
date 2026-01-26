import argparse
import os
import subprocess


def clean():
    """Run code quality checks on all services, tests, and cli.py"""
    services_dir = "services"

    # Process each service individually
    if os.path.exists(services_dir):
        for service in sorted(os.listdir(services_dir)):
            service_path = os.path.join(services_dir, service)
            requirements_path = os.path.join(service_path, "requirements.txt")
            src_path = os.path.join(service_path, "src")

            # Only process directories that have a src/ folder
            if not (os.path.isdir(service_path) and os.path.exists(src_path)):
                continue

            print(f"\n{'='*60}")
            print(f"Processing {service} service...")
            print(f"{'='*60}")

            # Step 1: Install dependencies
            if os.path.isfile(requirements_path):
                print(f"📦 Installing dependencies for {service}...")
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

            # Step 2: Format code
            print(f"🧹 Formatting {service}...")
            subprocess.run(
                [
                    "autoflake",
                    "--remove-all-unused-imports",
                    "--remove-unused-variables",
                    "--recursive",
                    service_path,
                    "-i",
                    "--exclude=__init__.py",
                ]
            )
            subprocess.run(
                ["isort", service_path, "--profile", "black"],
                stdout=subprocess.DEVNULL,
            )
            subprocess.run(["black", service_path], stdout=subprocess.DEVNULL)

            # Step 3: Type check
            print(f"🔍 Type checking {service}...")
            subprocess.run(
                ["mypy", "src", "--explicit-package-bases"], cwd=service_path
            )

    # Process tests directory
    print(f"\n{'='*60}")
    print(f"Processing tests...")
    print(f"{'='*60}")
    if os.path.exists("tests"):
        print("🧹 Formatting tests...")
        subprocess.run(
            [
                "autoflake",
                "--remove-all-unused-imports",
                "--remove-unused-variables",
                "--recursive",
                "tests",
                "-i",
                "--exclude=__init__.py",
            ]
        )
        subprocess.run(
            ["isort", "tests", "--profile", "black"], stdout=subprocess.DEVNULL
        )
        subprocess.run(["black", "tests"], stdout=subprocess.DEVNULL)

    # Process cli.py
    print(f"\n{'='*60}")
    print(f"Processing cli.py...")
    print(f"{'='*60}")
    print("🧹 Formatting cli.py...")
    subprocess.run(
        [
            "autoflake",
            "--remove-all-unused-imports",
            "--remove-unused-variables",
            "cli.py",
            "-i",
        ]
    )
    subprocess.run(["isort", "cli.py", "--profile", "black"], stdout=subprocess.DEVNULL)
    subprocess.run(["black", "cli.py"], stdout=subprocess.DEVNULL)

    print("🔍 Type checking cli.py...")
    subprocess.run(["mypy", "cli.py"])

    print(f"\n{'='*60}")
    print("✅ All done!")
    print(f"{'='*60}")


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
