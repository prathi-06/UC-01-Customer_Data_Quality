import os
import subprocess
import sys
import time
from pathlib import Path
import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.harness import mint_token

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_PATH):
    CHROME_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

def wait_for_server(url: str, timeout: int = 15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = httpx.get(url)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def take_screenshot(url: str, output_path: Path):
    cmd = [
        CHROME_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--window-size=1200,900",
        f"--screenshot={str(output_path)}",
        url
    ]
    subprocess.run(cmd, check=True)

def main():
    ui_dir = BASE_DIR / "evidence" / "ui"
    ui_dir.mkdir(parents=True, exist_ok=True)

    print("Starting uvicorn server...")
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(BASE_DIR)
    )

    try:
        health_url = "http://127.0.0.1:8000/health"
        if not wait_for_server(health_url):
            print("Server failed to start in time.", file=sys.stderr)
            sys.exit(1)
        print("Server is up and healthy.")

        # 1. Unauthenticated screen
        print("Capturing 01_tools_unauth.png...")
        take_screenshot("http://127.0.0.1:8000/", ui_dir / "01_tools_unauth.png")

        # 2. Authenticated Acme Pro Operator
        acme_tok = mint_token("acme:Operator")
        print("Capturing 02_tools_pro_active.png...")
        # give browser a moment to render JS
        take_screenshot(f"http://127.0.0.1:8000/?token={acme_tok}", ui_dir / "02_tools_pro_active.png")

        # 3. Authenticated Globex Basic Operator (Process disabled)
        globex_tok = mint_token("globex:Operator")
        print("Capturing 03_tools_basic.png...")
        take_screenshot(f"http://127.0.0.1:8000/?token={globex_tok}", ui_dir / "03_tools_basic.png")

        print("UI screenshots captured successfully in evidence/ui/")

    finally:
        server_process.terminate()
        server_process.wait()

if __name__ == "__main__":
    main()
