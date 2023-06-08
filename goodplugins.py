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
# import moe
# import search_anime

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
                res = self.get_moe(message_obj, self.busy)
                return res[0], res[1]
                
            elif platform == "qqchan":
                """
                频道处理逻辑(频道暂时只支持回复字符串类型的信息，返回的信息都会被转成字符串，如果不想处理某一个平台的信息，直接返回False, None就行)
                """
                return True, tuple([True, "QQ频道暂时无法使用此插件，本机器人支持GOCQ平台，请在QQ里使用本插件。", "moe"])
        
        elif message == "sf" or message == "搜番":
            if platform == "gocq":
                res = self.get_search_anime(message_obj, self.busy, qq_platform)
                return res[0], res[1]
                
            elif platform == "qqchan":
                """
                频道处理逻辑(频道暂时只支持回复字符串类型的信息，返回的信息都会被转成字符串，如果不想处理某一个平台的信息，直接返回False, None就行)
                """
                return True, tuple([True, "QQ频道SDK暂时无法使用此插件，本机器人支持GOCQ平台，请在QQ里使用本插件。", "moe"])
            
        elif message.startswith("喜报"):
            if platform == "gocq":
                msg = message[2:].strip()
                res = self.congrats(msg)
                return res[0], res[1]
        
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
        return True, tuple([True, [Image.fromFileSystem(path + "/t.jpg")], "congrats"])

    def get_moe(self, message_obj, busy):
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
        
    def get_search_anime(self, message_obj, busy, qq_platform = None):
        if message_obj.sender.user_id in busy and busy[message_obj.sender.user_id]:
                    return True, tuple([True, "有一个服务于你的任务正在执行，请稍等。", "moe"])
        else:
            busy[message_obj.sender.user_id] = True
        url = "https://api.trace.moe/search?anilistInfo&url=" 
        try:
            if isinstance(message_obj.message[1], Image):
                url += message_obj.message[1].url
                print(url)
                if qq_platform != None:
                    try:
                        qq_platform.send(message_obj, "正在搜索中，请稍等。")
                    except Exception as e:
                        print(e)
                        pass
                resp = requests.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data["result"] and len(data["result"]) > 0:
                        # 番剧时间转换为x分x秒
                        data["result"][0]["from"] = self.time_convert(data["result"][0]["from"])
                        data["result"][0]["to"] = self.time_convert(data["result"][0]["to"])

                        # name = data["result"][0]["anilist"]["title"]["native"]
                        # 调用https://trace.moe/anilist/翻译成中文

                        warn = ""
                        if float(data["result"][0]["similarity"]) < 0.8:
                            warn = "相似度过低，可能不是同一番剧。建议：相同尺寸大小的截图; 去除四周的黑边\n\n"

                        busy[message_obj.sender.user_id] = False
                        return True, tuple([True, [Plain(f"{warn}番名: {data['result'][0]['anilist']['title']['native']}\n相似度: {data['result'][0]['similarity']}\n剧集: 第{data['result'][0]['episode']}集\n时间: {data['result'][0]['from']} - {data['result'][0]['to']}\n精准空降截图:"),
                                                Image.fromURL(data['result'][0]['image'])], "sf"])
                    else:
                        busy[message_obj.sender.user_id] = False
                        return True, tuple([False, "没有找到相关番剧", "sf"])
                else:
                    busy[message_obj.sender.user_id] = False
                    return True, tuple([False, "api出错", "sf"])
        except Exception as e:
            busy[message_obj.sender.user_id] = False
            raise e
        

    def time_convert(self, t):
        m, s = divmod(t, 60)
        return f"{int(m)}分{int(s)}秒"
    

# test
if __name__ == "__main__":
    gp = GoodPluginsPlugin()
    gp.congrats("喜报喜报喜报喜报喜报喜报喜报喜报喜报喜报喜报喜报喜报喜报")