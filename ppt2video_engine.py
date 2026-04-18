import os
# --- 🟢 网络修复 ---
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

import asyncio
import subprocess
import win32com.client
import pythoncom
import shutil
import random
import json
import requests
import edge_tts
import threading
import time as _time
from pptx import Presentation 

try:
    import azure.cognitiveservices.speech as speechsdk
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

# ================= ⚙️ 引擎配置 =================
TTS_PROVIDER = "cosyvoice"  # 默认使用 cosyvoice
AZURE_SPEECH_KEY = "f9584ff6c39b43ef991a67435fbbb31a"
AZURE_SPEECH_REGION = "eastus"
# 🆕 多实例自动发现：扫描端口范围，找到所有活跃的 CosyVoice 实例
COSYVOICE_HOST = "10.255.1.115"
COSYVOICE_PORT_RANGE = (9880, 9899)  # 扫描端口范围

def _discover_cosyvoice_instances():
    """自动探测所有活跃的 CosyVoice API 实例"""
    import socket
    alive = []
    for port in range(COSYVOICE_PORT_RANGE[0], COSYVOICE_PORT_RANGE[1] + 1):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            s.connect((COSYVOICE_HOST, port))
            s.close()
            alive.append(f"http://{COSYVOICE_HOST}:{port}")
        except:
            pass
    if not alive:
        # 回退到默认端口
        alive = [f"http://{COSYVOICE_HOST}:9880"]
        print(f"⚠️ [Discovery] 未发现活跃实例，回退到默认端口 9880")
    else:
        print(f"🔍 [Discovery] 发现 {len(alive)} 个 CosyVoice 实例: {[u.split(':')[-1] for u in alive]}")
    return alive

# 启动时首次探测
COSYVOICE_API_URLS = _discover_cosyvoice_instances()
MAX_TTS_CONCURRENT = len(COSYVOICE_API_URLS)  # 并发数 = 实例数

MAX_RENDER_CONCURRENT = 8

# 背景图路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKGROUND_IMAGE_PATH = os.path.join(BASE_DIR, 'static', 'assets', 'bg_tech.png')

# 🎯 精准屏幕布局 (用户手工测量数据)
SCREEN_LAYOUT = {
    "x": 38, "y": 66, "w": 990, "h": 558
}

# ─── 进度管理 ────────────────────────────────────
# { session_id: { "stage": str, "current": int, "total": int, "detail": str, "done": bool, "success": bool } }
_progress_store = {}
_progress_lock = threading.Lock()

def update_progress(session_id, stage, current=0, total=0, detail="", done=False, success=True):
    """更新某个 session 的进度"""
    with _progress_lock:
        _progress_store[session_id] = {
            "stage": stage,
            "current": current,
            "total": total,
            "detail": detail,
            "done": done,
            "success": success,
        }

def get_progress(session_id):
    """获取某个 session 的当前进度"""
    with _progress_lock:
        return _progress_store.get(session_id, {
            "stage": "waiting", "current": 0, "total": 0,
            "detail": "等待中...", "done": False, "success": True
        }).copy()

def clear_progress(session_id):
    """清理已完成的进度"""
    with _progress_lock:
        _progress_store.pop(session_id, None)

# ===============================================

def cleanup_folder(folder):
    if os.path.exists(folder): shutil.rmtree(folder, ignore_errors=True)

def ppt_to_images(pptx_path, output_dir):
    pptx_abs_path = os.path.abspath(pptx_path)
    output_abs_dir = os.path.abspath(output_dir)
    if not os.path.exists(output_abs_dir): os.makedirs(output_abs_dir)
    pythoncom.CoInitialize()
    powerpoint = None
    try:
        powerpoint = win32com.client.Dispatch("PowerPoint.Application")
        presentation = powerpoint.Presentations.Open(pptx_abs_path, ReadOnly=True, WithWindow=False)
        for i, slide in enumerate(presentation.Slides):
            image_filename = os.path.join(output_abs_dir, f"{i+1}.png")
            slide.Export(image_filename, "PNG", 1920, 1080)
        presentation.Close()
        return True
    except Exception: return False
    finally:
        if powerpoint:
            try: powerpoint.Quit()
            except: pass
        pythoncom.CoUninitialize()

async def _generate_edge(text, output_file, voice_name):
    await asyncio.sleep(random.uniform(0.5, 2.0))
    for attempt in range(5): 
        try:
            communicate = edge_tts.Communicate(text, voice_name)
            await communicate.save(output_file)
            return True
        except: await asyncio.sleep(2)
    return False

