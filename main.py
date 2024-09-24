import random, os, json
import aiohttp
import urllib.parse
import logging
from PIL import Image as PILImage
from PIL import ImageDraw as PILImageDraw
from PIL import ImageFont as PILImageFont
from util.plugin_dev.api.v1 import (
    AstrMessageEvent,
    CommandResult,
    Context,
    Image,
    Plain
)

logger = logging.getLogger("astrbot")

class Main:
    def __init__(self, context: Context) -> None:
        PLUGIN_NAME = "astrbot_plugin_essential"
        path = os.path.abspath(os.path.dirname(__file__))
        self.mc_html_tmpl = open(path + "/templates/mcs.html", "r").read()
        self.what_to_eat_data: list = json.loads(open(path + "/resources/food.json", "r").read())['data']
        
        context.register_commands(PLUGIN_NAME, "moe", "随机动漫图片", 1, self.get_moe)
        context.register_commands(PLUGIN_NAME, "搜番", "以图搜番", 1, self.get_search_anime)
        context.register_commands(PLUGIN_NAME, "喜报", "喜报生成器", 1, self.congrats)
        context.register_commands(PLUGIN_NAME, "mcs", "查mc服务器", 1, self.mcs)
        context.register_commands(PLUGIN_NAME, "一言", "来一条一言", 1, self.hitokoto)
        context.register_commands(PLUGIN_NAME, "今天吃什么", "今天吃什么", 1, self.what_to_eat)

    def congrats(self, message: AstrMessageEvent, context: Context):
        msg = message.message_str.replace("喜报", "").strip()
        for i in range(20, len(msg), 20):
            msg = msg[:i] + "\n" + msg[i:]
        path = os.path.abspath(os.path.dirname(__file__))
        bg = path + "/congrats.jpg"
        img = PILImage.open(bg)
        draw = PILImageDraw.Draw(img)
        font = PILImageFont.truetype(path + "/simhei.ttf", 65)
        
        draw.text((img.size[0] / 2 - 65 / 2, img.size[1] / 2 - 65 / 2), msg, 
                  font=font, fill=(255, 0, 0), stroke_width=3, stroke_fill=(255, 255, 0))
        img.save("congrats_result.jpg")
        return CommandResult().file_image("congrats_result.jpg")

    async def get_moe(self, message: AstrMessageEvent, context: Context):
        uid = message.message_obj.sender.user_id
        urls = ["https://t.mwm.moe/pc/", "https://t.mwm.moe/mp"]
        
        async with aiohttp.ClientSession() as session:
            async with session.get(random.choice(urls)) as resp:
                if resp.status != 200:
                    return CommandResult().error(f"获取图片失败: {resp.status}")
                data = await resp.read()
        # 保存图片到本地
        try:
            with open("moe.jpg", "wb") as f:
                f.write(data)
            return CommandResult().file_image("moe.jpg")
            
        except Exception as e:
            return CommandResult().error(f"保存图片失败: {e}")
        
    async def get_search_anime(self, message: AstrMessageEvent, context: Context):
        message_obj = message.message_obj
        url = "https://api.trace.moe/search?anilistInfo&url="
        image_obj = None
        for i in message_obj.message:
            if isinstance(i, Image):
                image_obj = i
                break
        if not image_obj:
            return CommandResult().error("格式：/搜番 [图片]")
        try:
            try:
                # 需要经过url encode
                image_url = urllib.parse.quote(image_obj.url)
                url += image_url
            except BaseException as e:
                return CommandResult().error(f"发现不受本插件支持的图片数据：{type(image_obj)}，插件无法解析。")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return CommandResult().error("请求失败")
                    data = await resp.json()
                    
            if data["result"] and len(data["result"]) > 0:
                # 番剧时间转换为x分x秒
                data["result"][0]["from"] = self.time_convert(data["result"][0]["from"])
                data["result"][0]["to"] = self.time_convert(data["result"][0]["to"])

                warn = ""
                if float(data["result"][0]["similarity"]) < 0.8:
                    warn = "相似度过低，可能不是同一番剧。建议：相同尺寸大小的截图; 去除四周的黑边\n\n"

                return CommandResult(
                    message_chain=[Plain(f"{warn}番名: {data['result'][0]['anilist']['title']['native']}\n相似度: {data['result'][0]['similarity']}\n剧集: 第{data['result'][0]['episode']}集\n时间: {data['result'][0]['from']} - {data['result'][0]['to']}\n精准空降截图:"),
                                Image.fromURL(data['result'][0]['image'])],
                    use_t2i=False
                )
            else:
                return CommandResult(
                    True, False, [Plain("没有找到番剧")], "sf"
                )
        except Exception as e:
            raise e
    
    async def mcs(self, message: AstrMessageEvent, context: Context):
        message_str = message.message_str
        if message_str == "mcs":
            return CommandResult().error("查 Minecraft 服务器。格式: /mcs [服务器地址]")
        ip = message_str.replace("mcs", "").strip()
        url = f"https://api.mcsrvstat.us/2/{ip}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return CommandResult().error("请求失败")
                data = await resp.json()
                logger.info(f"获取到 {ip} 的服务器信息。")
                
        # result = await context.image_renderer.render_custom_template(self.mc_html_tmpl, data, return_url=True)
        motd = ""
        for i in data["motd"]["clean"]:
            if isinstance(i, str):
                motd += "\n" + i.strip()
        
        if "error" in data:
            return CommandResult().error(f"查询失败: {data['error']}")
        return CommandResult().message(f"""【查询结果】
服务器IP: {ip}
在线玩家: {data['players']['online']}/{data['players']['max']}
版本: {data['version']}
MOTD: {motd}""").use_t2i(False)
        
        
    def time_convert(self, t):
        m, s = divmod(t, 60)
        return f"{int(m)}分{int(s)}秒"

    async def hitokoto(self, message: AstrMessageEvent, context: Context):
        url = "https://v1.hitokoto.cn"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return CommandResult().error("请求失败")
                data = await resp.json()
        return CommandResult().message(data["hitokoto"] + " —— " + data["from"])
    
    async def save_what_eat_data(self):
        path = os.path.abspath(os.path.dirname(__file__))
        with open(path + "/resources/food.json", "w") as f:
            f.write(json.dumps({"data": self.what_to_eat_data}, ensure_ascii=False, indent=2))
    
    async def what_to_eat(self, message: AstrMessageEvent, context: Context):
        if "添加" in message.message_str:
            l = message.message_str.split(" ")
            # 今天吃什么 添加 xxx xxx xxx
            if len(l) < 3:
                return CommandResult().error("格式：今天吃什么 添加 [食物1] [食物2] ...")
            self.what_to_eat_data += l[2:]  # 添加食物
            await self.save_what_eat_data()
            return CommandResult().message("添加成功")
        elif "删除" in message.message_str:
            l = message.message_str.split(" ")
            # 今天吃什么 删除 xxx xxx xxx
            if len(l) < 3:
                return CommandResult().error("格式：今天吃什么 删除 [食物1] [食物2] ...")
            for i in l[2:]:
                if i in self.what_to_eat_data:
                    self.what_to_eat_data.remove(i)
            await self.save_what_eat_data()
            return CommandResult().message("删除成功")
        
        ret = f"今天吃 {random.choice(self.what_to_eat_data)}！"
        return CommandResult().message(ret)