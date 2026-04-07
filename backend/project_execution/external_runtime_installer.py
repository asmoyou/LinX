from __future__ import annotations

import hashlib
import io
import tarfile
import textwrap
import zipfile
from pathlib import Path

from project_execution.external_runtime_schemas import (
    ExternalRuntimeArtifactManifestResponse,
    ExternalRuntimeArtifactRecord,
)
from project_execution.external_runtime_service import (
    CURRENT_EXTERNAL_RUNTIME_VERSION,
    SUPPORTED_EXTERNAL_TARGETS,
)

_ASSET_ROOT = Path(__file__).resolve().parent / "runtime_assets"
_RUNTIME_SCRIPT_PATH = _ASSET_ROOT / "linx_external_runtime.py"


def _read_runtime_script_bytes() -> bytes:
    return _RUNTIME_SCRIPT_PATH.read_bytes()


def _runtime_payload_text(version: str, target_os: str, arch: str) -> str:
    return textwrap.dedent(
        f"""
        LinX external runtime package
        version={version}
        os={target_os}
        arch={arch}
        entrypoint=bin/linx_external_runtime.py
        """
    ).strip() + "\n"


def build_artifact_bytes(version: str, target_os: str, arch: str) -> tuple[bytes, str, str]:
    folder_name = f"linx-external-runtime_{version}_{target_os}_{arch}"
    readme_bytes = _runtime_payload_text(version, target_os, arch).encode("utf-8")
    runtime_bytes = _read_runtime_script_bytes()
    if target_os == "windows":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{folder_name}/README.txt", readme_bytes)
            zf.writestr(f"{folder_name}/bin/linx_external_runtime.py", runtime_bytes)
        return buf.getvalue(), f"{folder_name}.zip", "application/zip"

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        readme_info = tarfile.TarInfo(name=f"{folder_name}/README.txt")
        readme_info.size = len(readme_bytes)
        tar.addfile(readme_info, io.BytesIO(readme_bytes))

        runtime_info = tarfile.TarInfo(name=f"{folder_name}/bin/linx_external_runtime.py")
        runtime_info.mode = 0o755
        runtime_info.size = len(runtime_bytes)
        tar.addfile(runtime_info, io.BytesIO(runtime_bytes))
    return buf.getvalue(), f"{folder_name}.tar.gz", "application/gzip"


def build_manifest(base_url: str) -> ExternalRuntimeArtifactManifestResponse:
    artifacts: list[ExternalRuntimeArtifactRecord] = []
    for target_os, archs in SUPPORTED_EXTERNAL_TARGETS.items():
        for arch in archs:
            payload, _filename, _content_type = build_artifact_bytes(
                CURRENT_EXTERNAL_RUNTIME_VERSION,
                target_os,
                arch,
            )
            digest = hashlib.sha256(payload).hexdigest()
            artifacts.append(
                ExternalRuntimeArtifactRecord(
                    version=CURRENT_EXTERNAL_RUNTIME_VERSION,
                    os=target_os,
                    arch=arch,
                    sha256=digest,
                    download_path=(
                        f"{base_url}/api/v1/external-runtime/artifacts/"
                        f"{CURRENT_EXTERNAL_RUNTIME_VERSION}/{target_os}/{arch}/download"
                    ),
                )
            )
    return ExternalRuntimeArtifactManifestResponse(
        version=CURRENT_EXTERNAL_RUNTIME_VERSION,
        artifacts=artifacts,
    )


