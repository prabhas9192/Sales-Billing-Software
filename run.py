#!/usr/bin/env python3
"""
BillFlow — Modern Sales & Billing Software
Entry point
"""
import sys

def main():
    try:
        from billflow.app import BillFlowApp
    except ImportError as exc:
        print(f"Error starting BillFlow: {exc}", file=sys.stderr)
        sys.exit(1)

    app = BillFlowApp()
    app.run()

if __name__ == "__main__":
    main()
