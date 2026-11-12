"""真实容器验收：只读根文件系统、同源代理、SPA路由与卷中策略持久化。"""
import argparse
import json
import os
import re
import subprocess
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-image", default="myquant-backend:verify")
    parser.add_argument("--frontend-image", default="myquant-frontend:verify")
    args = parser.parse_args()
    prefix = "myquant-check-" + uuid.uuid4().hex[:8]
    network, volume, backend, frontend = [prefix + suffix for suffix in ("-net", "-data", "-api", "-web")]
    environment = os.environ.copy()
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        environment.pop(key, None)
    def docker(*command):
        return subprocess.check_output(["docker", "--host=unix:///var/run/docker.sock", *command], env=environment, text=True).strip()
    def request(base, path, payload=None):
        req = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=3) as response:
            return response.status, response.read().decode()
    def wait(base):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                if request(base, "/api/health/ready")[0] == 200:
                    return
            except (URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(.4)
        raise RuntimeError("容器健康检查超时")
    security = ["--read-only", "--tmpfs", "/tmp:rw,nosuid,size=128m", "--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
    backendRun = ["run", "-d", "--name", backend, "--network", network, "--network-alias", "myquant-backend", *security,
                  "-v", volume + ":/var/lib/myquant", "-e", "QUANT_CORS_ORIGINS=", args.backend_image]
    created = []
    try:
        docker("network", "create", network)
        docker("volume", "create", volume)
        docker(*backendRun)
        created.append(backend)
        docker("run", "-d", "--name", frontend, "--network", network, *security,
               "-p", "127.0.0.1::8080", "-e", "API_UPSTREAM=myquant-backend:8080", args.frontend_image)
        created.append(frontend)
        port = docker("port", frontend, "8080/tcp").split(":")[-1]
        base = "http://127.0.0.1:" + port
        wait(base)
        assert request(base, "/healthz")[0] == 200
        html = request(base, "/strategies")[1]
        script = re.search(r'src="([^"]+\.js)"', html)
        style = re.search(r'href="([^"]+\.css)"', html)
        assert script and style, "生产页面应引用Vue构建产物"
        for asset in (script.group(1), style.group(1)):
            status, content = request(base, asset)
            assert status == 200 and len(content) > 100 and not content.lstrip().lower().startswith("<!doctype"), "静态产物不可读或错误回退为HTML"
        assert json.loads(request(base, "/api/health/live")[1])["status"] == "ok"
        assert not json.loads(request(base, "/api/strategies/capabilities")[1])["configured"]
        try:
            request(base, "/api/does-not-exist")
            raise AssertionError("未知API不能回退为前端HTML")
        except HTTPError as exc:
            assert exc.code == 404 and "json" in exc.headers.get("Content-Type", "")
        condition = {"left": {"kind": "close"}, "op": "gt", "right": {"kind": "constant", "value": 10}}
        spec = {"name": "容器持久化验收", "entry": {"conditions": [condition]}, "exit": {"conditions": [{**condition, "op": "lt"}]}}
        item = json.loads(request(base, "/api/strategies/library", {"spec": spec})[1])
        factor = {"market": "cn", "symbol": "600519", "factor": "event_score", "source": "容器合成验证",
                  "observations": [{"availableAt": "2024-01-02T10:00:00+08:00", "value": 1}]}
        assert request(base, "/api/strategies/factors", factor)[0] == 200
        docker("exec", backend, "python", "-c", """
import pandas as pd
from app.data.contract import describeBars
from app.data.store import saveBars
prices = [9., 11., 12., 13.]
frame = pd.DataFrame({'date': pd.date_range('2024-01-02', periods=4), 'open': prices, 'close': prices,
                      'high': [p + 1 for p in prices], 'low': [p - 1 for p in prices], 'volume': 1000.})
frame = describeBars(frame, 'cn', '600519', 'day', source='container_fixture', adjustment='none', volumeUnit='share')
saveBars(frame, 'cn', '600519')
"""
        )
        execution = {"spec": spec, "symbols": [{"market": "cn", "symbol": "600519"}], "feeRate": 0}
        result = json.loads(request(base, "/api/strategies/execute", execution)[1])["results"][0]
        assert result["trades"][0]["entryDate"] == "2024-01-04"
        assert result["dataInfo"]["source"] == "container_fixture"
        docker("rm", "-f", backend)
        docker(*backendRun)
        docker("restart", frontend)
        port = docker("port", frontend, "8080/tcp").split(":")[-1]
        base = "http://127.0.0.1:" + port
        wait(base)
        assert json.loads(request(base, "/api/strategies/library")[1])[0]["id"] == item["id"]
        assert json.loads(request(base, "/api/strategies/factors")[1])[0]["factor"] == "event_score"
        restored = json.loads(request(base, "/api/strategies/execute", execution)[1])["results"][0]
        assert restored["equityCurve"] == result["equityCurve"]
        print("PASS: Vue/Python独立容器、非root/只读根目录、SPA与静态资源/API代理、健康探针、真实规则回测、容器重建后行情/策略/因子持久化")
    except Exception:
        for container in created:
            try:
                print(f"{container}: " + docker("inspect", "--format", "{{.State.Status}} / exit {{.State.ExitCode}} / {{.State.Error}}", container), flush=True)
                print(docker("logs", "--tail", "35", container), flush=True)
            except subprocess.CalledProcessError:
                pass
        raise
    finally:
        for container in reversed(created):
            try:
                docker("rm", "-f", container)
            except subprocess.CalledProcessError:
                pass
        for command in (("volume", "rm", volume), ("network", "rm", network)):
            try:
                docker(*command)
            except subprocess.CalledProcessError:
                pass


if __name__ == "__main__":
    main()