def render_install_sh(*, agent_id: str, base_url: str, target: str, code: str) -> str:
    return textwrap.dedent(
        f"""
        #!/usr/bin/env bash
        set -euo pipefail

        AGENT_ID="{agent_id}"
        TARGET_OS="{target}"
        INSTALL_CODE="{code}"
        CONTROL_PLANE="{base_url}"
        MANIFEST_URL="$CONTROL_PLANE/api/v1/external-runtime/artifacts/manifest"
        RUNTIME_HOME="${{LINX_EXTERNAL_RUNTIME_ROOT:-$HOME/.linx-external-runtime/$AGENT_ID}}"
        DOWNLOAD_DIR="$RUNTIME_HOME/download"
        EXTRACT_DIR="$DOWNLOAD_DIR/extracted"
        SCRIPT_PATH="$RUNTIME_HOME/bin/linx_external_runtime.py"
        CONFIG_PATH="$RUNTIME_HOME/config/runtime-config.json"
        STATE_DIR="$RUNTIME_HOME/config"

        if ! command -v python3 >/dev/null 2>&1; then
          echo "python3 is required to install LinX external runtime." >&2
          exit 1
        fi

        if ! command -v curl >/dev/null 2>&1; then
          echo "curl is required to install LinX external runtime." >&2
          exit 1
        fi

        ARCH="$(python3 - <<'PY'
        import platform
        machine = platform.machine().strip().lower()
        mapping = {{
            "x86_64": "amd64",
            "amd64": "amd64",
            "arm64": "arm64",
            "aarch64": "arm64",
        }}
        resolved = mapping.get(machine)
        if not resolved:
            raise SystemExit(f"Unsupported architecture: {{machine}}")
        print(resolved)
        PY
        )"

        mkdir -p "$DOWNLOAD_DIR" "$EXTRACT_DIR" "$(dirname "$SCRIPT_PATH")" "$STATE_DIR"
        chmod 700 "$RUNTIME_HOME" "$STATE_DIR"

        manifest_output="$(python3 - "$MANIFEST_URL" "$TARGET_OS" "$ARCH" <<'PY'
        import json
        import sys
        import urllib.request

        manifest_url, target_os, arch = sys.argv[1:4]
        with urllib.request.urlopen(manifest_url, timeout=30) as response:
            manifest = json.loads(response.read().decode("utf-8"))
        for record in manifest.get("artifacts", []):
            if record.get("os") == target_os and record.get("arch") == arch:
                print(record["version"])
                print(record["download_path"])
                print(record["sha256"])
                break
        else:
            raise SystemExit(f"Artifact not found for {{target_os}}/{{arch}}")
        PY
        )"
        VERSION="$(printf '%s\\n' "$manifest_output" | sed -n '1p')"
        DOWNLOAD_URL="$(printf '%s\\n' "$manifest_output" | sed -n '2p')"
        EXPECTED_SHA="$(printf '%s\\n' "$manifest_output" | sed -n '3p')"
        ARTIFACT_PATH="$DOWNLOAD_DIR/runtime.tar.gz"

        curl -fsSL "$DOWNLOAD_URL" -o "$ARTIFACT_PATH"

        python3 - "$ARTIFACT_PATH" "$EXPECTED_SHA" <<'PY'
        import hashlib
        import sys
        from pathlib import Path

        artifact_path, expected_sha = sys.argv[1:3]
        digest = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
        if digest != expected_sha:
            raise SystemExit("Downloaded artifact checksum mismatch")
        PY

        rm -rf "$EXTRACT_DIR"
        mkdir -p "$EXTRACT_DIR"
        tar -xzf "$ARTIFACT_PATH" -C "$EXTRACT_DIR"
        SCRIPT_SOURCE="$(find "$EXTRACT_DIR" -name 'linx_external_runtime.py' -type f | head -n 1)"
        if [ -z "$SCRIPT_SOURCE" ]; then
          echo "Runtime script was not found inside the downloaded artifact." >&2
          exit 1
        fi

        cp "$SCRIPT_SOURCE" "$SCRIPT_PATH"
        chmod 755 "$SCRIPT_PATH"

        HOST_NAME="$(hostname)"
        HOST_ARCH="$ARCH"
        HOST_FINGERPRINT="$(python3 - <<'PY'
        import hashlib
        import pathlib
        import platform
        import subprocess
        import socket

        def load_source() -> str:
            if pathlib.Path("/etc/machine-id").exists():
                return pathlib.Path("/etc/machine-id").read_text(encoding="utf-8").strip()
            if platform.system().lower() == "darwin":
                try:
                    result = subprocess.run(
                        ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except Exception:
                    result = None
                if result:
                    for line in result.stdout.splitlines():
                        if "IOPlatformUUID" in line:
                            return line.split("=", 1)[-1].replace('"', "").strip()
            return f"{{socket.gethostname()}}::{{platform.platform()}}"

        print(hashlib.sha256(load_source().encode("utf-8")).hexdigest())
        PY
        )"

        bootstrap_json="$(python3 - "$CONTROL_PLANE" "$AGENT_ID" "$INSTALL_CODE" "$HOST_NAME" "$TARGET_OS" "$HOST_ARCH" "$HOST_FINGERPRINT" "$VERSION" "$RUNTIME_HOME" <<'PY'
        import json
        import sys
        import urllib.request

        (
            control_plane,
            agent_id,
            install_code,
            host_name,
            host_os,
            host_arch,
            host_fingerprint,
            version,
            runtime_home,
        ) = sys.argv[1:10]
        payload = {{
            "agent_id": agent_id,
            "install_code": install_code,
            "host_name": host_name,
            "host_os": host_os,
            "host_arch": host_arch,
            "host_fingerprint": host_fingerprint,
            "current_version": version,
            "metadata": {{
                "installed_via": "install.sh",
                "runtime_home": runtime_home,
            }},
        }}
        request = urllib.request.Request(
            f"{{control_plane}}/api/v1/external-runtime/bootstrap",
            data=json.dumps(payload).encode("utf-8"),
            headers={{"Content-Type": "application/json"}},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            print(response.read().decode("utf-8"))
        PY
        )"

        python3 - "$CONFIG_PATH" "$bootstrap_json" "$CONTROL_PLANE" "$AGENT_ID" "$TARGET_OS" "$HOST_ARCH" "$HOST_NAME" "$HOST_FINGERPRINT" "$RUNTIME_HOME" "$VERSION" <<'PY'
        import json
        import sys
        from pathlib import Path

        (
            config_path,
            bootstrap_json,
            control_plane,
            agent_id,
            host_os,
            host_arch,
            host_name,
            host_fingerprint,
            runtime_home,
            version,
        ) = sys.argv[1:11]
        bootstrap = json.loads(bootstrap_json)
        config = {{
            "agent_id": agent_id,
            "control_plane": control_plane,
            "machine_token": bootstrap["machine_token"],
            "host_name": host_name,
            "host_os": host_os,
            "host_arch": host_arch,
            "host_fingerprint": host_fingerprint,
            "runtime_home": runtime_home,
            "runtime_version": version,
            "desired_version": bootstrap.get("desired_version"),
            "heartbeat_interval_seconds": bootstrap.get("heartbeat_interval_seconds", 20),
            "dispatch_poll_interval_seconds": bootstrap.get("dispatch_poll_interval_seconds", 25),
        }}
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        PY

        chmod 600 "$CONFIG_PATH"

        if [ "$TARGET_OS" = "linux" ]; then
          SERVICE_NAME="linx-external-runtime-$AGENT_ID.service"
          SERVICE_PATH="$HOME/.config/systemd/user/$SERVICE_NAME"
          mkdir -p "$(dirname "$SERVICE_PATH")"
          cat > "$SERVICE_PATH" <<EOF
        [Unit]
        Description=LinX External Runtime ($AGENT_ID)
        After=network-online.target

        [Service]
        Type=simple
        WorkingDirectory=$RUNTIME_HOME
        ExecStart=/usr/bin/env python3 $SCRIPT_PATH --config $CONFIG_PATH
        Restart=on-failure
        RestartSec=5
        Environment=PYTHONUNBUFFERED=1

        [Install]
        WantedBy=default.target
        EOF
          systemctl --user daemon-reload
          systemctl --user enable --now "$SERVICE_NAME"
        else
          PLIST_LABEL="com.linx.external-runtime.$AGENT_ID"
          PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
          mkdir -p "$(dirname "$PLIST_PATH")"
          cat > "$PLIST_PATH" <<EOF
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
          <dict>
            <key>Label</key>
            <string>$PLIST_LABEL</string>
            <key>ProgramArguments</key>
            <array>
              <string>/usr/bin/env</string>
              <string>python3</string>
              <string>$SCRIPT_PATH</string>
              <string>--config</string>
              <string>$CONFIG_PATH</string>
            </array>
            <key>WorkingDirectory</key>
            <string>$RUNTIME_HOME</string>
            <key>RunAtLoad</key>
            <true/>
            <key>KeepAlive</key>
            <dict>
              <key>SuccessfulExit</key>
              <false/>
            </dict>
            <key>StandardOutPath</key>
            <string>$RUNTIME_HOME/runtime.stdout.log</string>
            <key>StandardErrorPath</key>
            <string>$RUNTIME_HOME/runtime.stderr.log</string>
          </dict>
        </plist>
        EOF
          launchctl unload "$PLIST_PATH" 2>/dev/null || true
          launchctl load "$PLIST_PATH"
          launchctl kickstart -k "gui/$(id -u)/$PLIST_LABEL"
        fi

        echo "LinX external runtime installed for agent $AGENT_ID"
        echo "Config: $CONFIG_PATH"
        echo "Runtime home: $RUNTIME_HOME"
        """
    ).strip() + "\n"


