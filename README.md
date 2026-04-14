# GitHub 활동 모니터

특정 GitHub 사용자의 공개 활동을 감지하여 **Windows 팝업 + Gmail + Mattermost**로 알림을 보내는 모니터링 스크립트입니다.

---

## 파일 구조

```
github_monitor/
├── monitor.py           # 메인 모니터링 스크립트
├── config.json          # 설정 파일
├── run.bat              # 실행 배치 파일
├── setup_autostart.bat  # 시작 프로그램 자동 등록
├── monitor.log          # 실행 로그 (자동 생성)
└── .monitor_state.json  # 마지막 이벤트 ID 저장 (자동 생성)
```

---

## 알림 채널

| 채널 | 방식 | 특징 |
|------|------|------|
| **Windows 팝업** | 시스템 트레이 말풍선 | 이벤트마다 1개씩 즉시 표시 |
| **Gmail** | SMTP (앱 비밀번호) | 묶어서 1통으로 전송 |
| **Mattermost** | Incoming Webhook | 묶어서 1개 메시지로 전송 |

---

## 감지하는 이벤트 종류

| 이벤트 | 설명 |
|--------|------|
| `PushEvent` | 커밋 푸시 |
| `CreateEvent` | 레포지토리 / 브랜치 생성 |
| `PullRequestEvent` | PR 오픈 / 머지 / 닫기 |
| `ReleaseEvent` | 릴리즈 발행 |
| `PublicEvent` | 레포지토리 공개 전환 |

> `config.json`의 `notify_types` 배열을 수정하면 감지 이벤트를 변경할 수 있습니다.

---

## 설정 (`config.json`)

```json
{
  "github_token": "",
  "gmail_sender": "보내는Gmail@gmail.com",
  "gmail_app_password": "xxxx xxxx xxxx xxxx",
  "gmail_recipient": "받는이메일@gmail.com",
  "mattermost_webhook": "https://your-mattermost.com/hooks/...",
  "check_interval": 300,
  "notify_types": [
    "PushEvent",
    "CreateEvent",
    "PullRequestEvent",
    "ReleaseEvent",
    "PublicEvent"
  ]
}
```

| 항목 | 설명 |
|------|------|
| `github_token` | GitHub Personal Access Token (선택). 없으면 시간당 60회 API 제한 |
| `gmail_sender` | 발송에 사용할 Gmail 주소 |
| `gmail_app_password` | Gmail 앱 비밀번호 16자리 (구글 계정 > 보안 > 앱 비밀번호) |
| `gmail_recipient` | 알림 받을 이메일 (본인 주소 입력 시 나에게 보내기) |
| `mattermost_webhook` | Mattermost Incoming Webhook URL |
| `check_interval` | GitHub API 폴링 주기 (초), 기본값 300 (5분) |

---

## 처음 설정하는 방법

### 1. Gmail 앱 비밀번호 발급

1. [Google 계정 > 보안](https://myaccount.google.com/security) → **2단계 인증** 활성화
2. 검색창에 **"앱 비밀번호"** 입력 → 앱: `메일`, 기기: `Windows` 선택
3. 생성된 16자리 비밀번호를 `config.json`의 `gmail_app_password`에 입력

### 2. Mattermost Incoming Webhook 발급

1. Mattermost 접속 → **메인 메뉴 > 통합 > Incoming Webhook**
2. **Incoming Webhook 추가** → 알림 받을 채널 선택 → 저장
3. 생성된 URL을 `config.json`의 `mattermost_webhook`에 입력

### 3. 실행

```bat
run.bat
```

### 4. 시작 프로그램 등록 (선택)

`setup_autostart.bat`을 **관리자 권한으로 실행**하면 Windows 로그인 시 자동으로 모니터가 시작됩니다.

---

## 실행 / 중지

**실행**
```bat
run.bat
```

또는 직접:
```bash
python monitor.py
```

**중지**
- 터미널에서 `Ctrl+C`
- 또는 작업 관리자에서 `python.exe` 프로세스 종료

**로그 확인**
```bash
tail -f monitor.log
```

---

## 알림 예시

### Windows 팝업
```
GitHub: username
📦 커밋 푸시 (3개): username/my-project
```

### Gmail 제목
```
[GitHub] username 새 활동 2건
```

### Mattermost 메시지
```
#### GitHub 새 활동 감지 — username
- 📦 커밋 푸시 (3개): username/my-project · 2026-04-09 15:30 UTC
- ✨ 브랜치 생성: username/my-project · 2026-04-09 15:31 UTC
```

---

## 주의사항

- GitHub API는 인증 없이 시간당 60회 요청 제한이 있습니다. 5분 주기로 설정 시 하루 288회 사용하므로 `github_token` 설정을 권장합니다.
- 모니터는 **공개(public) 활동만** 감지합니다. Private 레포지토리 활동은 감지되지 않습니다.
