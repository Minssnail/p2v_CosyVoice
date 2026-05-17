from flask import Flask, render_template, request, send_from_directory, redirect, url_for, Response, jsonify, session
from functools import wraps
import os
import uuid
import threading
import time
import json
import requests
import subprocess

# 引入核心引擎
from ppt2video_engine import run_generation, get_progress, clear_progress, _discover_cosyvoice_instances_tcp_only
import db

def _get_live_instances():
    """获取当前活跃的 CosyVoice 实例（同步版本，用于音色管理）"""
    urls = _discover_cosyvoice_instances_tcp_only()
    if not urls:
        print("[WARN] 未发现任何 CosyVoice 实例")
    return urls

app = Flask(__name__)
# 从本地配置读取密钥（config_local.py 不纳入版本控制）
try:
    from config_local import FLASK_SECRET_KEY
    app.secret_key = FLASK_SECRET_KEY
except ImportError:
    app.secret_key = os.urandom(24).hex()
    print("[WARN] 未找到 config_local.py，使用随机 secret_key（重启后 session 会失效）")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'static', 'outputs')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# 存储正在运行的任务
_tasks = {}


# ─── 音频处理工具 ───

def convert_to_wav(input_path, output_path=None):
    """
    将音频文件转换为WAV格式（CosyVoice要求）
    支持: m4a, mp3, ogg, etc. → WAV (16kHz, mono)
    """
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        # 始终用不同文件名，避免 FFmpeg "Output same as Input" 错误
        output_path = f"{base}_std.wav"

    # 如果已经是WAV，检查格式
    if input_path.lower().endswith('.wav'):
        # 验证是否为标准格式
        try:
            probe_cmd = ["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_name,sample_rate,channels",
                        "-of", "json", input_path]
            result = subprocess.run(probe_cmd, capture_output=True, text=True, encoding="utf-8", timeout=5)
            if result.returncode == 0:
                import json
                info = json.loads(result.stdout)
                if info.get('streams'):
                    stream = info['streams'][0]
                    # 如果已经是16kHz单声道WAV，直接返回
                    if (stream.get('codec_name') == 'pcm_s16le' and
                        stream.get('sample_rate') == '16000' and
                        stream.get('channels') == 1):
                        return input_path
        except:
            pass

    # 执行格式转换
    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", input_path,
            "-ar", "16000",           # 采样率 16kHz
            "-ac", "1",                # 单声道
            "-c:a", "pcm_s16le",       # PCM 16-bit
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        return output_path
    except subprocess.TimeoutExpired:
        raise ValueError("音频转换超时，请尝试更短的音频")
    except subprocess.CalledProcessError as e:
        raise ValueError(f"音频转换失败: {e.stderr.decode('utf-8') if e.stderr else '未知错误'}")
    except Exception as e:
        raise ValueError(f"音频处理错误: {str(e)}")


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


