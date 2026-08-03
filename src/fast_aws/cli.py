"""CLI entrypoint: `fast-aws`."""

from __future__ import annotations

import argparse
import sys

from fast_aws.app import FastAwsApp
from fast_aws.auth import list_profiles


def _print_profiles() -> None:
    profiles = list_profiles()
    if not profiles:
        print("No profiles found in ~/.aws/config")
        sys.exit(1)
    width = max(len(p.name) for p in profiles)
    for p in profiles:
        badge = "SSO" if p.is_sso else "key"
        region = f"region={p.region}" if p.region else "region=(default)"
        print(f"  {p.name:<{width}}  [{badge}]  {region}")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="fast-aws",
        description="Fast TUI browser for AWS resources using local profiles & SSO.",
    )
    parser.add_argument(
        "-p", "--profile", help="AWS profile to use (defaults to interactive picker)"
    )
    parser.add_argument("-r", "--region", help="AWS region override (defaults to profile/env)")
    parser.add_argument(
        "--edit",
        action="store_true",
        help="opt into Edit mode (mutating actions); Readonly is the default",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="list discovered AWS profiles and exit",
    )
    args = parser.parse_args()

    if args.list_profiles:
        _print_profiles()
        return

    app = FastAwsApp(profile=args.profile, region=args.region, readonly=not args.edit)
    app.run()


if __name__ == "__main__":
    main()
