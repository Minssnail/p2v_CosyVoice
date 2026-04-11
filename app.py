from flask import Flask, render_template, request, send_from_directory, redirect, url_for, Response, jsonify
import os
import uuid
import threading
import time
import json
# 引入核心引擎
from ppt2video_engine import run_generation, get_progress, clear_progress

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'static', 'outputs')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 存储正在运行的任务 { session_id: { "thread": Thread, "output": filename } }
_tasks = {}

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files: return jsonify({"error": "未上传文件"}), 400
        file = request.files['file']
        if file.filename == '': return jsonify({"error": "文件名为空"}), 400

        if file:
            session_id = str(uuid.uuid4())[:8]
            safe_filename = f"{session_id}_{file.filename}"
            upload_path = os.path.join(UPLOAD_FOLDER, safe_filename)
            file.save(upload_path)

            selected_voice = request.form.get('voice', 'zh-CN-XiaoxiaoNeural')
            video_mode = request.form.get('video_mode', 'studio')

            # 处理零样本克隆参数
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

            # 🆕 在后台线程中运行生成任务
            def _run_task():
                success = run_generation(upload_path, output_video_path, session_id, voice_config, video_mode=video_mode)
                _tasks[session_id]["success"] = success

            t = threading.Thread(target=_run_task, daemon=True)
            _tasks[session_id] = {"thread": t, "output": output_video_name, "success": None}
            t.start()

            # 返回 session_id 给前端，用于轮询进度
            return jsonify({"session_id": session_id})

    return render_template('index.html')


@app.route('/api/progress/<session_id>')
def progress_stream(session_id):
    """SSE 端点：推送实时进度"""
    def event_stream():
        while True:
            prog = get_progress(session_id)
            task = _tasks.get(session_id, {})

            # 如果任务已完成，附带结果信息
            if prog.get("done"):
                if prog.get("success") and task.get("output"):
                    prog["redirect"] = f"/preview/{task['output']}"
                yield f"data: {json.dumps(prog, ensure_ascii=False)}\n\n"
                # 清理
                clear_progress(session_id)
                break

            yield f"data: {json.dumps(prog, ensure_ascii=False)}\n\n"
            time.sleep(0.8)

    return Response(event_stream(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/preview/<filename>')
def preview(filename):
    return render_template('preview.html', filename=filename)

@app.route('/download/<filename>')
def download(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    print("🚀 服务启动: https://10.255.1.102:5001")
    app.run(host='0.0.0.0', port=5001, ssl_context='adhoc',debug=True)