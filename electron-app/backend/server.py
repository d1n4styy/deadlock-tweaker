import sys
import os
import re
import json
import ctypes
import ctypes.wintypes
import winreg
import urllib.request
import urllib.error
import threading
from pathlib import Path
from datetime import datetime

from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow Electron renderer (file:// origin)

APP_VERSION = "1.1.30"
GITHUB_REPO = "d1n4styy/deadlock-tweaker"
UPDATE_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

CONFIG_PATH = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Deadlock\game\citadel\cfg\autoexec.cfg")
_CFG_RELATIVE = Path("steamapps/common/Deadlock/game/citadel/cfg/autoexec.cfg")
PROFILES_PATH = Path(__file__).resolve().parent.parent / "profiles.json"

_custom_cfg_path: Path | None = None

# ──────────────────────────────────────────────────────────────────────────────
# Steam / config discovery
# ──────────────────────────────────────────────────────────────────────────────
def _steam_paths_from_registry() -> list[Path]:
    paths = []
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Valve\Steam"),
    ]
    for hive, subkey in keys:
        try:
            with winreg.OpenKey(hive, subkey) as k:
                val, _ = winreg.QueryValueEx(k, "InstallPath")
                p = Path(val)
                if p.exists() and p not in paths:
                    paths.append(p)
        except OSError:
            pass
    return paths


def _steam_library_folders(steam_root: Path) -> list[Path]:
    libs = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if not vdf.exists():
        return libs
    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            p = Path(m.group(1))
            if p.exists() and p not in libs:
                libs.append(p)
    except Exception:
        pass
    return libs


def find_autoexec() -> Path | None:
    global _custom_cfg_path
    if _custom_cfg_path and _custom_cfg_path.exists():
        return _custom_cfg_path
    if CONFIG_PATH.exists():
        return CONFIG_PATH
    for steam_root in _steam_paths_from_registry():
        for lib in _steam_library_folders(steam_root):
            candidate = lib / _CFG_RELATIVE
            if candidate.exists():
                return candidate
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Game process detection
# ──────────────────────────────────────────────────────────────────────────────
def check_game_running() -> bool:
    try:
        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32(ctypes.Structure):
            _fields_ = [
                ("dwSize",              ctypes.wintypes.DWORD),
                ("cntUsage",            ctypes.wintypes.DWORD),
                ("th32ProcessID",       ctypes.wintypes.DWORD),
                ("th32DefaultHeapID",   ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID",        ctypes.wintypes.DWORD),
                ("cntThreads",          ctypes.wintypes.DWORD),
                ("th32ParentProcessID", ctypes.wintypes.DWORD),
                ("pcPriClassBase",      ctypes.c_long),
                ("dwFlags",             ctypes.wintypes.DWORD),
                ("szExeFile",           ctypes.c_char * 260),
            ]

        kernel32 = ctypes.windll.kernel32
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        _INVALID = ctypes.wintypes.HANDLE(-1).value
        found = False
        if snapshot != _INVALID:
            try:
                entry = PROCESSENTRY32()
                entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
                if kernel32.Process32First(snapshot, ctypes.byref(entry)):
                    while True:
                        name = entry.szExeFile.lower()
                        if name in (b"deadlock.exe", b"project8.exe"):
                            found = True
                            break
                        if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                            break
            finally:
                kernel32.CloseHandle(snapshot)
        return found
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────────────────────
# API routes
# ──────────────────────────────────────────────────────────────────────────────
@app.route('/api/version')
def api_version():
    return jsonify({'version': APP_VERSION})


@app.route('/api/status')
def api_status():
    cfg = find_autoexec()
    return jsonify({
        'game_running':  check_game_running(),
        'config_found':  cfg is not None,
        'config_path':   str(cfg) if cfg else None,
    })


@app.route('/api/config/scan')
def api_config_scan():
    cfg = find_autoexec()
    return jsonify({'found': cfg is not None, 'path': str(cfg) if cfg else None})


@app.route('/api/config/set', methods=['POST'])
def api_config_set():
    global _custom_cfg_path
    data = request.get_json(force=True)
    p = Path(data.get('path', ''))
    if p.exists():
        _custom_cfg_path = p
        return jsonify({'ok': True, 'path': str(p)})
    return jsonify({'ok': False, 'error': 'File not found'}), 400


@app.route('/api/config/create', methods=['POST'])
def api_config_create():
    global _custom_cfg_path
    steam_roots = _steam_paths_from_registry()
    target = (steam_roots[0] / _CFG_RELATIVE) if steam_roots else CONFIG_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("// Deadlock autoexec.cfg\n", encoding="utf-8")
        _custom_cfg_path = target
        return jsonify({'ok': True, 'path': str(target)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/profiles')
def api_profiles_list():
    try:
        data = json.loads(PROFILES_PATH.read_text(encoding='utf-8')) if PROFILES_PATH.exists() else {}
        return jsonify({'profiles': list(data.keys())})
    except Exception:
        return jsonify({'profiles': []})


@app.route('/api/profiles/<name>', methods=['GET'])
def api_profile_get(name):
    try:
        data = json.loads(PROFILES_PATH.read_text(encoding='utf-8')) if PROFILES_PATH.exists() else {}
        if name in data:
            return jsonify({'ok': True, 'settings': data[name]})
        return jsonify({'ok': False, 'error': 'Not found'}), 404
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/profiles', methods=['POST'])
def api_profile_save():
    try:
        payload = request.get_json(force=True)
        name = payload.get('name', '').strip()
        settings = payload.get('settings', {})
        if not name or name.lower() == 'default profile':
            return jsonify({'ok': False, 'error': 'Invalid name'}), 400
        data = json.loads(PROFILES_PATH.read_text(encoding='utf-8')) if PROFILES_PATH.exists() else {}
        data[name] = settings
        PROFILES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/profiles/<name>', methods=['DELETE'])
def api_profile_delete(name):
    try:
        data = json.loads(PROFILES_PATH.read_text(encoding='utf-8')) if PROFILES_PATH.exists() else {}
        data.pop(name, None)
        PROFILES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/update/check')
def api_update_check():
    try:
        headers = {
            'User-Agent': f'DeadlockTweaker/{APP_VERSION}',
            'Accept': 'application/vnd.github+json',
        }
        req = urllib.request.Request(UPDATE_API_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            release = json.loads(resp.read().decode())
        version = str(release.get('tag_name', '')).strip().lstrip('vV')
        # Extract .exe download URL from assets
        download_url = ''
        for asset in release.get('assets', []):
            name = asset.get('name', '').lower()
            if name.endswith('.exe'):
                download_url = asset.get('browser_download_url', '')
                break
        return jsonify({
            'ok': True,
            'version':      version,
            'current':      APP_VERSION,
            'notes':        (release.get('body') or '').strip(),
            'html_url':     release.get('html_url', ''),
            'download_url': download_url,
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=7654, debug=False, use_reloader=False)
