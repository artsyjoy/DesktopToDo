"""Stage the PyInstaller build as an MSIX layout for the Microsoft Store.

    python store/make_package.py <build_number>

Creates build/msix/ with AppxManifest.xml, Assets/ and DeskTodo/ (the app folder).
The workflow then runs makeappx.exe to turn it into DeskTodo.msix.
The Store signs the package itself, so no certificate is needed for uploading.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "store"
OUT = ROOT / "build" / "msix"
MAJOR, MINOR = 1, 5   # bump MINOR for big releases; the build number makes every upload unique


def main():
    build = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    ident = json.loads((STORE / "identity.json").read_text(encoding="utf-8"))
    values = {
        "name": ident["name"],
        "publisher": ident["publisher"],
        "publisher_display_name": ident["publisher_display_name"],
        "display_name": ident["display_name"],
        "version": f"{MAJOR}.{MINOR}.{build}.0",   # the Store requires the last number to be 0
    }
    manifest = (STORE / "AppxManifest.template.xml").read_text(encoding="utf-8")
    for key, val in values.items():
        manifest = manifest.replace("{{" + key + "}}", val)
    if "{{" in manifest:
        raise SystemExit("Unfilled value in AppxManifest template")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / "AppxManifest.xml").write_text(manifest, encoding="utf-8")
    shutil.copytree(STORE / "Assets", OUT / "Assets")
    shutil.copytree(ROOT / "dist" / "DeskTodo", OUT / "DeskTodo")
    placeholder = ident["name"].startswith("PLACEHOLDER")
    print(f"Staged MSIX layout v{values['version']} for {values['name']}"
          + ("  (PLACEHOLDER identity: test package only, not for upload)" if placeholder else ""))


if __name__ == "__main__":
    main()
