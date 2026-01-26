import argparse
import os
import subprocess
import sys


def clean():
    """Run code quality checks on all services, tests, and cli.py"""
    services_dir = "services"
    failures = []
    successes = []

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

            service_failed = False

            # Step 1: Install dependencies
            if os.path.isfile(requirements_path):
                print(f"📦 Installing dependencies for {service}...")
                result = subprocess.run(
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
                if result.returncode != 0:
                    failures.append(f"{service}: dependency installation failed")
                    service_failed = True

            # Step 2: Format code
            print(f"🧹 Formatting {service}...")
            result = subprocess.run(
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
            if result.returncode != 0:
                failures.append(f"{service}: autoflake failed")
                service_failed = True

            result = subprocess.run(
                ["isort", service_path, "--profile", "black"],
                stdout=subprocess.DEVNULL,
            )
            if result.returncode != 0:
                failures.append(f"{service}: isort failed")
                service_failed = True

            result = subprocess.run(["black", service_path], stdout=subprocess.DEVNULL)
            if result.returncode != 0:
                failures.append(f"{service}: black failed")
                service_failed = True

            # Step 3: Type check
            print(f"🔍 Type checking {service}...")
            result = subprocess.run(
                ["mypy", "src", "--explicit-package-bases"], cwd=service_path
            )
            if result.returncode != 0:
                failures.append(f"{service}: mypy type check failed")
                service_failed = True

            if not service_failed:
                successes.append(service)

    # Process tests directory
    print(f"\n{'='*60}")
    print(f"Processing tests...")
    print(f"{'='*60}")
    tests_failed = False

    if os.path.exists("tests"):
        print("🧹 Formatting tests...")
        result = subprocess.run(
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
        if result.returncode != 0:
            failures.append("tests: autoflake failed")
            tests_failed = True

        result = subprocess.run(
            ["isort", "tests", "--profile", "black"], stdout=subprocess.DEVNULL
        )
        if result.returncode != 0:
            failures.append("tests: isort failed")
            tests_failed = True

        result = subprocess.run(["black", "tests"], stdout=subprocess.DEVNULL)
        if result.returncode != 0:
            failures.append("tests: black failed")
            tests_failed = True

    if not tests_failed:
        successes.append("tests")

    # Process cli.py
    print(f"\n{'='*60}")
    print(f"Processing cli.py...")
    print(f"{'='*60}")
    cli_failed = False

    print("🧹 Formatting cli.py...")
    result = subprocess.run(
        [
            "autoflake",
            "--remove-all-unused-imports",
            "--remove-unused-variables",
            "cli.py",
            "-i",
        ]
    )
    if result.returncode != 0:
        failures.append("cli.py: autoflake failed")
        cli_failed = True

    result = subprocess.run(
        ["isort", "cli.py", "--profile", "black"], stdout=subprocess.DEVNULL
    )
    if result.returncode != 0:
        failures.append("cli.py: isort failed")
        cli_failed = True

    result = subprocess.run(["black", "cli.py"], stdout=subprocess.DEVNULL)
    if result.returncode != 0:
        failures.append("cli.py: black failed")
        cli_failed = True

    print("🔍 Type checking cli.py...")
    result = subprocess.run(["mypy", "cli.py"])
    if result.returncode != 0:
        failures.append("cli.py: mypy type check failed")
        cli_failed = True

    if not cli_failed:
        successes.append("cli.py")

    # Print summary
    print(f"\n{'='*60}")
    print("📊 SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Successful: {len(successes)}")
    for item in successes:
        print(f"   ✓ {item}")

    if failures:
        print(f"\n❌ Failed: {len(failures)}")
        for failure in failures:
            print(f"   ✗ {failure}")

    print(f"\n{'='*60}")
    if failures:
        print("❌ Code quality checks FAILED")
        print(f"{'='*60}")
        sys.exit(1)
    else:
        print("✅ All code quality checks PASSED")
        print(f"{'='*60}")
        sys.exit(0)


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

    result = subprocess.run(pytest_cmd)
    sys.exit(result.returncode)


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

        result = subprocess.run(pytest_cmd)
        sys.exit(result.returncode)
    else:
        print("Invalid command")
        sys.exit(1)


if __name__ == "__main__":
    main()
