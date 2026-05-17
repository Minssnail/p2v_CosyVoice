# -*- coding: utf-8 -*-
"""
本地敏感配置模板 — 请复制为 config_local.py 并填写实际值
    cp config_local.example.py config_local.py
"""

# ─── Flask ───
FLASK_SECRET_KEY = "请替换为随机字符串"

# ─── Azure Speech（备选 TTS，不使用可留空） ───
AZURE_SPEECH_KEY = ""
AZURE_SPEECH_REGION = "eastus"

# ─── CosyVoice 服务器集群 ───
COSYVOICE_SERVERS = [
    {"host": "YOUR_GPU_SERVER_IP", "port_range": (9880, 9888)},
    # 可添加更多服务器:
    # {"host": "ANOTHER_SERVER_IP", "port_range": (50050, 50055)},
]