async def _generate_azure(text, output_file, voice_name):
    if not AZURE_AVAILABLE: return False
    def _sync_task():
        try:
            speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
            speech_config.speech_synthesis_voice_name = voice_name
            speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
            audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)
            synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
            return synthesizer.speak_text_async(text).get().reason == speechsdk.ResultReason.SynthesizingAudioCompleted
        except: return False
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_task)

def _register_zero_shot_speaker(session_id, prompt_wav, prompt_text):
    """在所有 CosyVoice 实例上预注册零样本音色"""
    speaker_id = f"p2v_{session_id}"
    success_count = 0
    for api_url in COSYVOICE_API_URLS:
        url = f"{api_url}/api/speakers/register"
        try:
            with open(prompt_wav, "rb") as f:
                r = requests.post(url, data={
                    "speaker_id": speaker_id,
                    "prompt_text": prompt_text
                }, files={"prompt_wav": (os.path.basename(prompt_wav), f, "audio/wav")}, timeout=60)
                r.raise_for_status()
            success_count += 1
        except Exception as e:
            print(f"⚠️ [CosyVoice] 注册到 {api_url} 失败: {e}")
    if success_count > 0:
        print(f"✅ [CosyVoice] 音色预注册成功: {speaker_id} → {success_count}/{len(COSYVOICE_API_URLS)} 个实例")
        return speaker_id
    else:
        print(f"⚠️ [CosyVoice] 所有实例注册失败，回退到逐页上传模式")
        return None

def _unregister_speaker(speaker_id):
    """清理所有实例上已注册的临时音色"""
    for api_url in COSYVOICE_API_URLS:
        try:
            requests.delete(f"{api_url}/api/speakers/{speaker_id}", timeout=10)
        except:
            pass

async def _generate_cosyvoice(text, output_file, voice_name, prompt_wav=None, prompt_text="",
                               registered_spk_id=None, api_url=None):
    """
    调用 CosyVoice API 生成语音
    - api_url: 指定目标实例的 URL（多实例负载均衡）
    """
    base_url = api_url or COSYVOICE_API_URLS[0]
    url = f"{base_url}/api/tts/sft"
    data = {"tts_text": text, "speed": 1.0}
    files = {}

    if registered_spk_id:
        url = f"{base_url}/api/tts/zero_shot"
        data["speaker_id"] = registered_spk_id
    elif voice_name == "zero_shot" and prompt_wav:
        url = f"{base_url}/api/tts/zero_shot"
        data["prompt_text"] = prompt_text
        files["prompt_wav"] = (os.path.basename(prompt_wav), open(prompt_wav, "rb"), "audio/wav")
    else:
        data["speaker_id"] = voice_name

    def _sync_request():
        try:
            r = requests.post(url, data=data, files=files if files else None, timeout=120)
            r.raise_for_status()
            with open(output_file, "wb") as f:
                f.write(r.content)
            return True
        except Exception as e:
            print(f"❌ [CosyVoice Error] {base_url} → {e}")
            return False
        finally:
            if "prompt_wav" in files:
                files["prompt_wav"][1].close()

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_request)

async def text_to_speech_wrapper(text, output_file, semaphore, voice_name,
                                  prompt_wav=None, prompt_text="",
                                  registered_spk_id=None, api_url=None):
    async with semaphore:
        if not text.strip(): return True
        t0 = _time.time()
        if TTS_PROVIDER == "cosyvoice":
            result = await _generate_cosyvoice(text, output_file, voice_name,
                                               prompt_wav, prompt_text,
                                               registered_spk_id, api_url)
        elif TTS_PROVIDER == "azure":
            result = await _generate_azure(text, output_file, voice_name)
        else:
            result = await _generate_edge(text, output_file, voice_name)
        elapsed = _time.time() - t0
        server_tag = api_url.split(':')[-1] if api_url else ''
        status = "✅" if result else "❌"
        print(f"  {status} [TTS] {os.path.basename(output_file)} | {elapsed:.1f}s | {len(text)}字 | :{server_tag}")
        return result

async def create_silent_audio(duration, output_path):
    if os.path.exists(output_path): return
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(duration), "-c:a", "libmp3lame", "-q:a", "4", output_path]
    subprocess.run(cmd, check=True)

def get_audio_duration(audio_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", audio_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(json.loads(result.stdout)['format']['duration'])
    except: return 3.0

def build_random_filter(duration):
    if duration < 2.0: return f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration-0.5}:d=0.5", "Fade"
    effects = ["fade", "blur"]
    chosen = random.choice(effects)
    if chosen == "fade": vf = f"fade=t=in:st=0:d=0.5,fade=t=out:st={duration-0.5}:d=0.5"
    else: vf = f"boxblur=luma_radius=20:luma_power=1:enable='between(t,0,0.5)+between(t,{duration-0.5},{duration})',fade=t=in:st=0:d=0.5,fade=t=out:st={duration-0.5}:d=0.5"
    return vf, chosen

