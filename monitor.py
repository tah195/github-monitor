#!/usr/bin/env python3
"""
GitHub 사용자 활동 모니터
- Windows 데스크탑 팝업 알림
- Gmail 이메일 알림
- Mattermost 알림
"""

import requests
import json
import os
import smtplib
import time
import sys
import subprocess
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from html import escape as html_escape
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Windows 터미널 UTF-8 출력 설정
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ==================== 기본 설정 ====================
GITHUB_USER = "tellang"

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / ".monitor_state.json"
CONFIG_FILE = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "github_token": "",        # GitHub PAT (선택, 없으면 시간당 60회 제한)
    "gmail_sender": "",        # 보내는 Gmail 주소
    "gmail_app_password": "",  # Gmail 앱 비밀번호 (16자리)
    "gmail_recipient": "",     # 받는 이메일 주소
    "mattermost_webhook": "",  # Mattermost Incoming Webhook URL
    "check_interval": 300,     # 확인 주기 (초)
    "notify_types": [
        "PushEvent",
        "PullRequestEvent",
        "ReleaseEvent",
    ],
}


# ==================== 설정 / 상태 ====================
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[{now()}] config.json 읽기 실패 ({e}) — 기본값으로 실행합니다.")

    # 환경변수로 오버라이드 (GitHub Actions용)
    env_map = {
        "MONITOR_GITHUB_TOKEN": "github_token",
        "GMAIL_SENDER":         "gmail_sender",
        "GMAIL_APP_PASSWORD":   "gmail_app_password",
        "GMAIL_RECIPIENT":      "gmail_recipient",
        "MATTERMOST_WEBHOOK":   "mattermost_webhook",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key, "")
        if val:
            cfg[cfg_key] = val

    return cfg


def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print(f"[{now()}] 상태 파일 손상 — 초기화합니다.")
    return {"last_event_id": None}


def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except OSError as e:
        print(f"[{now()}] 상태 저장 실패 ({e}) — 다음 실행에서 중복 알림이 올 수 있습니다.")


def now():
    return datetime.now().strftime("%H:%M:%S")


def to_kst(dt_str):
    """GitHub API UTC 문자열 → KST (UTC+9) 포맷 문자열로 변환"""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        kst = dt.astimezone(timezone(timedelta(hours=9)))
        return kst.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return dt_str[:16].replace("T", " ")


# ==================== 이벤트 필터 ====================
def _should_notify(event, notify_types):
    etype = event.get("type")
    if etype not in notify_types:
        return False
    # PullRequestEvent는 merged된 경우만 알림
    if etype == "PullRequestEvent":
        payload = event.get("payload", {})
        pr = payload.get("pull_request", {})
        return payload.get("action") == "closed" and pr.get("merged") is True
    return True


# ==================== GitHub API ====================
def get_github_events(cfg):
    url = f"https://api.github.com/users/{GITHUB_USER}/events/public"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "GitHub-Activity-Monitor/1.0",
    }
    if cfg.get("github_token"):
        headers["Authorization"] = f"token {cfg['github_token']}"

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                print(f"[{now()}] GitHub API 응답 파싱 실패 (JSON 아님).")
                return []
        elif resp.status_code == 401:
            print(f"[{now()}] GitHub API 인증 실패. MONITOR_GITHUB_TOKEN이 만료되었거나 잘못되었습니다.")
        elif resp.status_code == 403:
            print(f"[{now()}] GitHub API rate limit 초과. MONITOR_GITHUB_TOKEN을 설정하세요.")
        else:
            print(f"[{now()}] GitHub API 오류: {resp.status_code}")
    except requests.RequestException as e:
        print(f"[{now()}] 네트워크 오류: {e}")
    return []