@app.route('/api/account/delete', methods=['POST'])
@login_required
def delete_account():
    """注销账号：验证密码后删除用户及其所有音色数据"""
    password = request.form.get('password', '')
    if not password:
        return jsonify({"error": "请输入密码以确认注销"}), 400

    user_id = session['user_id']
    result = db.delete_user(user_id, password)
    if not result:
        return jsonify({"error": "密码错误，注销失败"}), 403

    # 清理 CosyVoice 实例上的音色
    speaker_ids = result.get('speaker_ids', [])
    live_urls = _get_live_instances()
    for speaker_id in speaker_ids:
        for api_url in live_urls:
            try:
                requests.delete(f"{api_url}/api/speakers/{speaker_id}", timeout=10)
            except:
                pass
        # 清理归档的音频文件
        for suffix in ['_std.wav', '_orig.wav', '_orig.mp3', '_orig.m4a']:
            fpath = os.path.join(UPLOAD_FOLDER, f"voice_{speaker_id}{suffix}")
            if os.path.exists(fpath):
                os.remove(fpath)

    username = result['user']['username']
    print(f"[DELETE] [Account] 用户 {username} (ID:{user_id}) 已注销，清理了 {len(speaker_ids)} 个音色")

    # 清除 session
    session.clear()
    return jsonify({"message": "账号已注销"})


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

    # 保存原始上传文件
    temp_path = os.path.join(UPLOAD_FOLDER, f"voice_{speaker_id}_orig{os.path.splitext(prompt_file.filename)[1]}")
    prompt_file.save(temp_path)

    # 转换为标准WAV格式（CosyVoice要求）
    try:
        prompt_path = convert_to_wav(temp_path)
        print(f"[CONVERT] [Audio] 音频已转换: {os.path.basename(temp_path)} → {os.path.basename(prompt_path)}")
    except ValueError as e:
        # 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": f"音频处理失败: {str(e)}"}), 500

    # 清理原始文件（如果转换后产生新文件）
    if prompt_path != temp_path and os.path.exists(temp_path):
        os.remove(temp_path)

    # 注册到所有 CosyVoice 实例
    success_count = 0
    errors = []
    live_urls = _get_live_instances()
    if not live_urls:
        if os.path.exists(prompt_path): os.remove(prompt_path)
        return jsonify({"error": "音色注册失败：未发现任何 CosyVoice 实例，请确认语音服务已启动"}), 500
    for api_url in live_urls:
        try:
            with open(prompt_path, 'rb') as f:
                # 1. 增加超时时间：60秒 → 120秒
                r = requests.post(
                    f"{api_url}/api/speakers/register",
                    data={"speaker_id": speaker_id, "prompt_text": prompt_text},
                    files={"prompt_wav": (os.path.basename(prompt_path), f, "audio/wav")},
                    timeout=120
                )
                r.raise_for_status()
            success_count += 1
            print(f"[OK] [Voice] 成功注册到 {api_url}")
        except requests.exceptions.Timeout:
            err = f"{api_url} 请求超时（可能音频文件过大）"
            errors.append(err)
            print(f"[TIMEOUT] [Voice] {err}")
        except requests.exceptions.ConnectionError as e:
            err = f"{api_url} 连接失败"
            errors.append(err)
            print(f"[ERROR] [Voice] {err}: {str(e)[:100]}")
        except requests.exceptions.HTTPError as e:
            err = f"{api_url} 返回错误: {e.response.status_code}"
            errors.append(err)
            print(f"[HTTP_ERROR] [Voice] {err} - {e.response.text[:200]}")
        except Exception as e:
            err = f"{api_url} 未知错误"
            errors.append(err)
            print(f"[ERROR] [Voice] {err}: {str(e)[:100]}")

    if success_count == 0:
        # 清理已转换的WAV文件
        if os.path.exists(prompt_path):
            os.remove(prompt_path)
        error_msg = f"音色注册失败，语音服务不可用。\n详情: {'; '.join(errors)}"
        return jsonify({"error": error_msg}), 500

    # ✅ 保存标准WAV文件用于未来重注册（归档）
    archived_wav_path = os.path.join(UPLOAD_FOLDER, f"voice_{speaker_id}_std.wav")
    try:
        import shutil
        shutil.copy2(prompt_path, archived_wav_path)
        print(f"[ARCHIVE] 标准WAV已归档: {os.path.basename(archived_wav_path)}")
    except Exception as e:
        print(f"[WARN] 归档标准WAV失败: {e}")

    # 清理临时转换文件
    if prompt_path != temp_path and os.path.exists(prompt_path):
        os.remove(prompt_path)

    # 写数据库
    try:
        voice = db.add_voice(user_id, voice_name, speaker_id, prompt_text)
        print(f"[OK] [Voice] 用户 {user_id} 创建音色: {voice_name} → {speaker_id} ({success_count} 实例)")
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
    for api_url in _get_live_instances():
        try:
            requests.delete(f"{api_url}/api/speakers/{speaker_id}", timeout=10)
        except:
            pass

    print(f"[DELETE] [Voice] 用户 {session['user_id']} 删除音色: {speaker_id}")
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

            print(f"\n[VIDEO] [Web] 用户: {session.get('display_name')} | 任务: {safe_filename} | 音色: {selected_voice}")

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
    print("[START] 服务启动: http://0.0.0.0:5001")
    app.run(host='0.0.0.0', port=5001, debug=True)