def render_update_sh(*, agent_id: str, base_url: str, target: str) -> str:
    return textwrap.dedent(
        f"""
        #!/usr/bin/env bash
        set -euo pipefail

        AGENT_ID="{agent_id}"
        TARGET_OS="{target}"
        CONTROL_PLANE="{base_url}"
        MANIFEST_URL="$CONTROL_PLANE/api/v1/external-runtime/artifacts/manifest"
        RUNTIME_HOME="${{LINX_EXTERNAL_RUNTIME_ROOT:-$HOME/.linx-external-runtime/$AGENT_ID}}"
        DOWNLOAD_DIR="$RUNTIME_HOME/download"
        EXTRACT_DIR="$DOWNLOAD_DIR/extracted"
        SCRIPT_PATH="$RUNTIME_HOME/bin/linx_external_runtime.py"
        CONFIG_PATH="$RUNTIME_HOME/config/runtime-config.json"

        if [ ! -f "$CONFIG_PATH" ]; then
          echo "Runtime config does not exist at $CONFIG_PATH" >&2
          exit 1
        fi

        if ! command -v python3 >/dev/null 2>&1; then
          echo "python3 is required to update LinX external runtime." >&2
          exit 1
        fi

        if ! command -v curl >/dev/null 2>&1; then
          echo "curl is required to update LinX external runtime." >&2
          exit 1
        fi

        ARCH="$(python3 - "$CONFIG_PATH" <<'PY'
        import json
        import sys
        from pathlib import Path

        config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        print(config.get("host_arch") or "amd64")
        PY
        )"

        mkdir -p "$DOWNLOAD_DIR" "$EXTRACT_DIR"
        manifest_output="$(python3 - "$MANIFEST_URL" "$TARGET_OS" "$ARCH" <<'PY'
        import json
        import sys
        import urllib.request

        manifest_url, target_os, arch = sys.argv[1:4]
        with urllib.request.urlopen(manifest_url, timeout=30) as response:
            manifest = json.loads(response.read().decode("utf-8"))
        for record in manifest.get("artifacts", []):
            if record.get("os") == target_os and record.get("arch") == arch:
                print(record["version"])
                print(record["download_path"])
                print(record["sha256"])
                break
        else:
            raise SystemExit(f"Artifact not found for {{target_os}}/{{arch}}")
        PY
        )"
        VERSION="$(printf '%s\\n' "$manifest_output" | sed -n '1p')"
        DOWNLOAD_URL="$(printf '%s\\n' "$manifest_output" | sed -n '2p')"
        EXPECTED_SHA="$(printf '%s\\n' "$manifest_output" | sed -n '3p')"
        ARTIFACT_PATH="$DOWNLOAD_DIR/runtime.tar.gz"

        curl -fsSL "$DOWNLOAD_URL" -o "$ARTIFACT_PATH"
        python3 - "$ARTIFACT_PATH" "$EXPECTED_SHA" <<'PY'
        import hashlib
        import sys
        from pathlib import Path

        artifact_path, expected_sha = sys.argv[1:3]
        digest = hashlib.sha256(Path(artifact_path).read_bytes()).hexdigest()
        if digest != expected_sha:
            raise SystemExit("Downloaded artifact checksum mismatch")
        PY

        rm -rf "$EXTRACT_DIR"
        mkdir -p "$EXTRACT_DIR"
        tar -xzf "$ARTIFACT_PATH" -C "$EXTRACT_DIR"
        SCRIPT_SOURCE="$(find "$EXTRACT_DIR" -name 'linx_external_runtime.py' -type f | head -n 1)"
        if [ -z "$SCRIPT_SOURCE" ]; then
          echo "Runtime script was not found inside the downloaded artifact." >&2
          exit 1
        fi

        cp "$SCRIPT_SOURCE" "$SCRIPT_PATH"
        chmod 755 "$SCRIPT_PATH"
        python3 - "$CONFIG_PATH" "$VERSION" "$RUNTIME_HOME" <<'PY'
        import json
        import sys
        from pathlib import Path

        config_path, version, runtime_home = sys.argv[1:4]
        path = Path(config_path)
        config = json.loads(path.read_text(encoding="utf-8"))
        config["runtime_version"] = version
        config["runtime_home"] = runtime_home
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        PY

        if [ "$TARGET_OS" = "linux" ]; then
          SERVICE_NAME="linx-external-runtime-$AGENT_ID.service"
          systemctl --user restart "$SERVICE_NAME"
        else
          PLIST_LABEL="com.linx.external-runtime.$AGENT_ID"
          launchctl kickstart -k "gui/$(id -u)/$PLIST_LABEL"
        fi

        echo "LinX external runtime updated for agent $AGENT_ID"
        """
    ).strip() + "\n"


