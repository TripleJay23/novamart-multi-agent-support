"""Smoke-test a built ARM64 image without AWS credentials or cloud resources.

Run from the repository root:
    python tool/verify_container.py --image novamart-support:local-arm64
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
SESSION = "00000000-0000-4000-8000-000000000001"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="novamart-support:local-arm64")
    args = parser.parse_args()
    docker = shutil.which("docker")
    if docker is None:
        parser.error("Docker is not on PATH; reopen the shell or add its bin directory.")

    def command(*parts: str) -> str:
        result = subprocess.run(
            [docker, *parts], capture_output=True, text=True, check=True, timeout=60,
        )
        return result.stdout.strip()

    report: dict[str, object] = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "image_tag": args.image,
        "scope": "Local ARM64 container only; no AWS credentials, mounts, or model calls.",
        "checks": [],
        "ok": False,
    }
    checks: list[dict[str, object]] = []
    report["checks"] = checks
    container_id = ""
    success = False
    try:
        image = json.loads(command("image", "inspect", args.image))[0]
        report["image"] = {
            "id": image["Id"], "os": image["Os"], "architecture": image["Architecture"],
            "user": image["Config"]["User"], "command": image["Config"]["Cmd"],
            "repo_digests": image.get("RepoDigests", []),
        }
        assert (image["Os"], image["Architecture"]) == ("linux", "arm64")
        assert image["Config"]["User"] == "10001:10001"
        print(f"Image verified: linux/arm64, {image['Id']}", flush=True)

        container_id = command(
            "run", "--detach", "--platform", "linux/arm64",
            "--publish", "127.0.0.1::8080", "--env", "AWS_EC2_METADATA_DISABLED=true",
            args.image,
        )
        assert re.fullmatch(r"[a-f0-9]{64}", container_id)
        report["container_id"] = container_id
        container = json.loads(command("inspect", container_id))[0]
        assert container["Image"] == image["Id"]
        assert container["Mounts"] == []
        environment = container["Config"]["Env"]
        assert not any(e.startswith((
            "AWS_ACCESS_KEY_ID=", "AWS_SECRET_ACCESS_KEY=", "AWS_SESSION_TOKEN=",
        )) for e in environment)
        assert command("exec", container_id, "id", "-u") == "10001"
        report["python_version"] = command(
            "exec", container_id, "/app/.venv/bin/python", "--version",
        )
        report["machine"] = command("exec", container_id, "uname", "-m")
        checks.append({"name": "non_root_without_credentials_or_mounts", "passed": True})

        source = ROOT / "src/novamart_support"
        digest = hashlib.sha256()
        for path in sorted(source.rglob("*.py")):
            digest.update(path.relative_to(source).as_posix().encode() + b"\0" + path.read_bytes())
        installed_digest = command(
            "exec", container_id, "/app/.venv/bin/python", "-c",
            "from pathlib import Path; import hashlib, novamart_support; "
            "root=Path(novamart_support.__file__).parent; h=hashlib.sha256(); "
            "[(h.update(p.relative_to(root).as_posix().encode()+b'\\0'+p.read_bytes())) "
            "for p in sorted(root.rglob('*.py'))]; print(h.hexdigest())",
        )
        assert installed_digest == digest.hexdigest()
        report["application_source_sha256"] = installed_digest
        checks.append({"name": "installed_source_matches_working_tree", "passed": True})

        address = command("port", container_id, "8080/tcp")
        assert re.fullmatch(r"127\.0\.0\.1:\d+", address)
        base_url = f"http://{address}"
        opener = build_opener(ProxyHandler({}))

        def request(path: str, payload: dict | None = None, *, session: bool = False) -> dict:
            headers = {"Content-Type": "application/json"}
            if session:
                headers["X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"] = SESSION
            body = json.dumps(payload).encode() if payload is not None else None
            invocation = Request(base_url + path, data=body, headers=headers)
            with opener.open(invocation, timeout=3) as res:
                assert res.status == 200
                return json.load(res)

        deadline = time.monotonic() + 60
        while True:
            try:
                health = request("/ping")
                break
            except (URLError, TimeoutError, ConnectionError):
                if time.monotonic() >= deadline:
                    raise
                time.sleep(1)
        assert health["status"] == "Healthy"
        checks.append({"name": "health_endpoint", "passed": True, "response": health})
        print("Health endpoint passed.", flush=True)

        cases = [
            ("missing_session", {"query": "hello"}, False, "invalid_request"),
            ("missing_query", {}, True, "invalid_request"),
            ("session_override", {"query": "hello", "session_id": "foreign"}, True,
             "invalid_request"),
            ("missing_cloud_configuration", {"query": "hello"}, True, "configuration_error"),
        ]
        for name, payload, session, expected in cases:
            result = request("/invocations", payload, session=session)
            assert result["ok"] is False
            assert result["error"]["code"] == expected
            checks.append({"name": name, "passed": True, "response": result})
            print(f"{name}: {expected} (passed)", flush=True)
        success = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"Container verification failed: {report['error']}", flush=True)
    finally:
        if re.fullmatch(r"[a-f0-9]{64}", container_id):
            try:
                logs = subprocess.run(
                    [docker, "logs", container_id], capture_output=True, text=True, timeout=30,
                )
                (ROOT / "docs/evidence/container-runtime.txt").write_text(
                    logs.stdout + logs.stderr, encoding="utf-8",
                )
            finally:
                # Remove only the isolated container created by this invocation.
                cleanup = subprocess.run(
                    [docker, "rm", "--force", container_id],
                    capture_output=True, text=True, timeout=30,
                )
                report["container_removed"] = cleanup.returncode == 0
                success = success and cleanup.returncode == 0
        report["ok"] = success
        output = ROOT / "docs/evidence/container-smoke.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Evidence saved to {output.relative_to(ROOT)}", flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