def format_event(event):
    etype = event.get("type", "Unknown")
    repo = event.get("repo", {}).get("name", "unknown/unknown")
    payload = event.get("payload", {})

    size = payload.get("size")
    distinct = payload.get("distinct_size")
    commit_count = size if size is not None else (distinct if distinct is not None else len(payload.get("commits", [])))
    push_label = f"커밋 푸시 ({commit_count}개)" if commit_count else "커밋 푸시"
    type_map = {
        "PushEvent":         ("📦", push_label),
        "CreateEvent":       ("✨", f"{payload.get('ref_type', '브랜치')} 생성"),
        "DeleteEvent":       ("🗑️", f"{payload.get('ref_type', '브랜치')} 삭제"),
        "PullRequestEvent":  ("🔀", "PR merged"),
        "IssuesEvent":       ("📋", f"이슈 {payload.get('action', '')}"),
        "IssueCommentEvent": ("💬", "이슈 댓글"),
        "ForkEvent":         ("🍴", "포크"),
        "WatchEvent":        ("⭐", "Star"),
        "ReleaseEvent":      ("🚀", f"릴리즈 {payload.get('action', '')}"),
        "PublicEvent":       ("🌐", "레포 공개 전환"),
        "MemberEvent":       ("👥", f"멤버 {payload.get('action', '')}"),
    }

    if etype in type_map:
        emoji, action = type_map[etype]
        return f"{emoji} {action}: {repo}"
    return f"📌 {etype}: {repo}"


def build_email_body(events_with_msg):
    lines = [
        f"GitHub 사용자 <b>{GITHUB_USER}</b> 의 새 활동이 감지되었습니다.<br><br>",
    ]
    for ev, msg in events_with_msg:
        repo_name = ev.get("repo", {}).get("name", "")
        repo_url = f"https://github.com/{repo_name}"
        created = to_kst(ev.get("created_at", ""))
        lines.append(
            f"<li>{msg} &nbsp; "
            f'<a href="{repo_url}">{repo_name}</a> '
            f"<span style='color:#888'>({created} KST)</span>"
        )
        # PushEvent: 커밋 메시지 목록 추가
        if ev.get("type") == "PushEvent":
            commits = ev.get("payload", {}).get("commits", [])
            if commits:
                lines.append("<ul>")
                for commit in commits[:5]:
                    sha = commit.get("sha", "")[:7]
                    message = html_escape(commit.get("message", "").split("\n")[0])
                    commit_url = f"https://github.com/{repo_name}/commit/{commit.get('sha', '')}"
                    lines.append(
                        f'<li><code><a href="{commit_url}">{sha}</a></code> {message}</li>'
                    )
                lines.append("</ul>")
        lines.append("</li>")
    lines.append(
        f'<br><a href="https://github.com/{GITHUB_USER}">👤 {GITHUB_USER} 프로필 보기</a>'
    )
    return "<ul>" + "\n".join(lines) + "</ul>"


# ==================== Windows 데스크탑 알림 ====================
def notify_windows(title, message):
    try:
        # PowerShell 특수문자 제거: $, `, 개행 등
        def ps_safe(s):
            return s.replace('"', "'").replace('`', "'").replace('$', '').replace('\n', ' ').replace('\r', '')
        safe_title = ps_safe(title)
        safe_msg = ps_safe(message)

        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$n = New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon = [System.Drawing.SystemIcons]::Information; "
            "$n.Visible = $true; "
            f'$n.ShowBalloonTip(8000, "{safe_title}", "{safe_msg}", '
            "[System.Windows.Forms.ToolTipIcon]::Info); "
            "Start-Sleep -Milliseconds 9000; "
            "$n.Dispose()"
        )
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps],
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(f"[{now()}] 🔔 팝업: {title} | {message}")
    except Exception as e:
        print(f"[{now()}] Windows 알림 오류: {e}")


# ==================== Gmail 알림 ====================
def notify_gmail(subject, html_body, cfg):
    sender = cfg.get("gmail_sender", "")
    password = cfg.get("gmail_app_password", "")
    recipient = cfg.get("gmail_recipient", "")

    if not sender or not password or not recipient:
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.sendmail(sender, recipient, msg.as_string())

        print(f"[{now()}] 📧 이메일 전송 완료 → {recipient}")
    except smtplib.SMTPAuthenticationError:
        print(f"[{now()}] Gmail 인증 실패. gmail_app_password를 확인하세요.")
    except Exception as e:
        print(f"[{now()}] Gmail 오류: {e}")


