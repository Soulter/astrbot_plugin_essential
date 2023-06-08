from nakuru.entities.components import *
from nakuru import (
    GroupMessage,
    FriendMessage
)
from botpy.message import Message, DirectMessage
import random
import requests
# 设置插件路径
import sys
sys.path.append("./plugins")
import moe
import search_anime

class GoodPluginsPlugin:
    """
    初始化函数, 可以选择直接pass
    """
    def __init__(self) -> None:
        self.busy = {}
        pass

    # def set_busy(self, qq: int):
    #     self.busy[qq] = True

    # def set_free(self, qq: int):
    #     self.busy[qq] = False

    def run(self, message: str, role: str, platform: str, message_obj: GroupMessage, qq_platform = None):


        if message == "moe" or message == "动漫图片":

            if platform == "gocq":
                res = moe.get_moe(message_obj, self.busy)
                return res[0], res[1]
                
            elif platform == "qqchan":
                """
                频道处理逻辑(频道暂时只支持回复字符串类型的信息，返回的信息都会被转成字符串，如果不想处理某一个平台的信息，直接返回False, None就行)
                """
                return True, tuple([True, "QQ频道暂时无法使用此插件，本机器人支持GOCQ平台，请在QQ里使用本插件。", "moe"])
        
        elif message == "sf" or message == "搜番":
            if platform == "gocq":
                res = search_anime.get_search_anime(message_obj, self.busy, qq_platform)
                return res[0], res[1]
                
            elif platform == "qqchan":
                """
                频道处理逻辑(频道暂时只支持回复字符串类型的信息，返回的信息都会被转成字符串，如果不想处理某一个平台的信息，直接返回False, None就行)
                """
                return True, tuple([True, "QQ频道SDK暂时无法使用此插件，本机器人支持GOCQ平台，请在QQ里使用本插件。", "moe"])
        
        else:
            return False, None
             
    def info(self):
        return {
            "name": "GoodPlugins",
            "desc": "收集一些好玩的插件（随机动漫图片、以图搜番等）",
            "help": "指令: \nmoe或者动漫图片\n效果: 随机发送一张动漫图片\n\nsf或者搜番 然后带上图片\n效果: 以图搜番\n",
            "version": "v1.0.2",
            "author": "Soulter"
        }



        # 热知识：检测消息开头指令，使用以下方法
        # if message.startswith("原神"):
        #     pass