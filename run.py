from waitress import serve
from app import app
import ctypes
import sys

def disable_quick_edit():
    """
    禁用 Windows 控制台的“快速编辑模式” (Quick Edit Mode)。
    该模式下，鼠标点击控制台会导致程序挂起 (假死)，直到按下回车键。
    """
    if sys.platform != "win32":
        return

    try:
        kernel32 = ctypes.windll.kernel32
        hStdIn = kernel32.GetStdHandle(-10) # STD_INPUT_HANDLE
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(hStdIn, ctypes.byref(mode)):
            return
            
        # ENABLE_QUICK_EDIT_MODE = 0x0040
        # ENABLE_INSERT_MODE = 0x0020
        # ENABLE_MOUSE_INPUT = 0x0010
        # ENABLE_EXTENDED_FLAGS = 0x0080
        
        # 移除快速编辑模式和插入模式
        new_mode = mode.value
        new_mode &= ~0x0040 # 禁用快速编辑
        new_mode &= ~0x0020 # 禁用插入模式
        # new_mode |= 0x0080  # 确保扩展标志被设置 (通常需要)

        kernel32.SetConsoleMode(hStdIn, new_mode)
        print("✅ [System] 已禁用 Windows 控制台快速编辑模式，防止点击挂起。")
    except Exception as e:
        print(f"⚠️ [System] 无法禁用快速编辑模式: {e}")

if __name__ == '__main__':
    disable_quick_edit()
    print("--- 正在启动生产级Waitress服务器 ---")
    print("--- 服务器运行在 http://0.0.0.0:5001 ---")
    print("--- 现在可以通过浏览器访问 ---")
    serve(app, host='0.0.0.0', port=5001)