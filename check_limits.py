"""
Запустите: python check_limits.py
Покажет реальные лимиты вашего ключа из заголовков ответа Gemini.
"""
import os, json, urllib.request, urllib.error

# Загружаем .env
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

KEY = os.environ.get("GEMINI_API_KEY", "")
if not KEY:
    print("GEMINI_API_KEY не найден — добавьте в .env")
    exit(1)

MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
]

for model in MODELS:
    print(f"\n── {model} ──")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": "1+1"}]}],
        "generationConfig": {"maxOutputTokens": 5}
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            print("  Статус: 200 OK")
            headers = dict(resp.headers)
            limit_keys = [k for k in headers if any(
                x in k.lower() for x in ["limit", "remain", "retry", "quota", "rate", "reset", "x-ratelimit"]
            )]
            if limit_keys:
                for k in limit_keys:
                    print(f"  {k}: {headers[k]}")
            else:
                print("  (заголовков с лимитами нет — Gemini их не возвращает явно)")

    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 429:
            print(f"  [429] Rate limit активен прямо сейчас!")
            print(f"  Retry-After: {e.headers.get('Retry-After', 'не указан')}")
        elif e.code == 404:
            print(f"  [404] Модель недоступна на вашем аккаунте")
        else:
            print(f"  [{e.code}] {body[:200]}")