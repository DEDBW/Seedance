import os
import json
import time
import base64
import mimetypes
import tempfile
import requests
import gradio as gr

# --- ФАЙЛ ХРАНЕНИЯ НАСТРОЕК ---
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# --- ДОСТУПНЫЕ МОДЕЛИ ---
# Кортежи (Отображаемое имя, Реальный ID модели в OpenRouter)
MODEL_CHOICES = [
    ("Seedance 2.0 Fast", "bytedance/seedance-2.0-fast"),
    ("Seedance 2.0", "bytedance/seedance-2.0"),
    ("Seedance 2.0 Mini", "bytedance/seedance-2.0-mini"),
    ("Seedance 2.5", "bytedance/seedance-2.5"),
]

DEFAULT_CONFIG = {
    "api_key": "",
    "proxy": "",
    "model": "bytedance/seedance-2.0-fast",
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


def get_requests_proxies(proxy_url):
    """Формирует словарь proxies для библиотеки requests."""
    proxy = proxy_url.strip() if proxy_url else ""
    if not proxy:
        return None
    if not (proxy.startswith("http://") or proxy.startswith("https://") or proxy.startswith("socks5://")):
        proxy = f"http://{proxy}"
    return {
        "http": proxy,
        "https": proxy,
    }


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


def generate_video_ui(api_key, proxy, selected_model, user_prompt, resolution, aspect_ratio,
                      duration, seed_text, generate_audio, image_files, video_files, audio_files):
    """Основная функция генерации видео через OpenRouter Video Generation API."""
    api_key = api_key.strip() if api_key else ""
    if not api_key:
        yield "❌ Ошибка: Введите ваш OpenRouter API Key в блоке настроек!", None
        return

    if not user_prompt or not user_prompt.strip():
        yield "❌ Ошибка: Введите текстовый промпт!", None
        return

    # Автосохранение последних настроек
    save_config(api_key, proxy, selected_model, resolution, aspect_ratio, duration, generate_audio)

    proxies = get_requests_proxies(proxy)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # --- Сборка input_references ---
    input_references = []

    # 1. Изображения (base64)
    if image_files:
        if isinstance(image_files, str):
            image_files = [image_files]
        for idx, img_item in enumerate(image_files[:9], start=1):
            img_path = img_item.name if hasattr(img_item, 'name') else img_item
            if not img_path or not os.path.exists(img_path):
                continue
            yield f"🔄 Кодирование изображения #{idx} (@Image{idx}) в base64...", None
            data_url = file_to_data_url(img_path)
            if data_url:
                input_references.append({
                    "type": "image_url",
                    "image_url": {
                        "url": data_url
                    }
                })
                yield f"✅ Изображение #{idx} (@Image{idx}) добавлено (base64)", None
            else:
                yield f"❌ Ошибка при чтении изображения #{idx}", None
                return

    # 2. Видео (HTTPS через Catbox)
    if video_files:
        if isinstance(video_files, str):
            video_files = [video_files]
        for idx, vid_item in enumerate(video_files[:3], start=1):
            vid_path = vid_item.name if hasattr(vid_item, 'name') else vid_item
            if not vid_path or not os.path.exists(vid_path):
                continue
            yield f"📤 Загрузка видео-референса #{idx} (@Video{idx}) на Catbox...", None
            uploaded_vid_url, vid_err = upload_to_catbox(vid_path, proxies=proxies)
            if uploaded_vid_url:
                input_references.append({
                    "type": "video_url",
                    "video_url": {
                        "url": uploaded_vid_url
                    }
                })
                yield f"✅ Видео #{idx} (@Video{idx}) загружено: {uploaded_vid_url}", None
            else:
                yield f"❌ Ошибка загрузки видео #{idx} на Catbox: {vid_err}", None
                return

    # 3. Аудио (HTTPS через Catbox)
    if audio_files:
        if isinstance(audio_files, str):
            audio_files = [audio_files]
        for idx, aud_item in enumerate(audio_files[:3], start=1):
            aud_path = aud_item.name if hasattr(aud_item, 'name') else aud_item
            if not aud_path or not os.path.exists(aud_path):
                continue
            yield f"📤 Загрузка аудио-референса #{idx} (@Audio{idx}) на Catbox...", None
            uploaded_aud_url, aud_err = upload_to_catbox(aud_path, proxies=proxies)
            if uploaded_aud_url:
                input_references.append({
                    "type": "audio_url",
                    "audio_url": {
                        "url": uploaded_aud_url
                    }
                })
                yield f"✅ Аудио #{idx} (@Audio{idx}) загружено: {uploaded_aud_url}", None
            else:
                yield f"❌ Ошибка загрузки аудио #{idx} на Catbox: {aud_err}", None
                return

    # --- Формирование payload ---
    payload = {
        "model": selected_model,
        "prompt": user_prompt,
        "duration": int(duration),
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "generate_audio": generate_audio,
    }

    seed_text = seed_text.strip() if seed_text else ""
    if seed_text:
        try:
            payload["seed"] = int(seed_text)
        except ValueError:
            yield "⚠️ Seed должен быть целым числом. Игнорирую.", None

    if input_references:
        payload["input_references"] = input_references

    proxy_info = f"\nПрокси: {proxy}" if proxy else ""
    yield f"🚀 Отправка задачи на OpenRouter ({selected_model})...{proxy_info}\n\nПромпт: {user_prompt}\nВсего референсов: {len(input_references)}", None

    # --- Шаг 1: Отправка запроса ---
    try:
        response = requests.post(
            OPENROUTER_VIDEOS_URL,
            headers=headers,
            json=payload,
            proxies=proxies,
            timeout=60
        )

        if response.status_code not in (200, 201, 202):
            yield f"❌ Ошибка OpenRouter API (HTTP {response.status_code}):\n{response.text[:500]}", None
            return

        job_data = response.json()
        job_id = job_data.get("id")
        polling_url = job_data.get("polling_url")
        status = job_data.get("status", "unknown")

        if not job_id or not polling_url:
            yield f"❌ Не удалось получить ID задачи или polling_url:\n{job_data}", None
            return

        if polling_url.startswith("/"):
            polling_url = f"https://openrouter.ai{polling_url}"

        yield f"📋 Задача создана!\n  ID: {job_id}\n  Статус: {status}\n  Polling URL: {polling_url}", None

    except requests.exceptions.Timeout:
        yield "❌ Таймаут при отправке запроса. Попробуйте ещё раз.", None
        return
    except Exception as e:
        yield f"❌ Ошибка сетевого запроса: {e}", None
        return

    # --- Шаг 2: Поллинг статуса ---
    max_polls = 60  # 60 проверок по 15 секунд = 15 минут
    for check_step in range(max_polls):
        time.sleep(15)

        try:
            poll_response = requests.get(
                polling_url,
                headers=headers,
                proxies=proxies,
                timeout=30
            )
            poll_data = poll_response.json()
            current_status = poll_data.get("status", "unknown")

            yield (
                f"⏳ Генерация видео... (проверка {check_step + 1}/{max_polls})\n"
                f"  Модель: {selected_model}\n"
                f"  Статус: {current_status}"
            ), None

            if current_status == "completed":
                unsigned_urls = poll_data.get("unsigned_urls", [])
                usage = poll_data.get("usage", {})
                cost = usage.get("cost", "N/A")

                if unsigned_urls:
                    video_url = unsigned_urls[0]
                    yield (
                        f"✅ Видео готово!\n"
                        f"  Стоимость: ${cost}\n"
                        f"  Скачиваю видео..."
                    ), None

                    try:
                        video_response = requests.get(
                            video_url,
                            headers=headers,
                            proxies=proxies,
                            timeout=300
                        )
                        if video_response.status_code == 200:
                            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                                tmp.write(video_response.content)
                                tmp_path = tmp.name

                            yield (
                                f"✅ Видео успешно создано и скачано!\n"
                                f"  Модель: {selected_model}\n"
                                f"  Стоимость: ${cost}\n"
                                f"  URL: {video_url}"
                            ), tmp_path
                        else:
                            yield (
                                f"✅ Видео готово, но не удалось скачать (HTTP {video_response.status_code}).\n"
                                f"  Попробуйте скачать вручную: {video_url}"
                            ), None
                    except Exception as e:
                        yield f"✅ Видео готово, но ошибка при скачивании: {e}\n  URL: {video_url}", None
                else:
                    yield "❌ Видео готово, но OpenRouter не вернул URL файла.", None
                return

            elif current_status in ("failed", "cancelled", "expired"):
                error_msg = poll_data.get("error", "Нет деталей об ошибке")
                yield f"❌ Генерация прервана. Статус: {current_status}\n  Ошибка: {error_msg}", None
                return

        except Exception as e:
            yield f"⚠️ Ошибка сети при проверке статуса: {e}. Пробую снова...", None

    yield "⏱️ Превышено время ожидания (15 минут). Генерация может ещё продолжаться на стороне сервера.", None


# --- ИНИЦИАЛИЗАЦИЯ ИНТЕРФЕЙСА ---
init_config = load_config()

custom_css = """
footer {visibility: hidden !important; display: none !important;}
#api-indicator {display: none !important;}
"""

with gr.Blocks(
    title="Seedance — Генератор видео (OpenRouter)",
) as demo:
    gr.HTML("<style>footer {visibility: hidden !important; display: none !important;}</style>")
    gr.Markdown("# 🎬 Seedance — Генератор видео")
    gr.Markdown(
        "Генерация видео через **OpenRouter Video API** (Seedance 2.0 / 2.5). "
        "Поддерживает мульти-референсы: до **9 картинок**, до **3 видео** и до **3 аудио** (`@Image1`, `@Video1`, `@Audio1`)."
    )

    with gr.Accordion("⚙️ Настройки API и Подключения", open=not bool(init_config.get("api_key"))):
        with gr.Row():
            api_key_input = gr.Textbox(
                label="🔑 OpenRouter API Key",
                placeholder="sk-or-v1-...",
                value=init_config.get("api_key", ""),
                type="password",
                scale=3,
            )
            proxy_input = gr.Textbox(
                label="🌐 Прокси (HTTP / SOCKS5, опционально)",
                placeholder="http://user:pass@ip:port или socks5://ip:port",
                value=init_config.get("proxy", ""),
                scale=3,
            )
            save_btn = gr.Button("💾 Сохранить", size="sm", scale=1)
        save_status = gr.Markdown("")

    with gr.Row():
        with gr.Column(scale=1):
            model_selector = gr.Dropdown(
                choices=MODEL_CHOICES,
                value=init_config.get("model", "bytedance/seedance-2.0-fast"),
                label="🤖 Модель",
            )

            user_prompt = gr.Textbox(
                label="Промпт (текстовое описание видео)",
                placeholder="Пример: @Image1 in a futuristic cyberpunk city dancing with camera moving dynamically as seen in @Video1 to the rhythm of @Audio1",
                lines=4,
            )

            with gr.Row():
                resolution = gr.Dropdown(
                    choices=["480p", "720p", "1080p"],
                    value=init_config.get("resolution", "720p"),
                    label="Разрешение",
                )
                aspect_ratio = gr.Dropdown(
                    choices=["1:1", "9:16", "16:9", "4:3", "3:4"],
                    value=init_config.get("aspect_ratio", "9:16"),
                    label="Соотношение сторон",
                )

            with gr.Row():
                duration = gr.Slider(
                    minimum=4, maximum=15,
                    value=init_config.get("duration", 10),
                    step=1,
                    label="Длительность (секунд)",
                )
                seed_input = gr.Textbox(
                    label="Seed (опционально)",
                    placeholder="Оставьте пустым для случайного",
                    max_lines=1,
                )

            generate_audio = gr.Checkbox(
                label="Генерировать звук (автогенерация аудио видео)",
                value=init_config.get("generate_audio", True),
            )

            with gr.Accordion("📂 Референсы (Мультимодальность)", open=True):
                gr.Markdown(
                    "💡 *Вы можете выбрать сразу несколько файлов в каждом поле (удерживая Ctrl/Shift при выборе файлов).* "
                    "В промпте ссылайтесь как `@Image1`, `@Image2`, `@Video1`, `@Audio1` по порядку добавления."
                )
                image_inputs = gr.File(
                    label="🖼️ Изображения-референсы (до 9 шт)",
                    file_count="multiple",
                    file_types=["image"],
                )
                video_inputs = gr.File(
                    label="🎥 Видео-референсы (до 3 шт)",
                    file_count="multiple",
                    file_types=["video"],
                )
                audio_inputs = gr.File(
                    label="🎵 Аудио-референсы (до 3 шт)",
                    file_count="multiple",
                    file_types=["audio"],
                )

            btn = gr.Button("🚀 Запустить генерацию", variant="primary", size="lg")

        with gr.Column(scale=1):
            status_output = gr.Textbox(
                label="Статус выполнения",
                interactive=False,
                lines=12,
            )
            video_output = gr.Video(label="Результат")

    # Сохранение настроек по кнопке
    save_btn.click(
        fn=save_config,
        inputs=[
            api_key_input,
            proxy_input,
            model_selector,
            resolution,
            aspect_ratio,
            duration,
            generate_audio,
        ],
        outputs=[save_status],
    )

    # Запуск генерации
    btn.click(
        fn=generate_video_ui,
        inputs=[
            api_key_input,
            proxy_input,
            model_selector,
            user_prompt,
            resolution,
            aspect_ratio,
            duration,
            seed_input,
            generate_audio,
            image_inputs,
            video_inputs,
            audio_inputs,
        ],
        outputs=[status_output, video_output],
    )

    gr.HTML(
        "<div style='text-align: center; margin-top: 30px; padding: 18px 10px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace; font-size: 1.15rem; font-weight: 600; letter-spacing: 0.1em; color: #9ca3af; border-top: 1px solid rgba(156, 163, 175, 0.2); text-transform: uppercase;'>"
        "v1.0.0 · by <span style=\"font-weight: 800; color: #6366f1;\">DEDBW</span>"
        "</div>"
    )

if __name__ == "__main__":
    demo.queue().launch(inbrowser=True, show_error=True, theme=gr.themes.Soft())