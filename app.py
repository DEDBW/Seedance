import gradio as gr
from src.ui import create_ui

demo, custom_css, head_script = create_ui()

if __name__ == "__main__":
    demo.queue().launch(
        inbrowser=True,
        show_error=True,
        theme=gr.themes.Soft(),
        css=custom_css,
        head=head_script,
    )