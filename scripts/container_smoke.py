"""Exercise an image in an isolated container and disposable data volume."""

import argparse
import json
import subprocess
import time
import uuid


def docker(*args, data=None, quiet=False):
    result = subprocess.run(["docker", *args], input=data, text=True, capture_output=True, check=True)
    if result.stdout.strip() and not quiet:
        print(result.stdout.strip())
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="animescore:ci-test")
    args = parser.parse_args()
    name = "animescore-smoke-" + uuid.uuid4().hex[:12]
    volume = name + "-data"
    python = "/app/venv/bin/python"

    def run(code):
        return docker("exec", "-i", name, python, "-", data=code, quiet=True)

    def ready():
        for _ in range(30):
            try:
                run("import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/api/v1/health/ping', timeout=2)")
                return
            except subprocess.CalledProcessError:
                time.sleep(1)
        raise RuntimeError("Container did not become ready")

    try:
        docker("run", "--rm", "--network", "none", "--entrypoint", python, args.image, "-c",
               "import os; from pathlib import Path; assert os.getuid()==10001; "
               "assert not Path('/app/.env').exists(); assert not Path('/app/data/cache/ratings.sqlite3').exists(); "
               "assert not Path('/app/frontend/node_modules').exists(); assert Path('/app/LICENSE').exists()", quiet=True)
        docker("volume", "create", volume, quiet=True)
        docker("run", "-d", "--name", name, "--network", "none", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges:true", "-v", volume + ":/app/data/cache",
               "-e", "BANGUMI_DATA_AUTO_UPDATE=0", "-e", "SCORE_AUTO_UPDATE=0", "-e", "FILMARKS_AUTO_MAP=0",
               "-e", "ANIMESCORE_ADMIN_TOKEN=smoke-test-token", args.image, quiet=True)
        ready()
        payload = {"siteMeta": {}, "items": [{"title": "Container Smoke Anime", "titleTranslate": {},
                   "type": "tv", "lang": "ja", "officialSite": "", "begin": "2026-07-01T00:00:00Z",
                   "end": "", "broadcast": "", "sites": []}]}
        run("import json; from services.catalog import get_repository; get_repository().install(json.loads(" + repr(json.dumps(payload)) + "))")
        check = """
import json
import urllib.request
import urllib.error
base = 'http://127.0.0.1:5001'
def get(path, headers=None):
    with urllib.request.urlopen(urllib.request.Request(base+path, headers=headers or {}), timeout=5) as response:
        return response.read()
assert b'AnimeScore' in get('/')
assert len(get('/assets/app.js')) > 1000
assert b'AnimeScore' in get('/admin')
assert json.loads(get('/api/v1/health/'))['status'] == 'ok'
account = json.loads(get('/api/v1/auth/me'))
assert account['user'] is None and not account['login_enabled'] and not account['review_enabled']
try:
    get('/api/v1/admin/status')
    raise AssertionError('Anonymous administration was allowed')
except urllib.error.HTTPError as exc:
    assert exc.code == 401
headers = {'Authorization': 'Bearer smoke-test-token', 'Content-Type': 'application/json'}
item = json.loads(get('/api/v1/admin/mappings', headers))['items'][0]
assert item['name'] == 'Container Smoke Anime'
"""
        run(check + """
body = {'revision': item['mapping_revision'], 'changes': {'bgm': {'mode': 'manual', 'id': '123'}}}
request = urllib.request.Request(base+'/api/v1/admin/mappings/'+item['catalog_id'], data=json.dumps(body).encode(), headers=headers, method='PUT')
with urllib.request.urlopen(request) as response:
    assert json.load(response)['item']['ids']['bgm_id'] == '123'
""")
        docker("restart", "--time", "90", name, quiet=True)
        ready()
        run(check + "\nassert item['ids']['bgm_id'] == '123'\nassert item['mapping_revision'] == 1\n")
        print("Container smoke passed: frontend, API, auth isolation, non-root writes and mapping persistence.")
    except Exception:
        subprocess.run(["docker", "logs", "--tail", "80", name], check=False)
        raise
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", volume], capture_output=True, check=False)


if __name__ == "__main__":
    main()
