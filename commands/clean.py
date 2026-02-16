import os
import subprocess
import sys


def clean() -> None:
    """Run code quality checks on src/, tests/, and cli."""
    failures: list[str] = []
    successes: list[str] = []

    # Process src/ (the app)
    if os.path.exists("src"):
        print(f"\n{'='*60}")
        print("Processing src...")
        print(f"{'='*60}")
        src_failed = False

        print("🧹 Formatting src...")
        result = subprocess.run(
            [
                "autoflake",
                "--remove-all-unused-imports",
                "--remove-unused-variables",
                "--recursive",
                "src",
                "-i",
                "--exclude=__init__.py",
            ]
        )
        if result.returncode != 0:
            failures.append("src: autoflake failed")
            src_failed = True

        result = subprocess.run(
            ["isort", "src", "--profile", "black"], stdout=subprocess.DEVNULL
        )
        if result.returncode != 0:
            failures.append("src: isort failed")
            src_failed = True

        result = subprocess.run(["black", "src"], stdout=subprocess.DEVNULL)
        if result.returncode != 0:
            failures.append("src: black failed")
            src_failed = True

        print("🔍 Type checking src...")
        result = subprocess.run(["mypy", "src", "--explicit-package-bases"])
        if result.returncode != 0:
            failures.append("src: mypy type check failed")
            src_failed = True

        if not src_failed:
            successes.append("src")

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

    # Process cli.py + commands/
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
