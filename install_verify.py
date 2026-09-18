#!/usr/bin/env python
"""inventree-mbom: Installation verification script.

Run this OUTSIDE InvenTree's venv to check prerequisites,
then follow the step-by-step instructions to install.

Usage:
    python install_verify.py
"""

import subprocess, sys, os, json

BASE = os.path.dirname(os.path.abspath(__file__))
INVENTREE_URL = "http://127.0.0.1:8000"

def check(label, ok, detail=""):
    status = "\033[92m✓\033[0m" if ok else "\033[91m✗\033[0m"
    print(f"  {status}  {label}" + (f"\n     {detail}" if detail else ""))
    return ok

def main():
    print("\n\033[1m=== inventree-mbom Installation Checker ===\033[0m\n")

    # Check plugin files exist
    required = [
        "setup.py",
        "inventree_mbom/__init__.py",
        "inventree_mbom/core.py",
        "inventree_mbom/models.py",
        "inventree_mbom/migrations/0001_initial.py",
    ]
    for f in required:
        path = os.path.join(BASE, f)
        check(f"File exists: {f}", os.path.exists(path))

    print()

    # Check InvenTree is running
    import urllib.request, urllib.error
    try:
        r = urllib.request.urlopen(f"{INVENTREE_URL}/api/", timeout=3)
        check(f"InvenTree reachable at {INVENTREE_URL}", r.status == 200)
    except Exception as e:
        check(f"InvenTree reachable at {INVENTREE_URL}", False, str(e))

    print()
    print("\033[1mInstallation Steps:\033[0m")
    print()
    print("  1. Activate InvenTree virtual environment:")
    print("       source /path/to/inventree/venv/bin/activate   # Linux/Mac")
    print("       .\\inventree-venv\\Scripts\\Activate.ps1         # Windows")
    print()
    print(f"  2. Install plugin in editable mode:")
    print(f"       pip install -e {BASE}")
    print()
    print("  3. Restart InvenTree to load the plugin:")
    print("       invoke server   # or restart your docker/gunicorn process")
    print()
    print("  4. Enable the plugin in InvenTree:")
    print("       Settings → Plugins → Find 'ManufacturingBOMPlugin' → Enable")
    print()
    print("  5. Run database migrations:")
    print("       python manage.py migrate inventree_mbom")
    print("       # or: invoke migrate")
    print()
    print("  6. Create test data:")
    print("       python manage.py mbom_create_test_data")
    print()
    print("  7. Verify at: http://127.0.0.1:8000/web/")
    print("     → Navigate to any assembly part")
    print("     → Look for 'Manufacturing Routing (mBOM)' tab")
    print()

if __name__ == "__main__":
    main()