# --- 4. 渲染单页 (支持多模式) ---
async def render_slide_video(img_path, audio_path, output_video_path, video_mode="studio", effect_override=None):
    if os.path.exists(output_video_path): os.remove(output_video_path)
    duration = get_audio_duration(audio_path)
    raw_effect_filter, _ = build_random_filter(duration)

    cmd = []
    
    # 🌟 模式一：演播室模式 (叠加背景)
    if video_mode == "studio":
        if not os.path.exists(BACKGROUND_IMAGE_PATH): return None
        w, h = SCREEN_LAYOUT['w'], SCREEN_LAYOUT['h']
        x, y = SCREEN_LAYOUT['x'], SCREEN_LAYOUT['y']
        
        # 复杂滤镜链
        filter_complex = (
            f"[1:v]scale={w}:{h},setsar=1,{raw_effect_filter}[ppt];"
            f"[0:v][ppt]overlay=x={x}:y={y}:shortest=1[outv]"
        )
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-i", BACKGROUND_IMAGE_PATH,
            "-loop", "1", "-i", img_path,
            "-i", audio_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "2:a",
            "-c:v", "h264_nvenc", "-preset", "p1", "-r", "24", "-pix_fmt", "yuv420p", "-shortest",
            output_video_path
        ]
        
    # 🌟 模式二：默认模式 (全屏PPT，无背景)
    else:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-i", img_path, # 只有一个视频输入
            "-i", audio_path,
            "-vf", raw_effect_filter,     # 直接应用转场滤镜
            "-c:v", "h264_nvenc", "-preset", "p1", "-r", "24", "-pix_fmt", "yuv420p", "-shortest",
            output_video_path
        ]

    try:
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        # 使用 communicate() 读取输出，防止缓冲区填满导致的死锁 (假死)
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            print(f"⚠️ [FFmpeg Error] {stderr.decode()}")
            return None
            
        return output_video_path
    except Exception as e:
        print(f"❌ [Render Error] {e}")
        return None

