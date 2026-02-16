import os
import subprocess
import sys


def clean() -> None:
    """Run code quality checks on all services, tests, and cli.py"""
    services_dir = "services"
    failures: list[str] = []
    successes: list[str] = []

    # Process each service individually
    if os.path.exists(services_dir):
        for service in sorted(os.listdir(services_dir)):
            service_path = os.path.join(services_dir, service)
            requirements_path = os.path.join(service_path, "requirements.txt")
            src_path = os.path.join(service_path, "src")

            if not (os.path.isdir(service_path) and os.path.exists(src_path)):
                continue

            print(f"\n{'='*60}")
            print(f"Processing {service} service...")
            print(f"{'='*60}")

            service_failed = False

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
                ["isort", service_path, "--profile", "black"], stdout=subprocess.DEVNULL
            )
            if result.returncode != 0:
                failures.append(f"{service}: isort failed")
                service_failed = True

            result = subprocess.run(["black", service_path], stdout=subprocess.DEVNULL)
            if result.returncode != 0:
                failures.append(f"{service}: black failed")
                service_failed = True

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
    print("Processing tests...")
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

    # Process cli.py + cli/
    print(f"\n{'='*60}")
    print("Processing cli...")
    print(f"{'='*60}")
    cli_failed = False

    print("🧹 Formatting cli...")
    for target in ["cli.py", "commands"]:
        result = subprocess.run(
            [
                "autoflake",
                "--remove-all-unused-imports",
                "--remove-unused-variables",
                "--recursive",
                target,
                "-i",
                "--exclude=__init__.py",
            ]
        )
        if result.returncode != 0:
            failures.append(f"{target}: autoflake failed")
            cli_failed = True

        result = subprocess.run(
            ["isort", target, "--profile", "black"], stdout=subprocess.DEVNULL
        )
        if result.returncode != 0:
            failures.append(f"{target}: isort failed")
            cli_failed = True

        result = subprocess.run(["black", target], stdout=subprocess.DEVNULL)
        if result.returncode != 0:
            failures.append(f"{target}: black failed")
            cli_failed = True

    print("🔍 Type checking cli...")
    result = subprocess.run(["mypy", "cli.py", "commands"])
    if result.returncode != 0:
        failures.append("cli: mypy type check failed")
        cli_failed = True

    if not cli_failed:
        successes.append("cli")

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