def render_uninstall_sh(*, agent_id: str, base_url: str, target: str) -> str:
    return textwrap.dedent(
        f"""
        #!/usr/bin/env bash
        set -euo pipefail

        AGENT_ID="{agent_id}"
        TARGET_OS="{target}"
        CONTROL_PLANE="{base_url}"
        RUNTIME_HOME="${{LINX_EXTERNAL_RUNTIME_ROOT:-$HOME/.linx-external-runtime/$AGENT_ID}}"
        CONFIG_PATH="$RUNTIME_HOME/config/runtime-config.json"

        if [ -f "$CONFIG_PATH" ] && command -v python3 >/dev/null 2>&1; then
          python3 - "$CONFIG_PATH" <<'PY' || true
        import json
        import sys
        import urllib.request
        from pathlib import Path

        config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        machine_token = str(config.get("machine_token") or "").strip()
        control_plane = str(config.get("control_plane") or "").rstrip("/")
        if machine_token and control_plane:
            request = urllib.request.Request(
                f"{{control_plane}}/api/v1/external-runtime/self-unregister",
                data=b"",
                headers={{
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {{machine_token}}",
                }},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=20):
                    pass
            except Exception:
                pass
        PY
        fi

        if [ "$TARGET_OS" = "linux" ]; then
          SERVICE_NAME="linx-external-runtime-$AGENT_ID.service"
          systemctl --user disable --now "$SERVICE_NAME" 2>/dev/null || true
          rm -f "$HOME/.config/systemd/user/$SERVICE_NAME"
          systemctl --user daemon-reload 2>/dev/null || true
        elif [ "$TARGET_OS" = "darwin" ]; then
          PLIST_LABEL="com.linx.external-runtime.$AGENT_ID"
          PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
          launchctl unload "$PLIST_PATH" 2>/dev/null || true
          rm -f "$PLIST_PATH"
        fi

        rm -rf "$RUNTIME_HOME"
        echo "LinX external runtime uninstalled for agent $AGENT_ID"
        """
    ).strip() + "\n"