# --- 主任务 (带进度回调) ---
async def generate_video_task(ppt_path, output_video_path, temp_dir, voice_name, video_mode, session_id):
    global COSYVOICE_API_URLS, MAX_TTS_CONCURRENT
    total_slides = 0

    # 🔄 每次任务开始时重新探测实例（动态扩缩容）
    COSYVOICE_API_URLS = _discover_cosyvoice_instances()
    MAX_TTS_CONCURRENT = len(COSYVOICE_API_URLS)


    # ── 阶段 1：解析 PPT ──
    update_progress(session_id, "parse", 0, 0, "正在解析 PPT 提取幻灯片...")
    img_dir, vid_dir = os.path.join(temp_dir, "images"), os.path.join(temp_dir, "videos")
    if not os.path.exists(vid_dir): os.makedirs(vid_dir)
    if not ppt_to_images(ppt_path, img_dir):
        update_progress(session_id, "error", done=True, success=False, detail="PPT 解析失败")
        return False

    prs = Presentation(ppt_path)
    tts_tasks, slides_data = [], []
    tts_semaphore = asyncio.Semaphore(MAX_TTS_CONCURRENT)

    # 提取零样本克隆参数
    prompt_wav = voice_name.get("prompt_wav") if isinstance(voice_name, dict) else None
    prompt_text = voice_name.get("prompt_text", "") if isinstance(voice_name, dict) else ""
    real_voice_name = voice_name.get("voice_name", "中文女") if isinstance(voice_name, dict) else voice_name

    # 🚀 预注册零样本音色（一次提取特征，后续所有页复用）
    registered_spk_id = None
    if real_voice_name == "zero_shot" and prompt_wav:
        update_progress(session_id, "parse", 0, 0, "正在预注册教师音色...")
        registered_spk_id = _register_zero_shot_speaker(session_id, prompt_wav, prompt_text)

    print(f"🚀 [Engine] 开始处理 | 模式: {video_mode} | 音色: {real_voice_name}" +
          (f" | 预注册: {registered_spk_id}" if registered_spk_id else ""))

    for i, slide in enumerate(prs.slides):
        idx = i + 1
        notes = slide.notes_slide.notes_text_frame.text if slide.has_notes_slide and slide.notes_slide.notes_text_frame else ""
        notes = notes.replace('\n', '，').strip()
        img, aud, vid = os.path.join(img_dir, f"{idx}.png"), os.path.join(temp_dir, f"audio_{idx}.mp3"), os.path.join(vid_dir, f"seg_{idx}.mp4")
        if not os.path.exists(img): continue
        slides_data.append({"img": img, "aud": aud, "vid": vid, "notes": notes})
        if not notes:
            await create_silent_audio(3, aud)

    total_slides = len(slides_data)
    update_progress(session_id, "parse", total_slides, total_slides, f"解析完毕, 共 {total_slides} 页幻灯片")

    # ── 阶段 2：语音合成 ──
    tts_done = 0
    tts_total_start = _time.time()
    num_servers = len(COSYVOICE_API_URLS)

    # 收集需要合成的页面
    tts_items = [(i, d) for i, d in enumerate(slides_data) if d["notes"]]
    tts_need = len(tts_items)

    if tts_items:
        update_progress(session_id, "tts", 0, total_slides,
                        f"正在合成语音，共 {tts_need} 页...")

        tts_failed = []  # 记录失败的页

        async def _do_tts(idx, d, server_idx):
            nonlocal tts_done
            api_url = COSYVOICE_API_URLS[server_idx % num_servers]
            result = await text_to_speech_wrapper(
                d["notes"], d["aud"], tts_semaphore,
                real_voice_name, prompt_wav, prompt_text,
                registered_spk_id=registered_spk_id,
                api_url=api_url
            )
            if result:
                tts_done += 1
                update_progress(session_id, "tts", tts_done, total_slides,
                                f"已完成 {tts_done}/{tts_need} 页语音合成")
            else:
                tts_failed.append(idx + 1)
            return result

        # 并行合成，每完成一页就更新进度
        tts_coros = [_do_tts(idx, d, i) for i, (idx, d) in enumerate(tts_items)]
        await asyncio.gather(*tts_coros)

        if tts_failed:
            update_progress(session_id, "error", done=True, success=False,
                            detail=f"第 {tts_failed[0]} 页语音合成失败")
            if registered_spk_id: _unregister_speaker(registered_spk_id)
            return False

        update_progress(session_id, "tts", total_slides, total_slides,
                        f"全部 {tts_need} 页语音合成完成")
    else:
        tts_done = total_slides


    tts_total_elapsed = _time.time() - tts_total_start
    print(f"⏱️ [TTS 总耗时] {tts_total_elapsed:.1f}s | {len(tts_items)} 页 | {num_servers} 实例并行 | 平均 {tts_total_elapsed/max(len(tts_items),1):.1f}s/页")

    # ── 阶段 3：视频渲染 ──
    render_done = 0
    render_sem = asyncio.Semaphore(MAX_RENDER_CONCURRENT)

    async def do_render(idx, d):
        nonlocal render_done
        async with render_sem:
            if not os.path.exists(d['aud']): return None
            result = await render_slide_video(d['img'], d['aud'], d['vid'], video_mode=video_mode)
            render_done += 1
            update_progress(session_id, "render", render_done, total_slides,
                            f"已渲染 {render_done}/{total_slides} 页视频")
            return result

    update_progress(session_id, "render", 0, total_slides, "正在渲染视频片段...")
    render_tasks = [do_render(i, d) for i, d in enumerate(slides_data)]
    valid_vids = [v for v in await asyncio.gather(*render_tasks) if v]
    if not valid_vids:
        update_progress(session_id, "error", done=True, success=False, detail="视频渲染失败")
        return False

    # ── 阶段 4：合并输出 ──
    update_progress(session_id, "merge", 0, 1, "正在合并视频片段为最终文件...")
    list_path = os.path.join(temp_dir, "list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for v in valid_vids: f.write(f"file '{os.path.abspath(v).replace(os.sep, '/')}'\n")

    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_video_path])
    cleanup_folder(temp_dir)
    # 清理预注册的临时音色
    if registered_spk_id: _unregister_speaker(registered_spk_id)
    print(f"✅ 完成: {output_video_path}")

    update_progress(session_id, "done", 1, 1, "视频生成完成！", done=True, success=True)
    return True

# 🆕 添加入口参数 video_mode
def run_generation(ppt_path, output_path, session_id, voice_name, video_mode="studio", effect_type="random"):
    temp_dir = os.path.join(os.path.dirname(output_path), f"temp_{session_id}")
    update_progress(session_id, "init", 0, 0, "任务已提交，正在初始化...")
    try:
        asyncio.run(generate_video_task(ppt_path, output_path, temp_dir, voice_name, video_mode, session_id))
        return True
    except Exception as e:
        print(f"❌ 错误: {e}")
        update_progress(session_id, "error", done=True, success=False, detail=f"系统错误: {e}")
        cleanup_folder(temp_dir)
        return False