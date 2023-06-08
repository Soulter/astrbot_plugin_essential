import requests
import random
from nakuru.entities.components import *

def get_moe(message_obj, busy):
    if message_obj.sender.user_id in busy and busy[message_obj.sender.user_id]:
        return True, tuple([True, "有一个服务于你的任务正在执行，请稍等。", "moe"])
    else:
        busy[message_obj.sender.user_id] = True
    """
    QQ平台指令处理逻辑
    """
    urls = ["https://t.mwm.moe/pc/",
            "https://t.lizi.moe/mp",
            "https://t.lizi.moe/fj",]
    
    resp = requests.get(random.choice(urls))
    if resp.status_code == 200:
        # 保存图片到本地
        try:
            with open("moe.jpg", "wb") as f:
                f.write(resp.content)
            # 发送图片
            busy[message_obj.sender.user_id] = False
            return True, tuple([True, [Image.fromFileSystem("moe.jpg")], "moe"])
        except Exception as e:
            busy[message_obj.sender.user_id] = False
            return True, tuple([False, f"获取图片失败: {str(e)}", "moe"])
    else:
        busy[message_obj.sender.user_id] = False
        return True, tuple([False, "获取图片失败", "moe"])