def render_install_ps1(*, agent_id: str, base_url: str, target: str, code: str) -> str:
    return textwrap.dedent(
        f"""
        $ErrorActionPreference = "Stop"
        $AgentId = "{agent_id}"
        $TargetOs = "{target}"
        $InstallCode = "{code}"
        $ControlPlane = "{base_url}"
        $ManifestUrl = "$ControlPlane/api/v1/external-runtime/artifacts/manifest"
        $RuntimeHome = Join-Path $env:USERPROFILE ".linx-external-runtime\\$AgentId"
        $DownloadDir = Join-Path $RuntimeHome "download"
        $ExtractDir = Join-Path $DownloadDir "extracted"
        $ScriptPath = Join-Path $RuntimeHome "bin\\linx_external_runtime.py"
        $ConfigPath = Join-Path $RuntimeHome "config\\runtime-config.json"

        function Get-HostArch {{
          switch ($env:PROCESSOR_ARCHITECTURE.ToLowerInvariant()) {{
            "amd64" {{ return "amd64" }}
            "x86_64" {{ return "amd64" }}
            "arm64" {{ return "arm64" }}
            default {{ throw "Unsupported architecture: $env:PROCESSOR_ARCHITECTURE" }}
          }}
        }}

        function Get-HostFingerprint {{
          $machineGuid = (Get-ItemProperty "HKLM:\\SOFTWARE\\Microsoft\\Cryptography").MachineGuid
          $bytes = [Text.Encoding]::UTF8.GetBytes($machineGuid)
          $sha = [System.Security.Cryptography.SHA256]::Create()
          $hash = $sha.ComputeHash($bytes)
          return -join ($hash | ForEach-Object {{ $_.ToString("x2") }})
        }}

        function Get-PythonExecutable {{
          $py = Get-Command py -ErrorAction SilentlyContinue
          if ($py) {{
            return @{{ Path = $py.Source; Arguments = "-3" }}
          }}
          $python = Get-Command python -ErrorAction SilentlyContinue
          if ($python) {{
            return @{{ Path = $python.Source; Arguments = "" }}
          }}
          throw "Python 3 is required to install LinX external runtime."
        }}

        $Arch = Get-HostArch
        New-Item -ItemType Directory -Force -Path $DownloadDir, $ExtractDir, (Split-Path $ScriptPath), (Split-Path $ConfigPath) | Out-Null
        $Manifest = Invoke-RestMethod -Uri $ManifestUrl
        $Artifact = $Manifest.artifacts | Where-Object {{ $_.os -eq $TargetOs -and $_.arch -eq $Arch }} | Select-Object -First 1
        if (-not $Artifact) {{
          throw "Artifact not found for $TargetOs/$Arch"
        }}

        $ArtifactPath = Join-Path $DownloadDir "runtime.zip"
        Invoke-WebRequest -Uri $Artifact.download_path -OutFile $ArtifactPath | Out-Null
        if (Test-Path $ExtractDir) {{
          Remove-Item -Recurse -Force $ExtractDir
        }}
        New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
        Expand-Archive -Force -Path $ArtifactPath -DestinationPath $ExtractDir
        $SourceScript = Get-ChildItem -Path $ExtractDir -Filter "linx_external_runtime.py" -Recurse | Select-Object -First 1
        if (-not $SourceScript) {{
          throw "Runtime script was not found inside the downloaded artifact."
        }}
        Copy-Item -Force $SourceScript.FullName $ScriptPath

        $HostName = $env:COMPUTERNAME
        $HostFingerprint = Get-HostFingerprint
        $BootstrapPayload = @{{
          agent_id = $AgentId
          install_code = $InstallCode
          host_name = $HostName
          host_os = $TargetOs
          host_arch = $Arch
          host_fingerprint = $HostFingerprint
          current_version = $Manifest.version
          metadata = @{{
            installed_via = "install.ps1"
            runtime_home = $RuntimeHome
          }}
        }} | ConvertTo-Json -Depth 6
        $Bootstrap = Invoke-RestMethod -Uri "$ControlPlane/api/v1/external-runtime/bootstrap" -Method Post -ContentType "application/json" -Body $BootstrapPayload
        $Config = @{{
          agent_id = $AgentId
          control_plane = $ControlPlane
          machine_token = $Bootstrap.machine_token
          host_name = $HostName
          host_os = $TargetOs
          host_arch = $Arch
          host_fingerprint = $HostFingerprint
          runtime_home = $RuntimeHome
          runtime_version = $Manifest.version
          desired_version = $Bootstrap.desired_version
          heartbeat_interval_seconds = $Bootstrap.heartbeat_interval_seconds
          dispatch_poll_interval_seconds = $Bootstrap.dispatch_poll_interval_seconds
        }} | ConvertTo-Json -Depth 6
        Set-Content -Path $ConfigPath -Value $Config -Encoding UTF8

        $Python = Get-PythonExecutable
        $TaskName = "LinXExternalRuntime-$AgentId"
        $PythonArgs = if ($Python.Arguments) {{
          "$($Python.Arguments) `"$ScriptPath`" --config `"$ConfigPath`""
        }} else {{
          "`"$ScriptPath`" --config `"$ConfigPath`""
        }}
        $Action = New-ScheduledTaskAction -Execute $Python.Path -Argument $PythonArgs
        $Trigger = New-ScheduledTaskTrigger -AtLogOn
        $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "LinX External Runtime ($AgentId)" -User $env:USERNAME -RunLevel Limited | Out-Null
        Start-ScheduledTask -TaskName $TaskName

        Write-Host "LinX external runtime installed for agent $AgentId"
        Write-Host "Config: $ConfigPath"
        """
    ).strip() + "\n"


