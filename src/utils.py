import os
import time
import base64
import mimetypes
import requests
from src.config import CATBOX_API_URL


def get_requests_proxies(proxy_url):
    """Формирует словарь proxies для библиотеки requests."""
    proxy = proxy_url.strip() if proxy_url else ""
    if not proxy:
        return None
    if not (proxy.startswith("http://") or proxy.startswith("https://") or proxy.startswith("socks5://") or proxy.startswith("socks5h://")):
        proxy = f"http://{proxy}"
    return {
        "http": proxy,
        "https": proxy,
    }


def check_proxy(proxy_url):
    """Проверяет работоспособность и скорость отклика прокси."""
    proxy = proxy_url.strip() if proxy_url else ""
    if not proxy:
        return "⚠️ Введите адрес прокси для проверки!"

    proxies = get_requests_proxies(proxy)
    try:
        start_t = time.time()
        resp = requests.get(
            "https://openrouter.ai/api/v1/models",
            proxies=proxies,
            timeout=10
        )
        elapsed_ms = int((time.time() - start_t) * 1000)
        if resp.status_code == 200:
            return f"✅ Прокси работает! Соединение с OpenRouter успешно (отклик: {elapsed_ms} мс)."
        else:
            return f"⚠️ Прокси подключился, но OpenRouter вернул HTTP {resp.status_code} ({elapsed_ms} мс)."
    except requests.exceptions.Timeout:
        return "❌ Ошибка: Превышено время ожидания (10 сек). Прокси недоступен или слишком медленный."
    except requests.exceptions.ProxyError as pe:
        return f"❌ Ошибка прокси: Не удалось установить соединение ({pe})."
    except Exception as e:
        return f"❌ Ошибка проверки прокси: {e}"


def file_to_data_url(file_path):
    """Кодирует файл в base64 data URL (для изображений)."""
    if not file_path or not os.path.exists(file_path):
        return None

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime_type = mime_map.get(ext, "image/jpeg")

    with open(file_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{data}"


def upload_to_catbox(file_path, proxies=None):
    """Загружает локальный файл на Catbox (для аудио и видео референсов)."""
    if not file_path or not os.path.exists(file_path):
        return None, "Файл не найден"

    payload = {"reqtype": "fileupload"}
    try:
        with open(file_path, "rb") as f:
            ext = os.path.splitext(file_path)[1].lower() or ".bin"
            safe_filename = os.path.basename(file_path).encode("ascii", errors="replace").decode("ascii")
            if not safe_filename or safe_filename.startswith("?"):
                safe_filename = f"upload_{int(time.time())}{ext}"
            files = {"fileToUpload": (safe_filename, f)}
            response = requests.post(
                CATBOX_API_URL,
                data=payload,
                files=files,
                proxies=proxies,
                timeout=120
            )

        if response.status_code == 200 and response.text.strip().startswith("https://"):
            return response.text.strip(), None
        else:
            err = f"HTTP {response.status_code}: {response.text[:300]}"
            return None, err
    except Exception as e:
        return None, str(e)


def extract_file_paths(files):
    """Извлекает список путей к файлам из данных Gradio File."""
    if not files:
        return []
    if isinstance(files, str):
        return [files]
    paths = []
    for f in files:
        if hasattr(f, 'name'):
            paths.append(f.name)
        elif isinstance(f, str):
            paths.append(f)
    return paths


def format_gen_time(seconds):
    """Форматирует секунды в строку MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    if mins > 0:
        return f"{mins:02d}:{secs:02d} ({mins} мин {secs} сек)"
    return f"{mins:02d}:{secs:02d} ({secs} сек)"
