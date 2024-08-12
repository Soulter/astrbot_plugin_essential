import random, os
import requests
import urllib.parse
from PIL import Image as PILImage
from PIL import ImageDraw as PILImageDraw
from PIL import ImageFont as PILImageFont
flag_not_support = False
try:
    from util.plugin_dev.api.v1.config import *
    from util.plugin_dev.api.v1.bot import (
        AstrMessageEvent,
        CommandResult,
        Context
    )
    from util.plugin_dev.api.v1.types import *
except ImportError:
    flag_not_support = True
    print("llms: 导入接口失败。请升级到 AstrBot 最新版本。")

class GoodPluginsPlugin:
    def __init__(self, context: Context) -> None:
        self.PLUGIN_NAME = "goodplugins"
        self.busy = {}
        self.marry = {}
        self.path = os.path.abspath(os.path.dirname(__file__))
        # try:
        #     with open(self.path + "/marry.json", "r") as f:
        #         self.marry = json.load(f)
        # except Exception as e:
        #     # 创建
        #     with open(self.path + "/marry.json", "w") as f:
        #         json.dump({}, f)
        
        context.register_commands("goodplugins", "moe", "随机动漫图片。", 1, self.get_moe)
        context.register_commands("goodplugins", "搜番", "以图搜番。", 1, self.get_search_anime)
        context.register_commands("goodplugins", "喜报", "喜报生成器。", 1, self.congrats)

    def congrats(self, message: AstrMessageEvent, context: Context):
        is_new_line = False
        msg = message.message_str.replace("喜报", "").strip()
        tmpl = msg
        for i in range(20, len(msg), 20):
            msg = msg[:i] + "\n" + msg[i:]
            is_new_line = True
        if is_new_line:
            tmpl = msg[:20]
        path = os.path.abspath(os.path.dirname(__file__))
        bg = path + "/congrats.jpg"
        img = PILImage.open(bg)
        draw = PILImageDraw.Draw(img)
        font = PILImageFont.truetype(path + "/simhei.ttf", 65)
        
        draw.text((img.size[0] / 2 - 65 / 2, img.size[1] / 2 - 65 / 2), msg, 
                  font=font, fill=(255, 0, 0), stroke_width=3, stroke_fill=(255, 255, 0))
        img.save(path + "/t.jpg")
        return CommandResult().file_image(path + "/t.jpg")

    def get_moe(self, message: AstrMessageEvent, context: Context):
        uid = message.message_obj.sender.user_id
        if uid in self.busy and self.busy[uid]:
            return CommandResult().message("有一个服务于你的任务正在执行，请等待。")
        self.busy[uid] = True
        urls = ["https://t.mwm.moe/pc/", "https://t.mwm.moe/mp"]
        
        resp = requests.get(random.choice(urls))
        if resp.status_code == 200:
            # 保存图片到本地
            try:
                with open("moe.jpg", "wb") as f:
                    f.write(resp.content)
                # 发送图片
                self.busy[uid] = False
                return CommandResult().file_image("moe.jpg")
                
            except Exception as e:
                self.busy[uid] = False
                return CommandResult().error("获取图片失败")
        else:
            self.busy[uid] = False
            return CommandResult().error("获取图片失败")
        
    def get_search_anime(self, message: AstrMessageEvent, context: Context):
        message_obj = message.message_obj
        
        if message_obj.sender.user_id in self.busy and self.busy[message_obj.sender.user_id]:
            return CommandResult().message("有一个服务于你的任务正在执行，请等待。")
        
        self.busy[message_obj.sender.user_id] = True
        url = "https://api.trace.moe/search?anilistInfo&url=" 
        try:
            if isinstance(message_obj.message[1], Image):
                try:
                    # 需要经过url encode
                    image_url = urllib.parse.quote(message_obj.message[1].url)
                    url += image_url
                except BaseException as e:
                    return CommandResult().error(f"发现不受本插件支持的图片数据：{type(message_obj.message[1])}，插件无法解析。")
                
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

                        self.busy[message_obj.sender.user_id] = False
                        return CommandResult(
                            message_chain=[[Plain(f"{warn}番名: {data['result'][0]['anilist']['title']['native']}\n相似度: {data['result'][0]['similarity']}\n剧集: 第{data['result'][0]['episode']}集\n时间: {data['result'][0]['from']} - {data['result'][0]['to']}\n精准空降截图:"),
                                        Image.fromURL(data['result'][0]['image'])]],
                            use_t2i=False
                        )
                    else:
                        self.busy[message_obj.sender.user_id] = False
                        return CommandResult(
                            True, False, [Plain("没有找到番剧")], "sf"
                        )
                else:
                    self.busy[message_obj.sender.user_id] = False
                    return CommandResult(
                        True, False, [Plain(f"请求失败, code: {resp.status_code}")], "sf"
                    )
        except Exception as e:
            self.busy[message_obj.sender.user_id] = False
            raise e
        
    def time_convert(self, t):
        m, s = divmod(t, 60)
        return f"{int(m)}分{int(s)}秒"

    # def random_marry(self, user_id, group_id, qq_platform):
    #     if group_id not in self.marry:
    #         self.marry[group_id] = {}
    #     # 时间24小时
    #     if user_id in self.marry[group_id] and self.marry[group_id][user_id]["time"] > int(time.time()) - 60 * 60 * 24:
    #         return [Plain("你的今日对象是: " + self.marry[group_id][user_id]["name"]), Image.fromURL(self.marry[group_id][user_id]["url"])]
    #     else:
    #         ls = qq_platform.nakuru_method_invoker(qq_platform.get_client().getGroupMemberList, group_id)
    #         ls = random.choice(ls)
    #         url = "https://q1.qlogo.cn/g?b=qq&nk=" + str(ls.user_id) + "&s=640"
    #         ret = "你的今日对象是：" + ls.nickname
    #         self.marry[group_id][user_id] = {"name": ls.nickname, "url": url, "time": int(time.time())}
    #         with open(self.path + "/marry.json", "w") as f:
    #             json.dump(self.marry, f)
    #     return [Plain(ret), Image.fromURL(url)]
