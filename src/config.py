import os
import json

# --- ПУТИ К ФАЙЛАМ ---
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT_DIR, "config.json")
OUTPUTS_DIR = os.path.join(ROOT_DIR, "outputs")
HISTORY_FILE = os.path.join(OUTPUTS_DIR, "history.json")

# Создаем папку outputs при старте
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# --- ДОСТУПНЫЕ МОДЕЛИ ---
# Кортежи (Отображаемое имя, Реальный ID модели в OpenRouter)
MODEL_CHOICES = [
    ("Seedance 2.5", "bytedance/seedance-2.5"),
    ("Seedance 2.0", "bytedance/seedance-2.0"),
    ("Seedance 2.0 Fast", "bytedance/seedance-2.0-fast"),
    ("Seedance 2.0 Mini", "bytedance/seedance-2.0-mini"),
]

DEFAULT_CONFIG = {
    "api_key": "",
    "proxy": "",
    "model": "bytedance/seedance-2.5",
    "resolution": "720p",
    "aspect_ratio": "9:16",
    "duration": 10,
    "generate_audio": True,
}

CATBOX_API_URL = "https://catbox.moe/user/api.php"
OPENROUTER_VIDEOS_URL = "https://openrouter.ai/api/v1/videos"


def load_config():
    """Загружает сохраненные настройки из JSON-файла."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(saved)
                return config
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(api_key, proxy, model, resolution, aspect_ratio, duration, generate_audio):
    """Сохраняет текущие настройки в JSON-файл."""
    config = {
        "api_key": api_key.strip() if api_key else "",
        "proxy": proxy.strip() if proxy else "",
        "model": model,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "duration": int(duration),
        "generate_audio": bool(generate_audio),
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return "✅ Настройки успешно сохранены!"
    except Exception as e:
        return f"⚠️ Ошибка при сохранении настроек: {e}"


def load_history():
    """Загружает список задач и сгенерированных видео из истории."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_history(history_list):
    """Сохраняет список истории в JSON-файл."""
    try:
        os.makedirs(OUTPUTS_DIR, exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_list, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def add_history_entry(entry):
    """Добавляет новую запись в начало истории."""
    history = load_history()
    # Проверяем, нет ли уже такой задачи по job_id
    job_id = entry.get("job_id")
    if job_id:
        history = [item for item in history if item.get("job_id") != job_id]
    history.insert(0, entry)
    save_history(history)
    return history


def update_history_entry(job_id, updates):
    """Обновляет статус и данные задачи в истории по job_id."""
    history = load_history()
    for item in history:
        if item.get("job_id") == job_id or item.get("polling_url") == job_id:
            item.update(updates)
            break
    save_history(history)
    return history

