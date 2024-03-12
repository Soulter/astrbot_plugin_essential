from nakuru.entities.components import *
from nakuru import (
    GroupMessage,
    FriendMessage
)
from botpy.message import Message, DirectMessage
import random
import requests
import PIL
from PIL import Image as PILImage
from PIL import ImageDraw as PILImageDraw
from PIL import ImageFont as PILImageFont
flag_not_support = False
try:
    from util.plugin_dev.api.v1.config import *
    from util.plugin_dev.api.v1.bot import (
        PluginMetadata,
        PluginType,
        AstrMessageEvent,
        CommandResult,
    )
    from util.plugin_dev.api.v1.register import register_llm, unregister_llm
except ImportError:
    flag_not_support = True
    print("llms: 导入接口失败。请升级到 AstrBot 最新版本。")
import time
from .poke import poke_resource

class GoodPluginsPlugin:
    """
    初始化函数, 可以选择直接pass
    """
    def __init__(self) -> None:
        self.busy = {}
        self.marry = {}
        # 获取本文件的绝对路径
        self.path = os.path.abspath(os.path.dirname(__file__))
        # 读取marry.json
        try:
            with open(self.path + "/marry.json", "r") as f:
                self.marry = json.load(f)
        except Exception as e:
            # 创建
            with open(self.path + "/marry.json", "w") as f:
                json.dump({}, f)
        pass

    def run(self, ame: AstrMessageEvent):
        message = ame.message_str
        message_obj = ame.message_obj
        platform = ame.platform
        role = ame.role

        if message_obj.sub_type == "poke":
            return True, tuple([True, [Plain(random.choice(poke_resource))], "poke"])

        if message == "moe" or message == "动漫图片":
            res = self.get_moe(message_obj, self.busy)
            return res
        
        elif message == "sf" or message == "搜番":
            if platform == "gocq":
                res = self.get_search_anime(message_obj, self.busy)
                return res
            
        elif message.startswith("喜报"):
            msg = message[2:].strip()
            res = self.congrats(msg)
            return res

        elif message.startswith("sleep"):
            if role != "admin":
                return CommandResult(
                    True, False, [Plain("你没有权限执行此操作")], "sleep"
                )
            if platform.platform_name == "gocq" and message_obj.type == "GroupMessage":
                self.random_sleep(message_obj.group_id, platform.platform_instance)
                return CommandResult(
                    True, True, [Plain("已执行")], "sleep"
                )
            
            
        elif message.startswith("marry"):
            if platform.platform_name == "gocq" and message_obj.type == "GroupMessage":
                res = self.random_marry(message_obj.sender.user_id, message_obj.group_id, platform.platform_instance)
                return True, tuple([True, res, "marry"])

        else:
            return False, None
             
    def info(self):
        return {
            "name": "GoodPlugins",
            "desc": "收集一些好玩的插件（随机动漫图片、以图搜番等）",
            "help": "指令: \nmoe或者动漫图片\n效果: 随机发送一张动漫图片\n\nsf或者搜番 然后带上图片\n效果: 以图搜番\n\n喜报 xxx\n效果：喜报生成器\n\nsleep\n效果：随机禁言一个人8小时\n\n",
            "version": "v1.0.3",
            "author": "Soulter"
        }

    def congrats(self, msg):
        # 超过20个字，加一个换行
        is_new_line = False
        tmpl = msg
        for i in range(20, len(msg), 20):
            msg = msg[:i] + "\n" + msg[i:]
            is_new_line = True
        if is_new_line:
            tmpl = msg[:20]
        # 获得绝对路径
        path = os.path.abspath(os.path.dirname(__file__))
        # 读取文件
        bg = path + "/congrats.jpg"
        # PIL编辑，msg居中
        img = PILImage.open(bg)
        draw = PILImageDraw.Draw(img)
        
        font = PILImageFont.truetype(path + "/simhei.ttf", 65)
        # 红色字体，外边框为黄色，阴影
        draw.text((img.size[0] / 2 - font.getsize(tmpl)[0] / 2, img.size[1] / 2 - font.getsize(tmpl)[1] / 2), msg, 
                  font=font, fill=(255, 0, 0), stroke_width=3, stroke_fill=(255, 255, 0),
                  )
        # 保存图片
        img.save(path + "/t.jpg")
        # 发送图片
        return CommandResult(
            True, True, [Image.fromFileSystem(path + "/t.jpg")], "congrats"
        )

    def get_moe(self, message_obj, busy):
        uid = ""
        uid = message_obj.sender.user_id
        if uid in busy and busy[uid]:
            return CommandResult(
                True, True, [Plain("有一个服务于你的任务正在执行，请稍等。")], "moe"
            )
        busy[uid] = True
        """
        QQ平台指令处理逻辑
        """
        urls = ["https://t.mwm.moe/pc/","https://t.mwm.moe/mp"]
        
        resp = requests.get(random.choice(urls))
        if resp.status_code == 200:
            # 保存图片到本地
            try:
                with open("moe.jpg", "wb") as f:
                    f.write(resp.content)
                # 发送图片
                busy[uid] = False
                return CommandResult(
                    True, True, [Image.fromFileSystem("moe.jpg")], "moe"
                )
            except Exception as e:
                busy[uid] = False
                return CommandResult(
                    True, False, [Plain("获取图片失败")], "moe"
                )
        else:
            busy[uid] = False
            return CommandResult(
                True, False, [Plain("获取图片失败")], "moe"
            )
        
    def get_search_anime(self, message_obj, busy, qq_platform = None):
        if message_obj.sender.user_id in busy and busy[message_obj.sender.user_id]:
            return CommandResult(
                True, True, [Plain("有一个服务于你的任务正在执行，请等待。")], "sf"
            )
        busy[message_obj.sender.user_id] = True
        url = "https://api.trace.moe/search?anilistInfo&url=" 
        try:
            if isinstance(message_obj.message[1], Image):
                url += message_obj.message[1].url
                print(url)
                resp = requests.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data["result"] and len(data["result"]) > 0:
                        # 番剧时间转换为x分x秒
                        data["result"][0]["from"] = self.time_convert(data["result"][0]["from"])
                        data["result"][0]["to"] = self.time_convert(data["result"][0]["to"])

                        warn = ""
                        if float(data["result"][0]["similarity"]) < 0.8:
                            warn = "相似度过低，可能不是同一番剧。建议：相同尺寸大小的截图; 去除四周的黑边\n\n"

                        busy[message_obj.sender.user_id] = False
                        return CommandResult(
                            True, True, [Plain(f"{warn}番名: {data['result'][0]['anilist']['title']['native']}\n相似度: {data['result'][0]['similarity']}\n剧集: 第{data['result'][0]['episode']}集\n时间: {data['result'][0]['from']} - {data['result'][0]['to']}\n精准空降截图:"),
                                        Image.fromURL(data['result'][0]['image'])], "sf"
                        )
                    else:
                        busy[message_obj.sender.user_id] = False
                        return CommandResult(
                            True, False, [Plain("没有找到番剧")], "sf"
                        )
                else:
                    busy[message_obj.sender.user_id] = False
                    return CommandResult(
                        True, False, [Plain(f"请求失败, code: {resp.status_code}")], "sf"
                    )
        except Exception as e:
            busy[message_obj.sender.user_id] = False
            raise e
        
    def time_convert(self, t):
        m, s = divmod(t, 60)
        return f"{int(m)}分{int(s)}秒"
    
    def random_sleep(self, group_id, qq_platform):
        ls = qq_platform.nakuru_method_invoker(qq_platform.get_client().getGroupMemberList, group_id)
        ls = random.choice(ls)
        # 禁言8小时
        qq_platform.nakuru_method_invoker(qq_platform.get_client().mute, group_id, ls.user_id, 60 * 60 * 8)
        ret = "晚安zZ\n被禁名称：" + ls.nickname + "\n被禁时间：28800秒" + "\n解禁时间：" + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 60 * 60 * 8))
        qq_platform.send(group_id, ret)

    def random_marry(self, user_id, group_id, qq_platform):
        if group_id not in self.marry:
            self.marry[group_id] = {}
        # 时间24小时
        if user_id in self.marry[group_id] and self.marry[group_id][user_id]["time"] > int(time.time()) - 60 * 60 * 24:
            return [Plain("你的今日对象是: " + self.marry[group_id][user_id]["name"]), Image.fromURL(self.marry[group_id][user_id]["url"])]
        else:
            ls = qq_platform.nakuru_method_invoker(qq_platform.get_client().getGroupMemberList, group_id)
            ls = random.choice(ls)
            url = "https://q1.qlogo.cn/g?b=qq&nk=" + str(ls.user_id) + "&s=640"
            ret = "你的今日对象是：" + ls.nickname
            self.marry[group_id][user_id] = {"name": ls.nickname, "url": url, "time": int(time.time())}
            with open(self.path + "/marry.json", "w") as f:
                json.dump(self.marry, f)
        return [Plain(ret), Image.fromURL(url)]

    def poke(self):
        random.choice(poke_resource)
        

# test
if __name__ == "__main__":
    gp = GoodPluginsPlugin()
    gp.congrats("喜报喜报喜报喜报喜报喜报喜报喜报喜报喜报喜报喜报喜报喜报")