def render_update_ps1(*, agent_id: str, base_url: str, target: str) -> str:
    return textwrap.dedent(
        f"""
        $ErrorActionPreference = "Stop"
        $AgentId = "{agent_id}"
        $TargetOs = "{target}"
        $ControlPlane = "{base_url}"
        $ManifestUrl = "$ControlPlane/api/v1/external-runtime/artifacts/manifest"
        $RuntimeHome = Join-Path $env:USERPROFILE ".linx-external-runtime\\$AgentId"
        $DownloadDir = Join-Path $RuntimeHome "download"
        $ExtractDir = Join-Path $DownloadDir "extracted"
        $ScriptPath = Join-Path $RuntimeHome "bin\\linx_external_runtime.py"
        $ConfigPath = Join-Path $RuntimeHome "config\\runtime-config.json"
        if (-not (Test-Path $ConfigPath)) {{
          throw "Runtime config does not exist at $ConfigPath"
        }}

        function Get-HostArch {{
          $Config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
          return $Config.host_arch
        }}

        $Arch = Get-HostArch
        New-Item -ItemType Directory -Force -Path $DownloadDir, $ExtractDir | Out-Null
        $Manifest = Invoke-RestMethod -Uri $ManifestUrl
        $Artifact = $Manifest.artifacts | Where-Object {{ $_.os -eq $TargetOs -and $_.arch -eq $Arch }} | Select-Object -First 1
        if (-not $Artifact) {{
          throw "Artifact not found for $TargetOs/$Arch"
        }}
        $ArtifactPath = Join-Path $DownloadDir "runtime.zip"
        Invoke-WebRequest -Uri $Artifact.download_path -OutFile $ArtifactPath | Out-Null
        if (Test-Path $ExtractDir) {{
          Remove-Item -Recurse -Force $ExtractDir
        }}
        New-Item -ItemType Directory -Force -Path $ExtractDir | Out-Null
        Expand-Archive -Force -Path $ArtifactPath -DestinationPath $ExtractDir
        $SourceScript = Get-ChildItem -Path $ExtractDir -Filter "linx_external_runtime.py" -Recurse | Select-Object -First 1
        if (-not $SourceScript) {{
          throw "Runtime script was not found inside the downloaded artifact."
        }}
        Copy-Item -Force $SourceScript.FullName $ScriptPath
        $Config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        $Config.runtime_version = $Manifest.version
        $Config.runtime_home = $RuntimeHome
        $Config | ConvertTo-Json -Depth 6 | Set-Content -Path $ConfigPath -Encoding UTF8

        $TaskName = "LinXExternalRuntime-$AgentId"
        Start-ScheduledTask -TaskName $TaskName
        Write-Host "LinX external runtime updated for agent $AgentId"
        """
    ).strip() + "\n"


