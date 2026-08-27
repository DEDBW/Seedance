import os
import platform
import subprocess
import gradio as gr

from src.config import MODEL_CHOICES, OUTPUTS_DIR, load_config, save_config, load_history
from src.utils import check_proxy, extract_file_paths
from src.api import generate_video_ui, recover_task_status

custom_css = """
footer {visibility: hidden !important; display: none !important;}
#api-indicator {display: none !important;}
.references-hint {
    margin-bottom: 12px !important;
}
.compact-file {
    min-height: 130px !important;
}
.quick-tags-box {
    margin-top: 6px !important;
    margin-bottom: 8px !important;
    padding: 8px 12px !important;
    background: rgba(99, 102, 241, 0.08) !important;
    border-radius: 8px !important;
    border: 1px solid rgba(99, 102, 241, 0.2) !important;
}
.quick-tag-btn {
    min-width: 80px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
}
.preview-container-box {
    margin-top: 10px !important;
    padding: 12px !important;
    border: 1px dashed rgba(156, 163, 175, 0.35) !important;
    border-radius: 8px !important;
}
"""

head_script = """
<script>
window.insertTagAtPromptCursor = function(tag) {
    const el = document.querySelector('#prompt-input textarea');
    if (!el) return;
    const start = (el.selectionStart !== null && el.selectionStart !== undefined) ? el.selectionStart : el.value.length;
    const end = (el.selectionEnd !== null && el.selectionEnd !== undefined) ? el.selectionEnd : el.value.length;
    const text = el.value || '';
    const before = text.substring(0, start);
    const after = text.substring(end);
    
    const needSpaceBefore = before.length > 0 && !before.endsWith(' ') && !before.endsWith('\\n');
    const needSpaceAfter = !after.startsWith(' ') && !after.startsWith('\\n');
    const spaceBefore = needSpaceBefore ? ' ' : '';
    const spaceAfter = needSpaceAfter ? ' ' : '';
    
    const insertion = spaceBefore + tag + spaceAfter;
    const newText = before + insertion + after;
    
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
    if (nativeSetter) {
        nativeSetter.call(el, newText);
    } else {
        el.value = newText;
    }
    
    const newCursorPos = start + insertion.length;
    el.focus();
    el.setSelectionRange(newCursorPos, newCursorPos);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return newText;
};
</script>
"""


def get_history_choices():
    """Формирует список вариантов для выпадающего списка истории."""
    history = load_history()
    choices = []
    for item in history:
        ts = item.get("timestamp", "")
        model = item.get("model", "").split("/")[-1]
        status = item.get("status", "")
        prompt_snippet = (item.get("prompt") or "")[:35].replace("\n", " ")
        cost = f"${item.get('cost')}" if item.get("cost") not in (None, "N/A") else ""
        label = f"[{ts}] {model} | {status.upper()} | {prompt_snippet}... {cost}".strip()
        job_id = item.get("job_id") or item.get("polling_url")
        choices.append((label, job_id))
    return choices


def on_select_history_item(job_id):
    """Отображает детали и видео выбранной записи истории."""
    if not job_id:
        return "Выберите запись из списка выше.", None
    history = load_history()
    for item in history:
        if item.get("job_id") == job_id or item.get("polling_url") == job_id:
            md = (
                f"### 📋 Детали задачи `{item.get('job_id')}`\n\n"
                f"* **Дата/Время**: {item.get('timestamp')}\n"
                f"* **Модель**: `{item.get('model')}`\n"
                f"* **Статус**: `{item.get('status')}`\n"
                f"* **Стоимость**: `{item.get('cost')}`\n"
                f"* **Параметры**: {item.get('resolution')} | {item.get('aspect_ratio')} | {item.get('duration')} сек\n"
                f"* **Промпт**: {item.get('prompt')}\n"
            )
            if item.get("video_url"):
                md += f"* **Ссылка OpenRouter**: [Открыть видео в браузере]({item.get('video_url')})\n"
            if item.get("local_path"):
                md += f"* **Локальный файл**: `{item.get('local_path')}`\n"
            if item.get("error"):
                md += f"* **Ошибка**: `{item.get('error')}`\n"

            loc = item.get("local_path")
            if loc and os.path.exists(loc):
                return md, loc
            elif item.get("video_url"):
                return md, item.get("video_url")
            return md, None
    return "Запись не найдена в истории.", None


