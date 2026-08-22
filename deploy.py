#!/usr/bin/env python3
"""
deploy.py — 本地生成数据，同步到服务器，启动/重启 uvicorn
用法：
  python3 deploy.py              # 抓数据 + 同步 + 重启
  python3 deploy.py --no-fetch   # 只同步代码，不重新抓数据
  python3 deploy.py --no-restart # 只同步，不重启服务
"""

import os, sys, time, subprocess, argparse, paramiko
from pathlib import Path

# ── 配置 ────────────────────────────────────────────────────────────────
HOST           = os.environ.get("COFFEE_REMOTE_HOST", "210.45.78.109")
PORT           = int(os.environ.get("COFFEE_REMOTE_PORT", "22"))
USER           = os.environ.get("COFFEE_REMOTE_USER", "zbsu")
PASSWORD       = os.environ.get("COFFEE_REMOTE_PASSWORD", "")
BENTY_PASSWORD = os.environ.get("BENTY_PASSWORD", "")

LOCAL_DIR      = Path("/Users/suzhenbo/Mylibrary/Projects/lib_python_external/arxiv_ustc")
REMOTE_DIR     = "/home/zbsu/ustc_astro_coffee"
CONDA_INIT     = "source /home/zbsu/miniconda3/etc/profile.d/conda.sh && conda activate fastapi"
UVICORN        = "/home/zbsu/miniconda3/envs/fastapi/bin/uvicorn"
PORT_APP       = 10027
SCREEN_SESSION = "coffee"

missing = [
    name for name, value in {
        "COFFEE_REMOTE_PASSWORD": PASSWORD,
        "BENTY_PASSWORD": BENTY_PASSWORD,
    }.items()
    if not value
]
if missing:
    print("缺少环境变量：" + ", ".join(missing), file=sys.stderr)
    print("请先在本机 shell 或 GitHub Secrets 中配置后再运行 deploy.py。", file=sys.stderr)
    sys.exit(2)

# ── 参数 ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--no-fetch",   action="store_true")
parser.add_argument("--no-restart", action="store_true")
args = parser.parse_args()


# ── Step 1: 本地抓取数据 ──────────────────────────────────────────────────
if not args.no_fetch:
    print("=" * 50)
    print("Step 1: 本地抓取 Benty-Fields 数据...")
    print("=" * 50)
    env = os.environ.copy()
    env["BENTY_PASSWORD"] = BENTY_PASSWORD
    result = subprocess.run(
        [sys.executable, str(LOCAL_DIR / "fetch_benty.py"),
         "--output-dir", str(LOCAL_DIR / "data")],
        env=env
    )
    if result.returncode != 0:
        print("警告：fetch 失败，继续同步已有数据...")
else:
    print("跳过数据抓取")


# ── Step 2: 连接服务器 ────────────────────────────────────────────────────
print("\n" + "=" * 50)
print("Step 2: 连接服务器并同步文件...")
print("=" * 50)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, PORT, USER, PASSWORD, look_for_keys=False)
sftp = client.open_sftp()
print(f"连接 {USER}@{HOST} 成功 ✓")


def remote_mkdir(path):
    try:
        sftp.stat(path)
    except FileNotFoundError:
        sftp.mkdir(path)
        print(f"  创建目录：{path}")


def sync_dir(local_dir: Path, remote_dir: str, exclude=None):
    exclude = exclude or set()
    remote_mkdir(remote_dir)
    for item in sorted(local_dir.iterdir()):
        if item.name in exclude or item.name.startswith("."):
            continue
        remote_path = f"{remote_dir}/{item.name}"
        if item.is_dir():
            sync_dir(item, remote_path, exclude)
        else:
            print(f"  上传：{item.relative_to(LOCAL_DIR)}")
            sftp.put(str(item), remote_path)


def run(cmd):
    _, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode().strip(), stderr.read().decode().strip()


def run_sudo(cmd):
    stdin, stdout, stderr = client.exec_command(f"sudo -S bash -c '{cmd}'")
    stdin.write(PASSWORD + "\n")
    stdin.flush()
    return stdout.read().decode().strip(), stderr.read().decode().strip()


# 同步代码（排除 data/）
print("\n同步代码文件...")
sync_dir(LOCAL_DIR, REMOTE_DIR, exclude={"data", "__pycache__", ".DS_Store", "thoughts", "coffee_votes"})

# 同步 data/
data_dir = LOCAL_DIR / "data"
if data_dir.exists():
    print("\n同步 data/ 目录...")
    sync_dir(data_dir, f"{REMOTE_DIR}/data", exclude={"thoughts", "coffee_votes"})
else:
    remote_mkdir(f"{REMOTE_DIR}/data")

sftp.close()
print("\n文件同步完成 ✓")


# ── Step 2.5: 开放防火墙端口 ─────────────────────────────────────────────
print(f"\n开放端口 {PORT_APP}...")
_, err = run_sudo(f"iptables -C INPUT -p tcp --dport {PORT_APP} -j ACCEPT")
if err:
    run_sudo(f"iptables -I INPUT -p tcp --dport {PORT_APP} -j ACCEPT")
    run_sudo("iptables-save > /etc/iptables/rules.v4")
    print(f"  端口 {PORT_APP} 已开放 ✓")
else:
    print(f"  端口 {PORT_APP} 已存在，跳过")


# ── Step 3: 重启服务（用 screen）────────────────────────────────────────────
if not args.no_restart:
    print("\n" + "=" * 50)
    print("Step 3: 重启 uvicorn (screen)...")
    print("=" * 50)

    # 杀掉旧 screen session
    out, _ = run(f"screen -ls | grep '{SCREEN_SESSION}'")
    if out:
        print(f"  停止旧的 {SCREEN_SESSION} session...")
        run(f"screen -S {SCREEN_SESSION} -X quit")
        time.sleep(1)

    # 启动新 screen session，-dm 后台运行，-S 命名
    inner_cmd = f"{CONDA_INIT} && cd {REMOTE_DIR} && BENTY_PASSWORD='{BENTY_PASSWORD}' {UVICORN} app:app --host 0.0.0.0 --port {PORT_APP}"
    run(f"{CONDA_INIT} && screen -dmS {SCREEN_SESSION} bash -c '{inner_cmd}'")
    time.sleep(2)

    out, _ = run(f"screen -ls | grep '{SCREEN_SESSION}'")
    if out:
        print(f"  uvicorn 运行中 (screen: {SCREEN_SESSION}) ✓")
    else:
        print("  ⚠️  screen session 未检测到，请手动登录检查")

client.close()
print(f"\n完成！访问地址：http://{HOST}:{PORT_APP}")
