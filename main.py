import random
import asyncio
import os
import json
import datetime
import aiohttp
import urllib.parse
import logging
from PIL import Image as PILImage
from PIL import ImageDraw as PILImageDraw
from PIL import ImageFont as PILImageFont
from astrbot.api import AstrBotConfig
from astrbot.api.all import AstrMessageEvent, CommandResult, Context, Image, Plain
import astrbot.api.event.filter as filter
from astrbot.api.star import register, Star

logger = logging.getLogger("astrbot")


@register("astrbot_plugin_essential", "Soulter", "", "", "")
class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self.PLUGIN_NAME = "astrbot_plugin_essential"
        PLUGIN_NAME = self.PLUGIN_NAME
        path = os.path.abspath(os.path.dirname(__file__))
        self.mc_html_tmpl = open(
            path + "/templates/mcs.html", "r", encoding="utf-8"
        ).read()
        self.what_to_eat_data: list = json.loads(
            open(path + "/resources/food.json", "r", encoding="utf-8").read()
        )["data"]

        if not os.path.exists(f"data/{PLUGIN_NAME}_data.json"):
            with open(f"data/{PLUGIN_NAME}_data.json", "w", encoding="utf-8") as f:
                f.write(json.dumps({}, ensure_ascii=False, indent=2))
        with open(f"data/{PLUGIN_NAME}_data.json", "r", encoding="utf-8") as f:
            self.data = json.loads(f.read())
        self.good_morning_data = self.data.get("good_morning", {})

        # moe
        self.moe_urls = [
            "https://t.mwm.moe/pc/",
            "https://t.mwm.moe/mp",
            "https://www.loliapi.com/acg/",
            "https://www.loliapi.com/acg/pc/",
        ]

        self.search_anmime_demand_users = {}
        self.daily_sleep_cache = {}
        self.good_morning_cd = {} 

    def _get_report_font_size(self) -> int:
        size = self.config.get("report_font_size", 65)
        try:
            size = int(size)
        except (TypeError, ValueError):
            return 65
        return size if size > 0 else 65

    def time_convert(self, t):
        m, s = divmod(t, 60)
        return f"{int(m)}分{int(s)}秒"
    
    def get_cached_sleep_count(self, umo_id: str, date_str: str) -> int:
        """获取缓存的睡觉人数"""
        if umo_id not in self.daily_sleep_cache:
            self.daily_sleep_cache[umo_id] = {}
        return self.daily_sleep_cache[umo_id].get(date_str, -1)

    def update_sleep_cache(self, umo_id: str, date_str: str, count: int):
        """更新睡觉人数缓存"""
        if umo_id not in self.daily_sleep_cache:
            self.daily_sleep_cache[umo_id] = {}
        self.daily_sleep_cache[umo_id][date_str] = count

    def invalidate_sleep_cache(self, umo_id: str, date_str: str):
            """使缓存失效"""
            if umo_id in self.daily_sleep_cache and date_str in self.daily_sleep_cache[umo_id]:
                del self.daily_sleep_cache[umo_id][date_str]

    def check_good_morning_cd(self, user_id: str, current_time: datetime.datetime) -> bool:
        """检查用户是否在CD中，返回True表示在CD中"""
        if user_id not in self.good_morning_cd:
            return False
        
        last_time = self.good_morning_cd[user_id]
        time_diff = (current_time - last_time).total_seconds()
        return time_diff < 1800  # 硬编码30分钟

    def update_good_morning_cd(self, user_id: str, current_time: datetime.datetime):
        """更新用户的CD时间"""
        self.good_morning_cd[user_id] = current_time

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_search_anime(self, message: AstrMessageEvent):
        """检查是否有搜番请求"""
        sender = message.get_sender_id()
        if sender in self.search_anmime_demand_users:
            message_obj = message.message_obj
            url = "https://api.trace.moe/search?anilistInfo&url="
            image_obj = None
            for i in message_obj.message:
                if isinstance(i, Image):
                    image_obj = i
                    break
            try:
                try:
                    # 需要经过url encode
                    image_url = urllib.parse.quote(image_obj.url)
                    url += image_url
                except BaseException as _:
                    if sender in self.search_anmime_demand_users:
                        del self.search_anmime_demand_users[sender]
                    return CommandResult().error(
                        f"发现不受本插件支持的图片数据：{type(image_obj)}，插件无法解析。"
                    )

                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            if sender in self.search_anmime_demand_users:
                                del self.search_anmime_demand_users[sender]
                            return CommandResult().error("请求失败")
                        data = await resp.json()

                if data["result"] and len(data["result"]) > 0:
                    # 番剧时间转换为x分x秒
                    data["result"][0]["from"] = self.time_convert(
                        data["result"][0]["from"]
                    )
                    data["result"][0]["to"] = self.time_convert(data["result"][0]["to"])

                    warn = ""
                    if float(data["result"][0]["similarity"]) < 0.8:
                        warn = "相似度过低，可能不是同一番剧。建议：相同尺寸大小的截图; 去除四周的黑边\n\n"
                    if sender in self.search_anmime_demand_users:
                        del self.search_anmime_demand_users[sender]
                    return CommandResult(
                        chain=[
                            Plain(
                                f"{warn}番名: {data['result'][0]['anilist']['title']['native']}\n相似度: {data['result'][0]['similarity']}\n剧集: 第{data['result'][0]['episode']}集\n时间: {data['result'][0]['from']} - {data['result'][0]['to']}\n精准空降截图:"
                            ),
                            Image.fromURL(data["result"][0]["image"]),
                        ],
                        use_t2i_=False,
                    )
                else:
                    if sender in self.search_anmime_demand_users:
                        del self.search_anmime_demand_users[sender]
                    return CommandResult(True, False, [Plain("没有找到番剧")], "sf")
            except Exception as e:
                raise e

    @filter.command("喜报")
    async def congrats(self, message: AstrMessageEvent):
        """喜报生成器"""
        msg = message.message_str.replace("喜报", "").strip()
        for i in range(20, len(msg), 20):
            msg = msg[:i] + "\n" + msg[i:]

        path = os.path.abspath(os.path.dirname(__file__))
        bg = path + "/congrats.jpg"
        img = PILImage.open(bg)
        draw = PILImageDraw.Draw(img)
        font = PILImageFont.truetype(path + "/simhei.ttf", self._get_report_font_size())

        # Calculate the width and height of the text
        text_width, text_height = draw.textbbox((0, 0), msg, font=font)[2:4]

        # Calculate the starting position of the text to center it.
        x = (img.size[0] - text_width) / 2
        y = (img.size[1] - text_height) / 2

        draw.text(
            (x, y),
            msg,
            font=font,
            fill=(255, 0, 0),
            stroke_width=3,
            stroke_fill=(255, 255, 0),
        )

        img.save("congrats_result.jpg")
        return CommandResult().file_image("congrats_result.jpg")

    @filter.command("悲报")
    async def uncongrats(self, message: AstrMessageEvent):
        """悲报生成器"""
        msg = message.message_str.replace("悲报", "").strip()
        for i in range(20, len(msg), 20):
            msg = msg[:i] + "\n" + msg[i:]

        path = os.path.abspath(os.path.dirname(__file__))
        bg = path + "/uncongrats.jpg"
        img = PILImage.open(bg)
        draw = PILImageDraw.Draw(img)
        font = PILImageFont.truetype(path + "/simhei.ttf", self._get_report_font_size())

        # Calculate the width and height of the text
        text_width, text_height = draw.textbbox((0, 0), msg, font=font)[2:4]

        # Calculate the starting position of the text to center it.
        x = (img.size[0] - text_width) / 2
        y = (img.size[1] - text_height) / 2

        draw.text(
            (x, y),
            msg,
            font=font,
            fill=(0, 0, 0),
            stroke_width=3,
            stroke_fill=(255, 255, 255),
        )

        img.save("uncongrats_result.jpg")
        return CommandResult().file_image("uncongrats_result.jpg")

    @filter.command("moe")
    async def get_moe(self, message: AstrMessageEvent):
        """随机动漫图片"""
        shuffle = random.sample(self.moe_urls, len(self.moe_urls))
        for url in shuffle:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            return CommandResult().error(f"获取图片失败: {resp.status}")
                        data = await resp.read()
                        break
            except Exception as e:
                logger.error(f"从 {url} 获取图片失败: {e}。正在尝试下一个API。")
                continue
        # 保存图片到本地
        try:
            with open("moe.jpg", "wb") as f:
                f.write(data)
            return CommandResult().file_image("moe.jpg")

        except Exception as e:
            return CommandResult().error(f"保存图片失败: {e}")

    @filter.command("搜番")
    async def get_search_anime(self, message: AstrMessageEvent):
        """以图搜番"""
        sender = message.get_sender_id()
        if sender in self.search_anmime_demand_users:
            yield message.plain_result("正在等你发图喵，请不要重复发送")
        self.search_anmime_demand_users[sender] = False
        yield message.plain_result("请在 30 喵内发送一张图片让我识别喵")
        await asyncio.sleep(30)
        if sender in self.search_anmime_demand_users:
            if self.search_anmime_demand_users[sender]:
                del self.search_anmime_demand_users[sender]
                return
            del self.search_anmime_demand_users[sender]
            yield message.plain_result("🧐你没有发送图片，搜番请求已取消了喵")

    @filter.command("mcs")
    async def mcs(self, message: AstrMessageEvent):
        """查mc服务器"""
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
        motd = "查询失败"
        if (
            "motd" in data
            and isinstance(data["motd"], dict)
            and isinstance(data["motd"].get("clean"), list)
        ):
            motd_lines = [
                i.strip()
                for i in data["motd"]["clean"]
                if isinstance(i, str) and i.strip()
            ]
            motd = "\n".join(motd_lines) if motd_lines else "查询失败"

        players = "查询失败"
        version = "查询失败"
        if "error" in data:
            return CommandResult().error(f"查询失败: {data['error']}")

        name_list = []

        if "players" in data:
            players = f"{data['players']['online']}/{data['players']['max']}"

            if "list" in data["players"]:
                name_list = data["players"]["list"]

        if "version" in data:
            version = str(data["version"])

        status = "🟢" if data["online"] else "🔴"

        name_list_str = ""
        if name_list:
            name_list_str = "\n".join(name_list)
        if not name_list_str:
            name_list_str = "无玩家在线"

        result_text = (
            "【查询结果】\n"
            f"状态: {status}\n"
            f"服务器IP: {ip}\n"
            f"版本: {version}\n"
            f"MOTD: {motd}"
            f"玩家人数: {players}\n"
            f"在线玩家: \n{name_list_str}"
        )

        return CommandResult().message(result_text).use_t2i(False)

    @filter.command("一言")
    async def hitokoto(self, message: AstrMessageEvent):
        """来一条一言"""
        url = "https://v1.hitokoto.cn"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return CommandResult().error("请求失败")
                data = await resp.json()
        return CommandResult().message(data["hitokoto"] + " —— " + data["from"])

    async def save_what_eat_data(self):
        path = os.path.abspath(os.path.dirname(__file__))
        with open(path + "/resources/food.json", "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"data": self.what_to_eat_data}, ensure_ascii=False, indent=2
                )
            )

    @filter.command("今天吃什么")
    async def what_to_eat(self, message: AstrMessageEvent):
        """今天吃什么"""
        if "添加" in message.message_str:
            l = message.message_str.split(" ")
            # 今天吃什么 添加 xxx xxx xxx
            if len(l) < 3:
                return CommandResult().error(
                    "格式：今天吃什么 添加 [食物1] [食物2] ..."
                )
            self.what_to_eat_data += l[2:]  # 添加食物
            await self.save_what_eat_data()
            return CommandResult().message("添加成功")
        elif "删除" in message.message_str:
            l = message.message_str.split(" ")
            # 今天吃什么 删除 xxx xxx xxx
            if len(l) < 3:
                return CommandResult().error(
                    "格式：今天吃什么 删除 [食物1] [食物2] ..."
                )
            for i in l[2:]:
                if i in self.what_to_eat_data:
                    self.what_to_eat_data.remove(i)
            await self.save_what_eat_data()
            return CommandResult().message("删除成功")

        ret = f"今天吃 {random.choice(self.what_to_eat_data)}！"
        return CommandResult().message(ret)

    @filter.command("喜加一")
    async def epic_free_game(self, message: AstrMessageEvent):
        """EPIC 喜加一"""
        url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return CommandResult().error("请求失败")
                data = await resp.json()

        games = []
        upcoming = []

        for game in data["data"]["Catalog"]["searchStore"]["elements"]:
            title = game.get("title", "未知")
            try:
                if not game.get("promotions"):
                    continue
                original_price = game["price"]["totalPrice"]["fmtPrice"][
                    "originalPrice"
                ]
                discount_price = game["price"]["totalPrice"]["fmtPrice"][
                    "discountPrice"
                ]
                promotions = game["promotions"]["promotionalOffers"]
                upcoming_promotions = game["promotions"]["upcomingPromotionalOffers"]

                if promotions:
                    promotion = promotions[0]["promotionalOffers"][0]
                else:
                    promotion = upcoming_promotions[0]["promotionalOffers"][0]
                start = promotion["startDate"]
                end = promotion["endDate"]
                # 2024-09-19T15:00:00.000Z
                start_utc8 = datetime.datetime.strptime(
                    start, "%Y-%m-%dT%H:%M:%S.%fZ"
                ) + datetime.timedelta(hours=8)
                start_human = start_utc8.strftime("%Y-%m-%d %H:%M")
                end_utc8 = datetime.datetime.strptime(
                    end, "%Y-%m-%dT%H:%M:%S.%fZ"
                ) + datetime.timedelta(hours=8)
                end_human = end_utc8.strftime("%Y-%m-%d %H:%M")
                discount = float(promotion["discountSetting"]["discountPercentage"])
                if discount != 0:
                    # 过滤掉不是免费的游戏
                    continue

                if promotions:
                    games.append(
                        f"【{title}】\n原价: {original_price} | 现价: {discount_price}\n活动时间: {start_human} - {end_human}"
                    )
                else:
                    upcoming.append(
                        f"【{title}】\n原价: {original_price} | 现价: {discount_price}\n活动时间: {start_human} - {end_human}"
                    )

            except BaseException as e:
                raise e
                games.append(f"处理 {title} 时出现错误")

        if len(games) == 0:
            return CommandResult().message("暂无免费游戏")
        return (
            CommandResult()
            .message(
                "【EPIC 喜加一】\n"
                + "\n\n".join(games)
                + "\n\n"
                + "【即将免费】\n"
                + "\n\n".join(upcoming)
            )
            .use_t2i(False)
        )

    @filter.regex(r"^(早安|晚安)")
    async def good_morning(self, message: AstrMessageEvent):
        """和Bot说早晚安，记录睡眠时间，培养良好作息"""
        # CREDIT: 灵感部分借鉴自：https://github.com/MinatoAquaCrews/nonebot_plugin_morning
        umo_id = message.unified_msg_origin
        user_id = message.message_obj.sender.user_id
        user_name = message.message_obj.sender.nickname
        curr_utc8 = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        curr_human = curr_utc8.strftime("%Y-%m-%d %H:%M:%S")

        # 检查CD
        if self.check_good_morning_cd(user_id, curr_utc8):
            return CommandResult().message("你刚刚已经说过早安/晚安了，请30分钟后再试喵~").use_t2i(False)

        is_night = "晚安" in message.message_str

        if umo_id in self.good_morning_data:
            umo = self.good_morning_data[umo_id]
        else:
            umo = {}
        if user_id in umo:
            user = umo[user_id]
        else:
            user = {
                "daily": {
                    "morning_time": "",
                    "night_time": "",
                }
            }

        if is_night:
            user["daily"]["night_time"] = curr_human
            user["daily"]["morning_time"] = ""  # 晚安后清空早安时间
        else:
            user["daily"]["morning_time"] = curr_human

        umo[user_id] = user
        self.good_morning_data[umo_id] = umo

        with open(f"data/{self.PLUGIN_NAME}_data.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(self.good_morning_data, ensure_ascii=False, indent=2))
            
        # 更新CD
        self.update_good_morning_cd(user_id, curr_utc8)

        # 根据 day 判断今天是本群第几个睡觉的
        curr_day: int = curr_utc8.day
        curr_date_str = curr_utc8.strftime("%Y-%m-%d")

        self.invalidate_sleep_cache(umo_id, curr_date_str)
        
        curr_day_sleeping = 0
        curr_date_prefix = curr_utc8.strftime("%Y-%m-%d") # 获取今天的日期
        for v in umo.values():
            n_time = v["daily"]["night_time"]
            if n_time and n_time.startswith(curr_date_prefix):
                # 只要晚安是今天，就代表今天睡了一个
                curr_day_sleeping += 1
        
        # 更新缓存为最新计算结果
        self.update_sleep_cache(umo_id, curr_date_str, curr_day_sleeping)

        if not is_night:
            # 计算睡眠时间: xx小时xx分
            sleep_duration_human = ""
            if user["daily"]["night_time"]:
                night_time = datetime.datetime.strptime(
                    user["daily"]["night_time"], "%Y-%m-%d %H:%M:%S"
                )
                morning_time = datetime.datetime.strptime(
                    user["daily"]["morning_time"], "%Y-%m-%d %H:%M:%S"
                )
                sleep_duration = (morning_time - night_time).total_seconds()
                hrs = int(sleep_duration / 3600)
                mins = int((sleep_duration % 3600) / 60)
                sleep_duration_human = f"{hrs}小时{mins}分"

            good_moring_text = ""

            if sleep_duration_human:
                good_moring_text = f"早上好喵，{user_name}！\n现在是 {curr_human}，昨晚你睡了 {sleep_duration_human}。"
            else:
                good_moring_text = f"早上好喵，{user_name}！\n现在是 {curr_human}，昨晚似乎没说晚安呢~"

            return (
                CommandResult()
                .message(
                    good_moring_text
                )
                .use_t2i(False)
            )
        else:
            return (
                CommandResult()
                .message(
                    f"快睡觉喵，{user_name}！\n现在是 {curr_human}，你是本群今天第 {curr_day_sleeping} 个睡觉的。"
                )
                .use_t2i(False)
            )
