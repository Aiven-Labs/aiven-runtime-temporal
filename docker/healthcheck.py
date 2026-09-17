import subprocess
import urllib.request

subprocess.run(["temporal", "operator", "cluster", "health", "--address", "127.0.0.1:7233"],
               check=True, timeout=5, stdout=subprocess.DEVNULL)
with urllib.request.urlopen("http://127.0.0.1:8081", timeout=3) as response:
    assert response.status == 200