def open_outputs_folder():
    """Открывает папку outputs в проводнике операционной системы."""
    path = os.path.abspath(OUTPUTS_DIR)
    os.makedirs(path, exist_ok=True)
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return f"📂 Папка открыта: `{path}`"
    except Exception as e:
        return f"📁 Путь к папке: `{path}` ({e})"


def create_ui():
    """Создает и настраивает веб-интерфейс Gradio Blocks."""
    init_config = load_config()

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
                test_proxy_btn = gr.Button("⚡ Проверить прокси", size="sm", scale=1)
                save_btn = gr.Button("💾 Сохранить", size="sm", scale=1)
            save_status = gr.Markdown("")

        with gr.Row():
            with gr.Column(scale=1):
                model_selector = gr.Dropdown(
                    choices=MODEL_CHOICES,
                    value=init_config.get("model", "bytedance/seedance-2.5"),
                    label="🤖 Модель",
                )

                user_prompt = gr.Textbox(
                    label="Промпт (текстовое описание видео)",
                    placeholder="Пример: @Image1 in a futuristic cyberpunk city dancing with camera moving dynamically as seen in @Video1 to the rhythm of @Audio1",
                    lines=4,
                    elem_id="prompt-input",
                )

                # Быстрые кнопки добавления тегов в позицию курсора (под окошком промпта)
                with gr.Column(visible=False, elem_classes=["quick-tags-box"]) as quick_tags_container:
                    gr.Markdown("🏷️ **Вставить референс в место курсора (кликните):**")
                    with gr.Row():
                        img_tag_btns = [
                            gr.Button(f"+ @Image{i+1}", size="sm", visible=False, scale=1, elem_classes=["quick-tag-btn"])
                            for i in range(9)
                        ]
                    with gr.Row():
                        vid_tag_btns = [
                            gr.Button(f"+ @Video{i+1}", size="sm", visible=False, scale=1, elem_classes=["quick-tag-btn"])
                            for i in range(3)
                        ]
                        aud_tag_btns = [
                            gr.Button(f"+ @Audio{i+1}", size="sm", visible=False, scale=1, elem_classes=["quick-tag-btn"])
                            for i in range(3)
                        ]

                with gr.Row():
                    resolution = gr.Dropdown(
                        choices=["480p", "720p", "1080p"],
                        value=init_config.get("resolution", "720p"),
                        label="Разрешение",
                        scale=1,
                    )
                    aspect_ratio = gr.Dropdown(
                        choices=["1:1", "9:16", "16:9", "4:3", "3:4"],
                        value=init_config.get("aspect_ratio", "9:16"),
                        label="Соотношение сторон",
                        scale=1,
                    )
                    duration = gr.Slider(
                        minimum=4, maximum=15,
                        value=init_config.get("duration", 10),
                        step=1,
                        label="Длительность (сек)",
                        scale=2,
                    )

                generate_audio = gr.Checkbox(
                    label="Генерировать звук (автогенерация аудио видео)",
                    value=init_config.get("generate_audio", True),
                )

                with gr.Accordion("📂 Референсы (Мультимодальность)", open=True):
                    gr.Markdown(
                        "💡 *В каждом поле можно выбрать несколько файлов. "
                        "В промпте ссылайтесь как `@Image1`, `@Video1`, `@Audio1`.*",
                        elem_classes=["references-hint"],
                    )
                    with gr.Row():
                        image_inputs = gr.File(
                            label="🖼️ Картинки (до 9)",
                            file_count="multiple",
                            file_types=["image"],
                            elem_classes=["compact-file"],
                        )
                        video_inputs = gr.File(
                            label="🎥 Видео (до 3)",
                            file_count="multiple",
                            file_types=["video"],
                            elem_classes=["compact-file"],
                        )
                        audio_inputs = gr.File(
                            label="🎵 Аудио (до 3)",
                            file_count="multiple",
                            file_types=["audio"],
                            elem_classes=["compact-file"],
                        )

                    # Галочка предпросмотра файлов
                    show_preview_cb = gr.Checkbox(
                        label="👁️ Показать предпросмотр добавленных файлов",
                        value=False,
                    )

                    # Блок предпросмотра файлов
                    with gr.Column(visible=False, elem_classes=["preview-container-box"]) as preview_container:
                        preview_gallery = gr.Gallery(
                            label="🖼️ Картинки (кликните для вставки @Image в промпт)",
                            columns=3,
                            height="auto",
                            object_fit="contain",
                            preview=False,
                            visible=False,
                        )
                        with gr.Row():
                            vid_previews = [
                                gr.Video(label=f"🎥 @Video{i+1}", visible=False, interactive=False, height=240)
                                for i in range(3)
                            ]
                        with gr.Row():
                            aud_previews = [
                                gr.Audio(label=f"🎵 @Audio{i+1}", visible=False, interactive=False)
                                for i in range(3)
                            ]

                btn = gr.Button("🚀 Запустить генерацию", variant="primary", size="lg")

            with gr.Column(scale=1):
                status_output = gr.Textbox(
                    label="Статус выполнения",
                    interactive=False,
                    lines=12,
                )
                video_output = gr.Video(label="Результат", height=380)

        # --- Раздел: История и Восстановление ---
        with gr.Accordion("📜 История генераций и Восстановление задач", open=False):
            gr.Markdown(
                "💡 *Все сгенерированные видео автоматически сохраняются в папку `outputs/`. "
                "Если связь оборвалась во время генерации, задача сохранена в истории — вы можете восстановить её в один клик!*"
            )
            with gr.Row():
                history_dropdown = gr.Dropdown(
                    label="📋 Выберите задачу из истории",
                    choices=get_history_choices(),
                    value=get_history_choices()[0][1] if get_history_choices() else None,
                    interactive=True,
                    scale=3,
                )
                refresh_history_btn = gr.Button("🔄 Обновить историю", size="sm", scale=1)
                open_folder_btn = gr.Button("📂 Папка outputs", size="sm", scale=1)

            folder_status = gr.Markdown("")

            with gr.Row():
                with gr.Column(scale=1):
                    history_details = gr.Markdown("Выберите запись из списка выше для просмотра информации.")
                with gr.Column(scale=1):
                    history_video_player = gr.Video(label="Просмотр видео из истории", height=280)

            with gr.Accordion("🛠️ Восстановление по произвольному ID задачи / URL", open=False):
                with gr.Row():
                    task_id_input = gr.Textbox(
                        label="ID задачи или Polling URL",
                        placeholder="Например: gen_01j... или https://openrouter.ai/api/v1/videos/...",
                        scale=3,
                    )
                    recover_btn = gr.Button("🔄 Проверить и скачать", variant="primary", size="sm", scale=1)
                recover_status = gr.Markdown("")
                recover_video = gr.Video(label="Восстановленное видео", height=280)

        # --- Обработчики нажатий на кнопки тегов (вставка в место курсора) ---
        for idx, b in enumerate(img_tag_btns, start=1):
            tag_val = f"@Image{idx}"
            b.click(
                fn=None,
                js=f"() => window.insertTagAtPromptCursor('{tag_val}')",
            )

        for idx, b in enumerate(vid_tag_btns, start=1):
            tag_val = f"@Video{idx}"
            b.click(
                fn=None,
                js=f"() => window.insertTagAtPromptCursor('{tag_val}')",
            )

        for idx, b in enumerate(aud_tag_btns, start=1):
            tag_val = f"@Audio{idx}"
            b.click(
                fn=None,
                js=f"() => window.insertTagAtPromptCursor('{tag_val}')",
            )

        # Клик по картинке в галерее предпросмотра (вставка в место курсора)
        preview_gallery.select(
            fn=None,
            js="(evt) => { const i = (evt && evt.index !== undefined) ? evt.index : (evt && evt.detail ? evt.detail.index : 0); window.insertTagAtPromptCursor('@Image' + (i + 1)); }",
        )

        # Переключение видимости предпросмотра
        show_preview_cb.change(
            fn=lambda shown: gr.update(visible=shown),
            inputs=[show_preview_cb],
            outputs=[preview_container],
        )

        # Обновление кнопок и предпросмотра при загрузке картинок
        def on_image_inputs_change(files):
            paths = extract_file_paths(files)[:9]
            n = len(paths)
            btn_updates = [gr.update(visible=(i < n)) for i in range(9)]
            gallery_update = gr.update(value=paths, visible=bool(n))
            container_visible = gr.update(visible=bool(n))
            return btn_updates + [gallery_update, container_visible]

        image_inputs.change(
            fn=on_image_inputs_change,
            inputs=[image_inputs],
            outputs=img_tag_btns + [preview_gallery, quick_tags_container],
        )

        # Обновление кнопок и предпросмотра при загрузке видео
        def on_video_inputs_change(files):
            paths = extract_file_paths(files)[:3]
            n = len(paths)
            btn_updates = [gr.update(visible=(i < n)) for i in range(3)]
            vid_updates = [gr.update(value=paths[i] if i < n else None, visible=(i < n)) for i in range(3)]
            container_visible = gr.update(visible=bool(n))
            return btn_updates + vid_updates + [container_visible]

        video_inputs.change(
            fn=on_video_inputs_change,
            inputs=[video_inputs],
            outputs=vid_tag_btns + vid_previews + [quick_tags_container],
        )

        # Обновление кнопок и предпросмотра при загрузке аудио
        def on_audio_inputs_change(files):
            paths = extract_file_paths(files)[:3]
            n = len(paths)
            btn_updates = [gr.update(visible=(i < n)) for i in range(3)]
            aud_updates = [gr.update(value=paths[i] if i < n else None, visible=(i < n)) for i in range(3)]
            container_visible = gr.update(visible=bool(n))
            return btn_updates + aud_updates + [container_visible]

        audio_inputs.change(
            fn=on_audio_inputs_change,
            inputs=[audio_inputs],
            outputs=aud_tag_btns + aud_previews + [quick_tags_container],
        )

        # Проверка прокси по кнопке
        test_proxy_btn.click(
            fn=check_proxy,
            inputs=[proxy_input],
            outputs=[save_status],
        )

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

        # Обработчики Истории
        def update_history_view():
            choices = get_history_choices()
            first_val = choices[0][1] if choices else None
            details, vid = on_select_history_item(first_val) if first_val else ("История пуста.", None)
            return gr.update(choices=choices, value=first_val), details, vid

        refresh_history_btn.click(
            fn=update_history_view,
            outputs=[history_dropdown, history_details, history_video_player],
        )

        history_dropdown.change(
            fn=on_select_history_item,
            inputs=[history_dropdown],
            outputs=[history_details, history_video_player],
        )

        open_folder_btn.click(
            fn=open_outputs_folder,
            outputs=[folder_status],
        )

        # Восстановление по ID
        recover_btn.click(
            fn=recover_task_status,
            inputs=[task_id_input, api_key_input, proxy_input],
            outputs=[recover_status, recover_video],
            show_progress="full",
        )

        # Запуск генерации: блокировка кнопки -> генерация -> разблокировка кнопки
        btn.click(
            fn=lambda: gr.update(interactive=False, value="⏳ Идет генерация..."),
            outputs=[btn],
            queue=False,
        ).then(
            fn=generate_video_ui,
            inputs=[
                api_key_input,
                proxy_input,
                model_selector,
                user_prompt,
                resolution,
                aspect_ratio,
                duration,
                generate_audio,
                image_inputs,
                video_inputs,
                audio_inputs,
            ],
            outputs=[status_output, video_output],
            show_progress="full",
        ).then(
            fn=lambda: gr.update(interactive=True, value="🚀 Запустить генерацию"),
            outputs=[btn],
            queue=False,
        )

        gr.HTML(
            "<div style='text-align: center; margin-top: 30px; padding: 18px 10px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, \"Liberation Mono\", \"Courier New\", monospace; font-size: 1.15rem; font-weight: 600; letter-spacing: 0.1em; color: #9ca3af; border-top: 1px solid rgba(156, 163, 175, 0.2); text-transform: uppercase;'>"
            "v1.1.0 · by <span style=\"font-weight: 800; color: #6366f1;\">DEDBW</span>"
            "</div>"
        )

    return demo, custom_css, head_script