# ==================== Mattermost 알림 ====================
def notify_mattermost(events_with_msg, cfg):
    webhook_url = cfg.get("mattermost_webhook", "")
    if not webhook_url:
        return

    lines = [f"#### :github: GitHub 새 활동 감지 — [{GITHUB_USER}](https://github.com/{GITHUB_USER})"]
    for ev, msg in events_with_msg:
        repo_name = ev.get("repo", {}).get("name", "")
        repo_url = f"https://github.com/{repo_name}"
        created = to_kst(ev.get("created_at", ""))
        lines.append(f"- {msg} · [{repo_name}]({repo_url}) `{created} KST`")
        # PushEvent: 커밋 메시지 목록 추가
        if ev.get("type") == "PushEvent":
            commits = ev.get("payload", {}).get("commits", [])
            for commit in commits[:5]:
                sha = commit.get("sha", "")[:7]
                message = commit.get("message", "").split("\n")[0]
                commit_url = f"https://github.com/{repo_name}/commit/{commit.get('sha', '')}"
                lines.append(f"  - [`{sha}`]({commit_url}) {message}")

    payload = {"text": "\n".join(lines)}

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"[{now()}] Mattermost 전송 완료")
        else:
            print(f"[{now()}] Mattermost 오류: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"[{now()}] Mattermost 예외: {e}")


# ==================== 공통 모니터링 로직 ====================
def run_check(cfg):
    events = get_github_events(cfg)

    if not events:
        print(f"[{now()}] 이벤트를 가져오지 못했습니다 (API 오류 또는 활동 없음). 상태 유지.")
        return

    state = load_state()
    last_id = state.get("last_event_id")

    # 최초 실행: 현재 최신 이벤트 ID 저장 (과거 알림 스킵)
    if not last_id:
        state["last_event_id"] = str(events[0]["id"])
        save_state(state)
        print(f"[{now()}] 초기화 완료. 이후 새 활동부터 알림 전송.")
        return

    new_events = []
    found_last = False
    notify_types = cfg.get("notify_types", DEFAULT_CONFIG["notify_types"])
    for ev in events:
        if str(ev["id"]) == str(last_id):
            found_last = True
            break
        if _should_notify(ev, notify_types):
            new_events.append(ev)

    # last_id가 API 응답(최대 30개) 밖에 있는 경우 → 쌓인 이벤트 알림 후 상태 갱신
    if not found_last:
        state["last_event_id"] = str(events[0]["id"])
        save_state(state)
        if new_events:
            print(f"[{now()}] 상태 불일치 — 최근 이벤트 {len(new_events)}개 알림 전송 후 재초기화.")
        else:
            print(f"[{now()}] 상태 불일치 감지 — 상태 재초기화 완료.")
            return

    if new_events:
        state["last_event_id"] = str(events[0]["id"])
        save_state(state)

        print(f"[{now()}] 새 활동 {len(new_events)}개 감지!")

        events_with_msg = [(ev, format_event(ev)) for ev in reversed(new_events)]

        # Windows 팝업 (로컬 실행 시에만)
        if sys.platform == "win32":
            for ev, msg in events_with_msg:
                notify_windows(f"GitHub: {GITHUB_USER}", msg)
                time.sleep(1)

        count = len(new_events)
        subject = f"[GitHub] {GITHUB_USER} 새 활동 {count}건"
        html_body = build_email_body(events_with_msg)
        notify_gmail(subject, html_body, cfg)
        notify_mattermost(events_with_msg, cfg)

    else:
        print(f"[{now()}] 새 활동 없음")


# ==================== 메인 ====================
def main():
    parser = argparse.ArgumentParser(description="GitHub 활동 모니터")
    parser.add_argument("--once", action="store_true", help="한 번만 실행하고 종료 (GitHub Actions용)")
    args = parser.parse_args()

    cfg = load_config()
    interval = cfg.get("check_interval", 300)

    print("=" * 55)
    print("  GitHub 활동 모니터")
    print(f"  대상  : https://github.com/{GITHUB_USER}")
    print(f"  모드  : {'1회 실행' if args.once else f'{interval}초 ({interval // 60}분) 주기'}")
    print(f"  이메일: {'✅ ' + cfg['gmail_recipient'] if cfg.get('gmail_recipient') else '❌ 비활성'}")
    print(f"  Mattermost: {'✅ 활성' if cfg.get('mattermost_webhook') else '❌ 비활성'}")
    print("=" * 55)

    if args.once:
        try:
            run_check(cfg)
        except Exception as e:
            print(f"[{now()}] 오류: {e}")
    else:
        while True:
            try:
                run_check(cfg)
            except KeyboardInterrupt:
                print("\n모니터 종료")
                sys.exit(0)
            except Exception as e:
                print(f"[{now()}] 오류: {e}")
            time.sleep(interval)


if __name__ == "__main__":
    main()
