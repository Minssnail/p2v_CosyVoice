from flask import Flask, render_template, request, send_from_directory, redirect, url_for, Response, jsonify, session
from functools import wraps
import os
import uuid
import threading
import time
import json
import requests

# 引入核心引擎
from ppt2video_engine import run_generation, get_progress, clear_progress, COSYVOICE_API_URLS
import db

app = Flask(__name__)
app.secret_key = 'p2v_cosyvoice_2026_secret'  # 固定密钥，重启不丢失 session

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'static', 'outputs')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 存储正在运行的任务
_tasks = {}


# ─── 登录装饰器 ───

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def current_user():
    """获取当前登录用户"""
    uid = session.get('user_id')
    if uid:
        return db.get_user_by_id(uid)
    return None


# ─── 认证路由 ───

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = db.verify_user(username, password)
        if user:
            session['user_id'] = user['id']
            session['display_name'] = user['display_name'] or user['username']
            return redirect(url_for('index'))
        return render_template('login.html', error='用户名或密码错误', tab='login')
    return render_template('login.html')


@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    display_name = request.form.get('display_name', '').strip()
    if len(username) < 2:
        return render_template('login.html', error='用户名至少2个字符', tab='register')
    if len(password) < 4:
        return render_template('login.html', error='密码至少4个字符', tab='register')
    try:
        user = db.create_user(username, password, display_name)
        return render_template('login.html', success='注册成功，请登录', tab='login')
    except ValueError as e:
        return render_template('login.html', error=str(e), tab='register')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ─── 音色管理 API ───

@app.route('/api/voices', methods=['GET'])
@login_required
def list_voices():
    """获取当前用户的音色列表"""
    voices = db.get_user_voices(session['user_id'])
    return jsonify({"voices": voices})


@app.route('/api/voices/create', methods=['POST'])
@login_required
def create_voice():
    """创建新音色：上传 prompt_wav → 注册到所有 CosyVoice 实例 → 写数据库"""
    voice_name = request.form.get('voice_name', '').strip()
    prompt_text = request.form.get('prompt_text', '').strip()

    if not voice_name:
        return jsonify({"error": "请输入音色名称"}), 400
    if not prompt_text:
        return jsonify({"error": "请输入参考音频中的原话"}), 400
    if 'prompt_wav' not in request.files:
        return jsonify({"error": "请上传参考录音"}), 400

    prompt_file = request.files['prompt_wav']
    if prompt_file.filename == '':
        return jsonify({"error": "请选择录音文件"}), 400

    user_id = session['user_id']
    speaker_id = db.make_speaker_id(user_id, voice_name)

    # 保存 prompt_wav 到 uploads
    prompt_path = os.path.join(UPLOAD_FOLDER, f"voice_{speaker_id}_{prompt_file.filename}")
    prompt_file.save(prompt_path)

    # 注册到所有 CosyVoice 实例
    success_count = 0
    for api_url in COSYVOICE_API_URLS:
        try:
            with open(prompt_path, 'rb') as f:
                r = requests.post(
                    f"{api_url}/api/speakers/register",
                    data={"speaker_id": speaker_id, "prompt_text": prompt_text},
                    files={"prompt_wav": (os.path.basename(prompt_path), f, "audio/wav")},
                    timeout=60
                )
                r.raise_for_status()
            success_count += 1
        except Exception as e:
            print(f"⚠️ [Voice] 注册到 {api_url} 失败: {e}")

    if success_count == 0:
        return jsonify({"error": "音色注册失败，语音服务不可用"}), 500

    # 写数据库
    try:
        voice = db.add_voice(user_id, voice_name, speaker_id, prompt_text)
        print(f"✅ [Voice] 用户 {user_id} 创建音色: {voice_name} → {speaker_id} ({success_count} 实例)")
        return jsonify({"message": f"音色「{voice_name}」创建成功", "voice": voice})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/voices/delete', methods=['POST'])
@login_required
def delete_voice():
    """删除音色"""
    voice_id = request.form.get('voice_id', type=int)
    if not voice_id:
        return jsonify({"error": "缺少 voice_id"}), 400

    speaker_id = db.delete_voice(session['user_id'], voice_id)
    if not speaker_id:
        return jsonify({"error": "音色不存在或无权删除"}), 404

    # 从所有 CosyVoice 实例删除
    for api_url in COSYVOICE_API_URLS:
        try:
            requests.delete(f"{api_url}/api/speakers/{speaker_id}", timeout=10)
        except:
            pass

    print(f"🗑️ [Voice] 用户 {session['user_id']} 删除音色: {speaker_id}")
    return jsonify({"message": "已删除"})


# ─── 主页面 ───

@app.route('/', methods=['GET', 'POST'])
@login_required
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

            selected_voice = request.form.get('voice', '')
            video_mode = request.form.get('video_mode', 'studio')

            # 判断音色类型
            user_id = session['user_id']
            prompt_wav_path = None
            prompt_text = ''

            if selected_voice.startswith('u'):
                # 用户自定义音色，验证所有权
                voice_info = db.get_voice_by_speaker_id(user_id, selected_voice)
                if not voice_info:
                    return jsonify({"error": "音色不存在或无权使用"}), 403
                # 使用已注册的 speaker_id，设为 zero_shot 模式
                voice_config = {
                    "voice_name": "zero_shot",
                    "prompt_wav": None,
                    "prompt_text": "",
                    "registered_speaker_id": selected_voice  # 直接传 speaker_id
                }
            elif selected_voice == 'zero_shot':
                # 临时零样本模式（上传新音频）
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
            else:
                voice_config = {
                    "voice_name": selected_voice,
                    "prompt_wav": None,
                    "prompt_text": ""
                }

            output_video_name = f"{session_id}_output.mp4"
            output_video_path = os.path.join(OUTPUT_FOLDER, output_video_name)

            print(f"\n🎬 [Web] 用户: {session.get('display_name')} | 任务: {safe_filename} | 音色: {selected_voice}")

            def _run_task():
                success = run_generation(upload_path, output_video_path, session_id, voice_config, video_mode=video_mode)
                _tasks[session_id]["success"] = success

            t = threading.Thread(target=_run_task, daemon=True)
            _tasks[session_id] = {"thread": t, "output": output_video_name, "success": None}
            t.start()

            return jsonify({"session_id": session_id})

    user = current_user()
    voices = db.get_user_voices(session['user_id'])
    return render_template('index.html', user=user, voices=voices)


@app.route('/api/progress/<session_id>')
def progress_stream(session_id):
    """SSE 端点：推送实时进度"""
    def event_stream():
        while True:
            prog = get_progress(session_id)
            task = _tasks.get(session_id, {})

            if prog.get("done"):
                if prog.get("success") and task.get("output"):
                    prog["redirect"] = f"/preview/{task['output']}"
                yield f"data: {json.dumps(prog, ensure_ascii=False)}\n\n"
                if prog.get("done"):
                    clear_progress(session_id)
                    break

            yield f"data: {json.dumps(prog, ensure_ascii=False)}\n\n"
            time.sleep(0.8)

    return Response(event_stream(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/preview/<filename>')
@login_required
def preview(filename):
    return render_template('preview.html', filename=filename)

@app.route('/download/<filename>')
@login_required
def download(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    print("🚀 服务启动: https://10.255.1.102:5001")
    app.run(host='0.0.0.0', port=5001, ssl_context='adhoc', debug=True)