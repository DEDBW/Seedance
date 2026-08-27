import os
import time
import requests

from src.config import (
    OPENROUTER_VIDEOS_URL,
    OUTPUTS_DIR,
    save_config,
    load_history,
    add_history_entry,
    update_history_entry,
)
from src.utils import (
    get_requests_proxies,
    file_to_data_url,
    upload_to_catbox,
    extract_file_paths,
    format_gen_time,
)


def generate_video_ui(api_key, proxy, selected_model, user_prompt, resolution, aspect_ratio,
                      duration, generate_audio, image_files, video_files, audio_files):
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
    image_paths = extract_file_paths(image_files)[:9]
    if image_paths:
        for idx, img_path in enumerate(image_paths, start=1):
            if not img_path or not os.path.exists(img_path):
                continue
            yield f"🔄 Подготовка изображения #{idx} (@Image{idx})...", None
            data_url = file_to_data_url(img_path)
            if data_url:
                input_references.append({
                    "type": "image_url",
                    "image_url": {
                        "url": data_url
                    }
                })
                yield f"✅ Изображение #{idx} (@Image{idx}) закодировано (base64)", None
            else:
                yield f"❌ Ошибка при чтении изображения #{idx}", None
                return

    # 2. Видео (HTTPS через Catbox)
    video_paths = extract_file_paths(video_files)[:3]
    if video_paths:
        for idx, vid_path in enumerate(video_paths, start=1):
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
                yield f"✅ Видео #{idx} (@Video{idx}) загружено на Catbox", None
            else:
                yield f"❌ Ошибка загрузки видео #{idx} на Catbox: {vid_err}", None
                return

    # 3. Аудио (HTTPS через Catbox)
    audio_paths = extract_file_paths(audio_files)[:3]
    if audio_paths:
        for idx, aud_path in enumerate(audio_paths, start=1):
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
                yield f"✅ Аудио #{idx} (@Audio{idx}) загружено на Catbox", None
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

    if input_references:
        payload["input_references"] = input_references

    proxy_info = f"\nПрокси: {proxy}" if proxy else ""
    yield (
        f"🚀 Отправка задачи на OpenRouter ({selected_model})...{proxy_info}\n\n"
        f"Промпт: {user_prompt}\n"
        f"Всего референсов: {len(input_references)}"
    ), None

    # --- Шаг 1: Отправка запроса ---
    try:
        response = requests.post(
            OPENROUTER_VIDEOS_URL,
            headers=headers,
            json=payload,
            proxies=proxies,
            timeout=90
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

        # СРАЗУ СОХРАНЯЕМ В ИСТОРИЮ, чтобы не потерять ID задачи при обрыве связи!
        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
        add_history_entry({
            "job_id": job_id,
            "polling_url": polling_url,
            "timestamp": timestamp_str,
            "prompt": user_prompt,
            "model": selected_model,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "duration": int(duration),
            "status": "processing",
            "cost": "N/A",
            "video_url": None,
            "local_path": None,
            "error": None,
        })

    except requests.exceptions.Timeout:
        yield "❌ Таймаут при отправке запроса на OpenRouter (сервер не ответил за 90с). Попробуйте ещё раз.", None
        return
    except Exception as e:
        yield f"❌ Ошибка сетевого запроса: {e}", None
        return

    # --- Шаг 2: Отсчет времени ИМЕННО С НАЧАЛА ГЕНЕРАЦИИ на сервере с непрерывным таймером ---
    generation_start_time = time.time()
    poll_interval = 4  # Запрос к API каждые 4 секунды
    last_poll_time = 0
    max_wait_seconds = 1200  # 20 минут
    current_status = status
    poll_count = 0
    completed_poll_data = None
    consecutive_network_errors = 0

    while (time.time() - generation_start_time) < max_wait_seconds:
        now = time.time()
        if now - last_poll_time >= poll_interval:
            last_poll_time = now
            poll_count += 1
            try:
                poll_response = requests.get(
                    polling_url,
                    headers=headers,
                    proxies=proxies,
                    timeout=30
                )
                poll_data = poll_response.json()
                current_status = poll_data.get("status", current_status)
                consecutive_network_errors = 0

                if current_status == "completed":
                    completed_poll_data = poll_data
                    break
                elif current_status in ("failed", "cancelled", "expired"):
                    error_msg = poll_data.get("error", "Нет деталей об ошибке")
                    total_time = format_gen_time(time.time() - generation_start_time)
                    update_history_entry(job_id, {
                        "status": current_status,
                        "error": str(error_msg),
                        "gen_time": total_time,
                    })
                    yield f"❌ Генерация прервана (время: {total_time}).\nСтатус: {current_status}\nОшибка: {error_msg}\n\n💡 ID задачи сохранен в Истории: {job_id}", None
                    return
            except Exception as e:
                consecutive_network_errors += 1
                # Не прерываем сразу при единичных сбоях сети (продолжаем поллинг)
                if consecutive_network_errors >= 15:
                    total_time = format_gen_time(time.time() - generation_start_time)
                    yield f"⚠️ Временная потеря связи с сервером ({e}).\nЗадача {job_id} сохранена в истории! Вы сможете восстановить видео во вкладке 'История'.", None

        elapsed_sec = time.time() - generation_start_time
        time_display = format_gen_time(elapsed_sec)

        yield (
            f"⏳ Идет генерация видео на сервере...\n"
            f"⏱️ Время генерации: {time_display}\n"
            f"🤖 Модель: {selected_model}\n"
            f"📋 Задача: {job_id}\n"
            f"📊 Статус: {current_status} (проверок: {poll_count})"
        ), None

        time.sleep(1)

    if not completed_poll_data:
        total_time = format_gen_time(time.time() - generation_start_time)
        yield f"⏱️ Превышено время ожидания генерации ({total_time}). ID задачи сохранен в Истории: {job_id}", None
        return

    # --- Шаг 3: Сохранение готового видео в папку outputs/ ---
    total_gen_time = format_gen_time(time.time() - generation_start_time)
    unsigned_urls = completed_poll_data.get("unsigned_urls", [])
    usage = completed_poll_data.get("usage", {})
    cost = usage.get("cost", "N/A")

    if unsigned_urls:
        video_url = unsigned_urls[0]
        yield (
            f"✅ Видео успешно сгенерировано!\n"
            f"⏱️ Время генерации: {total_gen_time}\n"
            f"💰 Стоимость: ${cost}\n"
            f"📥 Скачиваю видео в папку outputs..."
        ), None

        try:
            video_response = requests.get(
                video_url,
                headers=headers,
                proxies=proxies,
                timeout=300
            )
            if video_response.status_code == 200:
                clean_date = time.strftime("%Y%m%d_%H%M%S")
                safe_id = "".join(c for c in str(job_id) if c.isalnum() or c in ("-", "_"))[-8:]
                filename = f"seedance_{clean_date}_{safe_id}.mp4"
                saved_path = os.path.join(OUTPUTS_DIR, filename)

                with open(saved_path, "wb") as f:
                    f.write(video_response.content)

                # Обновляем историю
                update_history_entry(job_id, {
                    "status": "completed",
                    "cost": cost,
                    "video_url": video_url,
                    "local_path": saved_path,
                    "gen_time": total_gen_time,
                })

                yield (
                    f"🎉 Видео успешно создано и сохранено в outputs!\n"
                    f"📁 Файл: {filename}\n"
                    f"⏱️ Время генерации: {total_gen_time}\n"
                    f"🤖 Модель: {selected_model}\n"
                    f"💰 Стоимость: ${cost}\n"
                    f"🔗 URL: {video_url}"
                ), saved_path
            else:
                update_history_entry(job_id, {
                    "status": "completed",
                    "cost": cost,
                    "video_url": video_url,
                    "gen_time": total_gen_time,
                })
                yield (
                    f"✅ Видео сгенерировано на сервере!\n"
                    f"⏱️ Время генерации: {total_gen_time}\n"
                    f"💰 Стоимость: ${cost}\n"
                    f"⚠️ Не удалось автоматически скачать в outputs (HTTP {video_response.status_code}).\n"
                    f"🔗 Скачайте вручную: {video_url}\n"
                    f"💡 Или восстановите во вкладке 'История'."
                ), None
        except Exception as e:
            update_history_entry(job_id, {
                "status": "completed",
                "cost": cost,
                "video_url": video_url,
                "gen_time": total_gen_time,
            })
            yield (
                f"✅ Видео сгенерировано на сервере!\n"
                f"⏱️ Время генерации: {total_gen_time}\n"
                f"💰 Стоимость: ${cost}\n"
                f"⚠️ Ошибка при скачивании: {e}\n"
                f"🔗 Скачайте вручную: {video_url}\n"
                f"💡 Или восстановите во вкладке 'История'."
            ), None
    else:
        yield f"❌ Видео готово ({total_gen_time}), но OpenRouter не вернул URL файла.", None


def recover_task_status(task_id_or_url, api_key, proxy):
    """Проверяет статус задачи по ID или Polling URL и скачивает видео в outputs/ при готовности."""
    api_key = api_key.strip() if api_key else ""
    if not api_key:
        return "❌ Ошибка: Введите OpenRouter API Key в блоке настроек!", None

    task_id_or_url = (task_id_or_url or "").strip()
    if not task_id_or_url:
        return "⚠️ Введите ID задачи или Polling URL!", None

    job_id = task_id_or_url
    if task_id_or_url.startswith("http://") or task_id_or_url.startswith("https://"):
        polling_url = task_id_or_url
        job_id = task_id_or_url.rstrip("/").split("/")[-1]
    elif task_id_or_url.startswith("/"):
        polling_url = f"https://openrouter.ai{task_id_or_url}"
        job_id = task_id_or_url.rstrip("/").split("/")[-1]
    else:
        # Проверяем наличие в истории
        history = load_history()
        found_url = None
        for item in history:
            if item.get("job_id") == job_id and item.get("polling_url"):
                found_url = item.get("polling_url")
                break
        if found_url:
            polling_url = found_url
        else:
            polling_url = f"https://openrouter.ai/api/v1/videos/{job_id}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    proxies = get_requests_proxies(proxy)

    try:
        resp = requests.get(polling_url, headers=headers, proxies=proxies, timeout=30)
        if resp.status_code != 200:
            return f"❌ Ошибка проверки задачи (HTTP {resp.status_code}):\n{resp.text[:400]}", None

        data = resp.json()
        status = data.get("status", "unknown")
        usage = data.get("usage", {})
        cost = usage.get("cost", "N/A")
        unsigned_urls = data.get("unsigned_urls", [])

        if status == "completed":
            if unsigned_urls:
                video_url = unsigned_urls[0]
                clean_date = time.strftime("%Y%m%d_%H%M%S")
                safe_id = "".join(c for c in str(job_id) if c.isalnum() or c in ("-", "_"))[-8:]
                filename = f"seedance_recovered_{clean_date}_{safe_id}.mp4"
                saved_path = os.path.join(OUTPUTS_DIR, filename)

                v_resp = requests.get(video_url, headers=headers, proxies=proxies, timeout=300)
                if v_resp.status_code == 200:
                    with open(saved_path, "wb") as f:
                        f.write(v_resp.content)

                    update_history_entry(job_id, {
                        "status": "completed",
                        "cost": cost,
                        "video_url": video_url,
                        "local_path": saved_path,
                    })
                    return (
                        f"🎉 Видео успешно найдено и скачано в outputs!\n"
                        f"📁 Файл: {filename}\n"
                        f"💰 Стоимость: ${cost}\n"
                        f"🔗 URL: {video_url}"
                    ), saved_path
                else:
                    return f"✅ Задача завершена (Стоимость: ${cost}), но не удалось скачать файл (HTTP {v_resp.status_code}). URL: {video_url}", None
            return "✅ Задача завершена, но URL видео отсутствует.", None
        elif status in ("failed", "cancelled", "expired"):
            err = data.get("error", "Нет деталей об ошибке")
            update_history_entry(job_id, {"status": status, "error": str(err)})
            return f"❌ Задача завершилась со статусом '{status}':\n{err}", None
        else:
            return f"⏳ Задача '{job_id}' в данный момент выполняется на сервере (статус: {status}).\nПопробуйте повторить проверку через некоторое время.", None

    except Exception as e:
        return f"❌ Ошибка сетевого запроса: {e}", None
