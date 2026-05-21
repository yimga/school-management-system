#!/usr/bin/env python
"""Capture authenticated /backend dashboard screenshots locally.

Usage:
  python scripts/dev/capture_backend_screenshot.py
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


ROOT = Path(__file__).resolve().parents[2]
HOST = "127.0.0.1"
PORT = 8765
BASE = f"http://{HOST}:{PORT}"
LOGIN_URL = f"{BASE}/authentication/login/?next=/authentication/backend/"
OUT_DIR = ROOT / "tmp" / "screenshots"
USER = "codex_preview"
PASSWORD = "Preview123!"


def wait_for_port(host: str, port: int, timeout: float = 45.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.4)
    raise TimeoutError(f"Server did not start on {host}:{port} in {timeout}s")


def build_driver() -> webdriver.Remote:
    errors: list[str] = []

    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-dev-shm-usage")
        return webdriver.Chrome(options=options)
    except Exception as exc:  # pragma: no cover
        errors.append(f"Chrome failed: {exc}")

    try:
        options = webdriver.EdgeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        return webdriver.Edge(options=options)
    except Exception as exc:  # pragma: no cover
        errors.append(f"Edge failed: {exc}")

    raise RuntimeError("No browser driver available. " + " | ".join(errors))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", f"{HOST}:{PORT}", "--noreload"],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    driver: webdriver.Remote | None = None
    try:
        wait_for_port(HOST, PORT)
        driver = build_driver()
        wait = WebDriverWait(driver, 30)
        print("Stage: open login")

        driver.get(LOGIN_URL)
        (OUT_DIR / "debug").mkdir(parents=True, exist_ok=True)
        driver.save_screenshot(str(OUT_DIR / "debug" / "01-login-page.png"))
        wait.until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(
            USER
        )
        wait.until(EC.presence_of_element_located((By.NAME, "password"))).send_keys(
            PASSWORD
        )
        wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
            )
        ).click()
        print("Stage: submitted login")
        time.sleep(1.0)
        driver.save_screenshot(str(OUT_DIR / "debug" / "02-after-submit.png"))
        print(f"After submit URL: {driver.current_url}")

        # Wait for post-login redirect to settle (backend, redirect, or school picker)
        start_url = LOGIN_URL
        WebDriverWait(driver, 30).until(lambda d: d.current_url != start_url)
        current = driver.current_url
        print(f"Post-login URL: {current}")
        driver.save_screenshot(str(OUT_DIR / "debug" / "03-post-login.png"))

        if "/school-picker/" in current:
            print("Stage: school picker detected")
            radios = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            if radios:
                radios[0].click()
            picker_submit = driver.find_elements(
                By.CSS_SELECTOR, "button[type='submit'], input[type='submit']"
            )
            if picker_submit:
                picker_submit[0].click()
            time.sleep(1.0)
            driver.save_screenshot(
                str(OUT_DIR / "debug" / "04-after-school-picker.png")
            )

        if "/authentication/mfa/" in driver.current_url:
            print("Stage: MFA page detected; redirecting to backend for debug capture")
            driver.save_screenshot(str(OUT_DIR / "debug" / "04-mfa-page.png"))

        if "/authentication/backend" not in driver.current_url:
            driver.get(f"{BASE}/authentication/backend/")
            time.sleep(0.8)
            print(f"After direct backend GET URL: {driver.current_url}")
            driver.save_screenshot(
                str(OUT_DIR / "debug" / "05-after-direct-backend.png")
            )

        wait.until(EC.url_contains("/authentication/backend"))
        wait.until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    ".backend-v2-workspace, #dashboard-layout, .backend-v2-panel, .admin-dashboard-grid",
                )
            )
        )
        time.sleep(1.4)

        driver.set_window_size(1920, 1080)
        time.sleep(0.4)
        shot_1920 = OUT_DIR / "backend-final-1920x1080.png"
        driver.save_screenshot(str(shot_1920))

        driver.set_window_size(1536, 864)
        time.sleep(0.4)
        shot_1536 = OUT_DIR / "backend-final-1536x864.png"
        driver.save_screenshot(str(shot_1536))

        driver.set_window_size(1366, 768)
        time.sleep(0.4)
        shot_1366 = OUT_DIR / "backend-final-1366x768.png"
        driver.save_screenshot(str(shot_1366))

        print(str(shot_1920))
        print(str(shot_1536))
        print(str(shot_1366))
        return 0
    except TimeoutException as exc:
        if driver is not None:
            try:
                print(f"Timeout URL: {driver.current_url}")
                driver.save_screenshot(str(OUT_DIR / "debug" / "99-timeout.png"))
                (OUT_DIR / "debug" / "99-timeout.html").write_text(
                    driver.page_source, encoding="utf-8"
                )
            except Exception:
                pass
        print(f"Timeout while capturing screenshot: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"Failed to capture screenshot: {exc}", file=sys.stderr)
        return 1
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        try:
            server.terminate()
            server.wait(timeout=10)
        except Exception:
            try:
                server.kill()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
