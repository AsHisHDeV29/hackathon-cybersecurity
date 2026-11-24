"""Start the local Ollama runtime and NETRA together; reuse an existing runtime."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent

def installed_models(url):
    try:
        with urllib.request.urlopen(url + "/api/tags", timeout=2) as response:
            return [model["name"] for model in json.load(response)["models"]]
    except (OSError, ValueError, KeyError):
        return None

def main():
    def shutdown(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    runtime = None
    server = None
    environment = os.environ.copy()
    environment.setdefault("OLLAMA_MODEL", "llama3.2:3b")
    environment.setdefault("OLLAMA_MODELS", str(ROOT / ".runtime" / "models"))
    environment.setdefault("OLLAMA_NO_CLOUD", "1")
    url = environment.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    binary = shutil.which("ollama") or str(ROOT / ".runtime" / "ollama" / "bin" / "ollama")
    try:
        if environment.get("NETRA_ENGINE") != "rules":
            installed = installed_models(url)
            if installed is None:
                if url != "http://127.0.0.1:11434":
                    raise RuntimeError("Configured OLLAMA_URL is unreachable. Start that runtime first.")
                if not Path(binary).is_file():
                    raise RuntimeError("Ollama is not installed. Follow README.md for the local runtime setup.")
                environment["OLLAMA_HOST"] = "127.0.0.1:11434"
                runtime = subprocess.Popen([binary, "serve"], env=environment, cwd=ROOT)
                for _ in range(60):
                    installed = installed_models(url)
                    if installed is not None:
                        break
                    if runtime.poll() is not None:
                        raise RuntimeError("Ollama exited before it was ready.")
                    time.sleep(.5)
                else:
                    raise RuntimeError("Ollama did not become ready within 30 seconds.")
            model = environment["OLLAMA_MODEL"]
            if model not in installed and model + ":latest" not in installed:
                if not Path(binary).is_file():
                    raise RuntimeError(f"Install {model} in the configured Ollama runtime first.")
                environment["OLLAMA_HOST"] = url
                print(f"Downloading {model} on first run…", flush=True)
                subprocess.run([binary, "pull", model], env=environment, cwd=ROOT, check=True)
        server = subprocess.Popen([sys.executable, "-m", "backend.server"], cwd=ROOT, env=environment)
        return server.wait()
    except KeyboardInterrupt:
        return 0
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        return 1
    finally:
        for process in (server, runtime):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

if __name__ == "__main__":
    sys.exit(main())