def render_uninstall_ps1(*, agent_id: str, base_url: str, target: str) -> str:
    return textwrap.dedent(
        f"""
        $ErrorActionPreference = "Stop"
        $AgentId = "{agent_id}"
        $TargetOs = "{target}"
        $ControlPlane = "{base_url}"
        $RuntimeHome = Join-Path $env:USERPROFILE ".linx-external-runtime\\$AgentId"
        $ConfigPath = Join-Path $RuntimeHome "config\\runtime-config.json"

        if (Test-Path $ConfigPath) {{
          try {{
            $Config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
            if ($Config.machine_token -and $Config.control_plane) {{
              Invoke-RestMethod `
                -Uri "$($Config.control_plane)/api/v1/external-runtime/self-unregister" `
                -Method Post `
                -Headers @{{ Authorization = "Bearer $($Config.machine_token)" }} `
                -ContentType "application/json" `
                -Body "{{}}" | Out-Null
            }}
          }} catch {{
          }}
        }}

        $TaskName = "LinXExternalRuntime-$AgentId"
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
        if (Test-Path $RuntimeHome) {{
          Remove-Item -Recurse -Force $RuntimeHome
        }}

        Write-Host "LinX external runtime uninstalled for agent $AgentId"
        """
    ).strip() + "\n"
