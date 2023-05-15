from nakuru.entities.components import *
from nakuru import (
    GroupMessage,
    FriendMessage
)
from botpy.message import Message, DirectMessage
import random
import requests

class GoodPluginsPlugin:
    """
    初始化函数, 可以选择直接pass
    """
    def __init__(self) -> None:
        pass

    def run(self, message: str, role: str, platform: str, message_obj, qq_platform):
        if message == "moe" or message == "动漫图片":

            if platform == "gocq":
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
                        return True, tuple([True, [Image.fromFileSystem("moe.jpg")], "moe"])
                    except Exception as e:
                        return True, tuple([False, f"获取图片失败: {str(e)}", "moe"])
                else:
                    return True, tuple([False, "获取图片失败", "moe"])
            elif platform == "qqchan":
                """
                频道处理逻辑(频道暂时只支持回复字符串类型的信息，返回的信息都会被转成字符串，如果不想处理某一个平台的信息，直接返回False, None就行)
                """
                return True, tuple([True, "QQ频道暂时无法使用此插件，本机器人支持QQ平台，请在QQ里使用本插件。", "moe"])
        else:
            return False, None
             
    def info(self):
        return {
            "name": "GoodPlugins",
            "desc": "收集一些好玩的插件（动漫图片等）",
            "help": "指令: \nmoe或者动漫图片\n效果: 随机发送一张动漫图片\n",
            "version": "v1.0.0",
            "author": "Soulter"
        }


        # 热知识：检测消息开头指令，使用以下方法
        # if message.startswith("原神"):
        #     pass