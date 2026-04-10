from flask import Flask, render_template, request, send_from_directory, redirect, url_for
import os
import uuid
# 引入核心引擎
from ppt2video_engine import run_generation

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'static', 'outputs')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files: return "错误：未上传文件"
        file = request.files['file']
        if file.filename == '': return "错误：文件名为空"

        if file:
            session_id = str(uuid.uuid4())[:8]
            safe_filename = f"{session_id}_{file.filename}"
            upload_path = os.path.join(UPLOAD_FOLDER, safe_filename)
            file.save(upload_path)

            selected_voice = request.form.get('voice', 'zh-CN-XiaoxiaoNeural')
            # 🆕 获取视频模式参数 (默认 'studio')
            video_mode = request.form.get('video_mode', 'studio')

            # 🆕 处理零样本克隆参数
            prompt_wav_path = None
            prompt_text = request.form.get('prompt_text', '')
            if 'prompt_wav' in request.files:
                prompt_file = request.files['prompt_wav']
                if prompt_file.filename != '':
                    prompt_wav_path = os.path.join(UPLOAD_FOLDER, f"prompt_{session_id}_{prompt_file.filename}")
                    prompt_file.save(prompt_wav_path)

            voice_config = {
                "voice_name": selected_voice,
                "prompt_wav": prompt_wav_path,
                "prompt_text": prompt_text
            }

            output_video_name = f"{session_id}_output.mp4"
            output_video_path = os.path.join(OUTPUT_FOLDER, output_video_name)

            print(f"\n🎬 [Web] 任务: {safe_filename} | 模式: {video_mode} | 音色: {selected_voice}")

            # 🆕 将 voice_config 传递给引擎
            success = run_generation(upload_path, output_video_path, session_id, voice_config, video_mode=video_mode)

            if success:
                return redirect(url_for('preview', filename=output_video_name))
            else:
                return "❌ 生成失败，请查看后台日志。"

    return render_template('index.html')

@app.route('/preview/<filename>')
def preview(filename):
    return render_template('preview.html', filename=filename)

@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    print("🚀 服务启动: https://10.255.1.102:5001")
    app.run(host='0.0.0.0', port=5001, ssl_context='adhoc',debug=True)