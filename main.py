import asyncio
import datetime
import json
import logging
import random
import re
import urllib.parse
from pathlib import Path
from typing import Optional

import aiohttp
import astrbot.api.event.filter as filter  # noqa: A004
from astrbot.api import AstrBotConfig, html_renderer
from astrbot.api.all import AstrMessageEvent, CommandResult, Context, Image, Plain
from astrbot.api.message_components import Poke
from astrbot.api.star import Star
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from PIL import Image as PILImage
from PIL import ImageDraw as PILImageDraw
from PIL import ImageFont as PILImageFont

logger = logging.getLogger("astrbot")


_DATA_DIR = "data"
_GOOD_MORNING_PREFIX = "good_morning:"
_MAX_SLEEP_HOURS = 24
_GOOD_MORNING_CD_SECONDS = 1800
_SIMILARITY_WARN_THRESHOLD = 0.8
_HTTP_OK = 200
_MIN_CMD_PARTS = 3


class Main(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self.PLUGIN_NAME = "astrbot_plugin_essential"

        # 动态加载 poke 子模块
        import importlib.util
        import sys

        _poke_name = "astrbot_plugin_essential_poke"
        if _poke_name in sys.modules:
            self._poke = sys.modules[_poke_name]
        else:
            _spec = importlib.util.spec_from_file_location(
                _poke_name,
                Path(__file__).resolve().parent / "resources" / "poke.py",
            )
            _mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            sys.modules[_poke_name] = _mod
            self._poke = _mod

        self._plugin_dir = Path(__file__).resolve().parent

        _mcs_html = self._plugin_dir / "templates" / "mcs.html"
        self.mc_html_tmpl = (
            _mcs_html.read_text(encoding="utf-8") if _mcs_html.exists() else ""
        )

        self.moe_urls = [
            "https://t.mwm.moe/pc/",
            "https://t.mwm.moe/mp",
            "https://www.loliapi.com/acg/",
            "https://www.loliapi.com/acg/pc/",
        ]

        self.search_anmime_demand_users: dict = {}
        self.good_morning_cd: dict = {}

        # 图片缓存目录
        self._cache_dir = (
            Path(get_astrbot_data_path()) / "plugin_data" / "astrbot_plugin_essential"
        )
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        self.what_to_eat_data: list = []

    async def initialize(self) -> None:
        """插件激活时加载持久化数据，并迁移旧版 JSON 文件。"""
        self.what_to_eat_data = self._load_food_json()

        await self._migrate_good_morning_json()

    async def terminate(self) -> None:
        pass

    # ── 迁移工具 ──────────────────────────────────────────────

    def _load_food_json(self) -> list:
        """读取 resources/food.json。"""
        path = self._plugin_dir / "resources" / "food.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))["data"]
        except Exception as e:  # noqa: BLE001
            logger.warning("[essential] 读取 food.json 失败: %s", e)
            return []

    def _save_food_json(self) -> None:
        """将食物列表写回 resources/food.json。"""
        path = self._plugin_dir / "resources" / "food.json"
        try:
            path.write_text(
                json.dumps(
                    {"data": self.what_to_eat_data}, ensure_ascii=False, indent=2
                ),
                encoding="utf-8",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[essential] 写入 food.json 失败: %s", e)

    async def _migrate_good_morning_json(self) -> None:
        """从旧版 data/ 目录 JSON 迁移早晚安数据到 KV，按群拆分存储。

        旧版 key 格式为 unified_msg_origin（如 aiocqhttp:GROUP_MESSAGE:123456），
        迁移时提取末段 session_id 作为新 key，与 get_group_id() 返回值一致。
        私聊场景 session_id 为 user_id，新版降级用 unified_msg_origin，
        格式不同故私聊历史数据无法自动对齐，迁移后将被忽略（影响极小）。
        """
        old_path = Path(f"{_DATA_DIR}/{self.PLUGIN_NAME}_data.json")
        if not old_path.exists():
            return
        sentinel = await self.get_kv_data(_GOOD_MORNING_PREFIX + "__migrated__", None)
        if sentinel is not None:
            return
        try:
            raw = json.loads(old_path.read_text(encoding="utf-8"))
            data = raw.get("good_morning", raw) if isinstance(raw, dict) else {}
            for old_key, users in data.items():
                # 'platform:type:session_id' -> 'session_id'
                parts = old_key.split(":", 2)
                group_id = parts[2] if len(parts) == 3 else old_key
                await self.put_kv_data(_GOOD_MORNING_PREFIX + group_id, users)
            # 写入迁移完成标志
            await self.put_kv_data(_GOOD_MORNING_PREFIX + "__migrated__", True)
            old_path.rename(str(old_path) + ".migrated")
            logger.info(
                "[essential] 早晚安数据已从 JSON 迁移到 KV 存储（%d 个群）", len(data)
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[essential] 迁移 good_morning JSON 失败: %s", e)

    # ── 辅助方法 ──────────────────────────────────────────────

    def _get_report_font_size(self) -> int:
        size = self.config.get("report_font_size", 65)
        try:
            size = int(size)
        except (TypeError, ValueError):
            return 65
        return size if size > 0 else 65

    def time_convert(self, t: float) -> str:
        m, s = divmod(t, 60)
        return f"{int(m)}分{int(s)}秒"

    def check_good_morning_cd(
        self, user_id: str, current_time: datetime.datetime
    ) -> bool:
        """检查用户是否在 CD 中，True 表示仍在 CD。"""
        last_time = self.good_morning_cd.get(user_id)
        if last_time is None:
            return False
        return (current_time - last_time).total_seconds() < _GOOD_MORNING_CD_SECONDS

    def update_good_morning_cd(
        self, user_id: str, current_time: datetime.datetime
    ) -> None:
        """更新用户的 CD 时间。"""
        self.good_morning_cd[user_id] = current_time

    # ── 命令处理 ──────────────────────────────────────────────

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_poke(self, message: AstrMessageEvent):
        """处理戳一戳事件，随机回复一句话。"""
        message_obj = message.message_obj
        for component in message_obj.message:
            # 只响应戳自己的事件（target_id 为 bot 自身）
            if isinstance(component, Poke) and str(component.id) == str(
                message_obj.self_id
            ):
                return CommandResult().message(self._poke.random_reply())
        return None

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_search_anime(self, message: AstrMessageEvent):
        """拦截搜番等待期间的图片消息。"""
        sender = message.get_sender_id()
        if sender not in self.search_anmime_demand_users:
            return None

        message_obj = message.message_obj
        url = "https://api.trace.moe/search?anilistInfo&url="
        image_obj = None
        for component in message_obj.message:
            if isinstance(component, Image):
                image_obj = component
                break

        def _cleanup() -> None:
            self.search_anmime_demand_users.pop(sender, None)

        try:
            if image_obj is None:
                _cleanup()
                return CommandResult().error("未检测到图片，请发送一张图片进行搜番。")

            try:
                url += urllib.parse.quote(image_obj.url)
            except Exception:  # noqa: BLE001
                _cleanup()
                return CommandResult().error(
                    f"发现不受支持的图片数据：{type(image_obj)}，无法解析。"
                )

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != _HTTP_OK:
                        _cleanup()
                        return CommandResult().error("请求失败")
                    data = await resp.json()

            if data["result"]:
                result = data["result"][0]
                result["from"] = self.time_convert(result["from"])
                result["to"] = self.time_convert(result["to"])
                warn = ""
                if float(result["similarity"]) < _SIMILARITY_WARN_THRESHOLD:
                    warn = (
                        "相似度过低，可能不是同一番剧。"
                        "建议：相同尺寸大小的截图; 去除四周的黑边\n\n"
                    )
                _cleanup()
                return CommandResult(
                    chain=[
                        Plain(
                            f"{warn}番名: {result['anilist']['title']['native']}\n"
                            f"相似度: {result['similarity']}\n"
                            f"剧集: 第{result['episode']}集\n"
                            f"时间: {result['from']} - {result['to']}\n"
                            "精准空降截图:"
                        ),
                        Image.fromURL(result["image"]),
                    ],
                    use_t2i_=False,
                )
            _cleanup()
            return CommandResult().message("没有找到番剧")

        except Exception:
            _cleanup()
            raise

    @filter.command("喜报", desc="生成喜报图片。用法：/喜报 <内容>")
    async def congrats(self, message: AstrMessageEvent):
        """喜报生成器。"""
        msg = message.message_str[len("喜报") :].strip()
        msg = "\n".join(msg[i : i + 20] for i in range(0, len(msg), 20))

        img = PILImage.open(self._plugin_dir / "congrats.jpg")
        draw = PILImageDraw.Draw(img)
        font = PILImageFont.truetype(
            str(self._plugin_dir / "simhei.ttf"), self._get_report_font_size()
        )
        text_width, text_height = draw.textbbox((0, 0), msg, font=font)[2:4]
        draw.text(
            ((img.size[0] - text_width) / 2, (img.size[1] - text_height) / 2),
            msg,
            font=font,
            fill=(255, 0, 0),
            stroke_width=3,
            stroke_fill=(255, 255, 0),
        )
        out_path = self._cache_dir / f"congrats_{message.get_sender_id()}.jpg"
        img.save(str(out_path))
        return CommandResult().file_image(str(out_path))

    @filter.command("悲报", desc="生成悲报图片。用法：/悲报 <内容>")
    async def uncongrats(self, message: AstrMessageEvent):
        """悲报生成器。"""
        msg = message.message_str[len("悲报") :].strip()
        msg = "\n".join(msg[i : i + 20] for i in range(0, len(msg), 20))

        img = PILImage.open(self._plugin_dir / "uncongrats.jpg")
        draw = PILImageDraw.Draw(img)
        font = PILImageFont.truetype(
            str(self._plugin_dir / "simhei.ttf"), self._get_report_font_size()
        )
        text_width, text_height = draw.textbbox((0, 0), msg, font=font)[2:4]
        draw.text(
            ((img.size[0] - text_width) / 2, (img.size[1] - text_height) / 2),
            msg,
            font=font,
            fill=(0, 0, 0),
            stroke_width=3,
            stroke_fill=(255, 255, 255),
        )
        out_path = self._cache_dir / f"uncongrats_{message.get_sender_id()}.jpg"
        img.save(str(out_path))
        return CommandResult().file_image(str(out_path))

    @filter.command("moe", desc="随机获取一张动漫图片。")
    async def get_moe(self, message: AstrMessageEvent):
        """随机动漫图片。"""
        shuffle = random.sample(self.moe_urls, len(self.moe_urls))
        data: Optional[bytes] = None
        for url in shuffle:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != _HTTP_OK:
                            logger.warning(
                                "[essential] %s 返回 %s，尝试下一个", url, resp.status
                            )
                            continue
                        data = await resp.read()
                        break
            except Exception as e:  # noqa: BLE001
                logger.error("[essential] 从 %s 获取图片失败: %s，尝试下一个", url, e)
                continue

        if data is None:
            return CommandResult().error("所有图片源均不可用，请稍后再试")

        out_path = self._cache_dir / f"moe_{message.get_sender_id()}.jpg"
        out_path.write_bytes(data)
        return CommandResult().file_image(str(out_path))

    @filter.command(
        "搜番",
        desc="以图搜番。发送指令后，30 秒内发一张截图即可识别番剧名称和出处。",
    )
    async def get_search_anime(self, message: AstrMessageEvent):
        """以图搜番。"""
        sender = message.get_sender_id()
        if sender in self.search_anmime_demand_users:
            yield message.plain_result("正在等你发图喵，请不要重复发送")
            return
        self.search_anmime_demand_users[sender] = False
        yield message.plain_result("请在 30 喵内发送一张图片让我识别喵")
        await asyncio.sleep(30)
        if sender in self.search_anmime_demand_users:
            if self.search_anmime_demand_users[sender]:
                del self.search_anmime_demand_users[sender]
                return
            del self.search_anmime_demand_users[sender]
            yield message.plain_result("🧐你没有发送图片，搜番请求已取消了喵")

    @filter.command("mcs", desc="查询 Minecraft 服务器状态。用法：/mcs <服务器地址>")
    async def mcs(self, message: AstrMessageEvent):
        """查询 Minecraft 服务器状态。"""
        message_str = message.message_str
        if message_str.strip() == "mcs":
            return CommandResult().error("查 Minecraft 服务器。格式: /mcs [服务器地址]")
        ip = message_str[len("mcs") :].strip()
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.mcsrvstat.us/2/{ip}") as resp:
                if resp.status != _HTTP_OK:
                    return CommandResult().error("请求失败")
                data = await resp.json()
                logger.info("[essential] 获取到 %s 的服务器信息", ip)

        if "error" in data:
            return CommandResult().error(f"查询失败: {data['error']}")

        # 预处理 MOTD：过滤 Minecraft 颜色代码和空行
        _mc_color_re = re.compile(r"§[0-9a-fk-or]", re.IGNORECASE)
        _raw_motd = (
            data.get("motd", {}).get("clean", [])
            if isinstance(data.get("motd"), dict)
            else []
        )
        _motd_lines = [
            _mc_color_re.sub("", line).strip()
            for line in _raw_motd
            if isinstance(line, str) and _mc_color_re.sub("", line).strip()
        ]
        _protocol = data.get("protocol")
        _mcs_tmpl_data = {
            "icon": data.get("icon", ""),
            "server_name": _motd_lines[0] if _motd_lines else ip,
            "motd_lines": _motd_lines[1:] if len(_motd_lines) > 1 else [],
            "players": data.get("players", {"online": 0, "max": 0}),
            "version": data.get("version", "未知"),
            "protocol_name": _protocol.get("name", "未知")
            if isinstance(_protocol, dict)
            else str(_protocol)
            if _protocol
            else "未知",
            "ip": ip,
            "port": data.get("port", 25565),
            "online": data.get("online", False),
        }
        if self.mc_html_tmpl:
            try:
                img_path = await html_renderer.render_custom_template(
                    tmpl_str=self.mc_html_tmpl,
                    options={"quality": 90, "deviceScaleFactor": 2},
                    tmpl_data=_mcs_tmpl_data,
                )
                return CommandResult().file_image(img_path)
            except Exception as e:  # noqa: BLE001
                logger.warning("[essential] mcs HTML 渲染失败，降级为纯文本: %s", e)

        motd = "查询失败"
        if (
            "motd" in data
            and isinstance(data["motd"], dict)
            and isinstance(data["motd"].get("clean"), list)
        ):
            motd_lines = [
                line.strip()
                for line in data["motd"]["clean"]
                if isinstance(line, str) and line.strip()
            ]
            motd = "\n".join(motd_lines) if motd_lines else "查询失败"

        players = "查询失败"
        name_list: list = []
        if "players" in data:
            players = f"{data['players']['online']}/{data['players']['max']}"
            name_list = data["players"].get("list", [])

        version = str(data["version"]) if "version" in data else "查询失败"
        status = "🟢" if data["online"] else "🔴"
        name_list_str = "\n".join(name_list) if name_list else "无玩家在线"

        result_text = (
            "【查询结果】\n"
            f"状态: {status}\n"
            f"服务器IP: {ip}\n"
            f"版本: {version}\n"
            f"MOTD: {motd}\n"
            f"玩家人数: {players}\n"
            f"在线玩家: \n{name_list_str}"
        )
        return CommandResult().message(result_text).use_t2i(False)  # noqa: FBT003

    @filter.command("一言", desc="随机获取一句话。")
    async def hitokoto(self, message: AstrMessageEvent):  # noqa: ARG002
        """来一条一言。"""
        async with aiohttp.ClientSession() as session:
            async with session.get("https://v1.hitokoto.cn") as resp:
                if resp.status != _HTTP_OK:
                    return CommandResult().error("请求失败")
                data = await resp.json()
        return CommandResult().message(data["hitokoto"] + " —— " + data["from"])

    def _save_food_data(self) -> None:
        self._save_food_json()

    @filter.command(
        "今天吃什么",
        desc="随机选择今天吃什么。支持添加/删除：/今天吃什么 添加 食物1 食物2 | /今天吃什么 删除 食物1",
    )
    async def what_to_eat(self, message: AstrMessageEvent):
        """随机选择今天吃什么，支持添加/删除食物。"""
        parts = message.message_str.split()

        if "添加" in message.message_str:
            if len(parts) < _MIN_CMD_PARTS:
                return CommandResult().error(
                    "格式：今天吃什么 添加 [食物1] [食物2] ..."
                )
            self.what_to_eat_data += parts[2:]
            self._save_food_data()
            return CommandResult().message("添加成功")

        if "删除" in message.message_str:
            if len(parts) < _MIN_CMD_PARTS:
                return CommandResult().error(
                    "格式：今天吃什么 删除 [食物1] [食物2] ..."
                )
            for item in parts[2:]:
                if item in self.what_to_eat_data:
                    self.what_to_eat_data.remove(item)
            self._save_food_data()
            return CommandResult().message("删除成功")

        if not self.what_to_eat_data:
            return CommandResult().error(
                "食物列表为空，请先用「今天吃什么 添加 ...」添加一些食物！"
            )

        return CommandResult().message(
            f"今天吃 {random.choice(self.what_to_eat_data)}！"
        )

    @filter.command("喜加一", desc="查询 EPIC 当前及即将免费的游戏。")
    async def epic_free_game(self, message: AstrMessageEvent):  # noqa: ARG002
        """EPIC 喜加一。"""
        epic_url = (
            "https://store-site-backend-static-ipv4.ak.epicgames.com"
            "/freeGamesPromotions"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(epic_url) as resp:
                if resp.status != _HTTP_OK:
                    return CommandResult().error("请求失败")
                data = await resp.json()

        games: list = []
        upcoming: list = []

        for game in data["data"]["Catalog"]["searchStore"]["elements"]:
            title = game.get("title", "未知")
            try:
                if not game.get("promotions"):
                    continue

                fmtprice = game["price"]["totalPrice"]["fmtPrice"]
                original_price = fmtprice["originalPrice"]
                discount_price = fmtprice["discountPrice"]
                promotions = game["promotions"]["promotionalOffers"]
                upcoming_promotions = game["promotions"]["upcomingPromotionalOffers"]

                if not promotions and not upcoming_promotions:
                    continue

                offers = (
                    promotions[0].get("promotionalOffers", [])
                    if promotions
                    else upcoming_promotions[0].get("promotionalOffers", [])
                )
                if not offers:
                    continue

                promotion = offers[0]
                start_utc8 = datetime.datetime.strptime(
                    promotion["startDate"], "%Y-%m-%dT%H:%M:%S.%fZ"
                ) + datetime.timedelta(hours=8)
                end_utc8 = datetime.datetime.strptime(
                    promotion["endDate"], "%Y-%m-%dT%H:%M:%S.%fZ"
                ) + datetime.timedelta(hours=8)

                if float(promotion["discountSetting"]["discountPercentage"]) != 0:
                    continue

                entry = (
                    f"【{title}】\n"
                    f"原价: {original_price} | 现价: {discount_price}\n"
                    f"活动时间: {start_utc8.strftime('%Y-%m-%d %H:%M')}"
                    f" - {end_utc8.strftime('%Y-%m-%d %H:%M')}"
                )
                if promotions:
                    games.append(entry)
                else:
                    upcoming.append(entry)

            except Exception as e:  # noqa: BLE001
                logger.warning("[essential] 处理游戏 %s 时出错: %s", title, e)
                continue

        if not games:
            return CommandResult().message("暂无免费游戏")

        return (
            CommandResult()
            .message(
                "【EPIC 喜加一】\n"
                + "\n\n".join(games)
                + "\n\n【即将免费】\n"
                + "\n\n".join(upcoming)
            )
            .use_t2i(False)  # noqa: FBT003
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command(
        "清除缓存", desc="（仅管理员）清除喜报、悲报、moe 的本地图片缓存文件。"
    )
    async def clear_cache(self, message: AstrMessageEvent):  # noqa: ARG002
        """清除喜报/悲报/moe 的图片缓存文件。"""
        files = list(self._cache_dir.glob("*.jpg"))
        deleted = 0
        for f in files:
            f.unlink(missing_ok=True)
            deleted += 1
        return CommandResult().message(f"已清除 {deleted} 个缓存文件。")

    @filter.regex(r"^(早安|晚安)")
    async def good_morning(self, message: AstrMessageEvent):
        """和 Bot 说早晚安，记录睡眠时间，培养良好作息。"""
        # CREDIT: 灵感部分借鉴自 https://github.com/MinatoAquaCrews/nonebot_plugin_morning

        group_id = message.get_group_id() or message.unified_msg_origin
        user_id = message.message_obj.sender.user_id
        user_name = message.message_obj.sender.nickname
        curr_utc8 = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=8))
        )
        curr_human = curr_utc8.strftime("%Y-%m-%d %H:%M:%S")
        curr_date_str = curr_utc8.strftime("%Y-%m-%d")

        if self.check_good_morning_cd(user_id, curr_utc8):
            return (
                CommandResult()
                .message("你刚刚已经说过早安/晚安了，请30分钟后再试喵~")
                .use_t2i(False)  # noqa: FBT003
            )

        is_night = "晚安" in message.message_str

        kv_key = _GOOD_MORNING_PREFIX + group_id
        umo = await self.get_kv_data(kv_key, {})
        if not isinstance(umo, dict):
            logger.warning("[essential] KV 数据异常（key=%s），已重置", kv_key)
            umo = {}
        user = umo.get(
            user_id,
            {"daily": {"morning_time": "", "night_time": ""}},
        )

        if is_night:
            user["daily"]["night_time"] = curr_human
            user["daily"]["morning_time"] = ""
        else:
            user["daily"]["morning_time"] = curr_human

        umo[user_id] = user
        await self.put_kv_data(kv_key, umo)
        self.update_good_morning_cd(user_id, curr_utc8)

        if not is_night:
            sleep_duration_human = ""
            if user["daily"]["night_time"]:
                night_dt = datetime.datetime.strptime(
                    user["daily"]["night_time"], "%Y-%m-%d %H:%M:%S"
                )
                morning_dt = datetime.datetime.strptime(
                    user["daily"]["morning_time"], "%Y-%m-%d %H:%M:%S"
                )
                sleep_seconds = (morning_dt - night_dt).total_seconds()
                if 0 < sleep_seconds <= _MAX_SLEEP_HOURS * 3600:
                    hrs = int(sleep_seconds / 3600)
                    mins = int((sleep_seconds % 3600) / 60)
                    sleep_duration_human = f"{hrs}小时{mins}分"

            return (
                CommandResult()
                .message(
                    f"早上好喵，{user_name}！\n"
                    f"现在是 {curr_human}，昨晚你睡了 {sleep_duration_human}。"
                )
                .use_t2i(False)  # noqa: FBT003
            )

        # 统计今日睡觉人数
        curr_day_sleeping = 0
        for v in umo.values():
            if v["daily"]["night_time"] and not v["daily"]["morning_time"]:
                night_date = datetime.datetime.strptime(
                    v["daily"]["night_time"], "%Y-%m-%d %H:%M:%S"
                ).strftime("%Y-%m-%d")
                if night_date == curr_date_str:
                    curr_day_sleeping += 1

        return (
            CommandResult()
            .message(
                f"快睡觉喵，{user_name}！\n"
                f"现在是 {curr_human}，你是本群今天第 {curr_day_sleeping} 个睡觉的。"
            )
            .use_t2i(False)  # noqa: FBT003
        )
