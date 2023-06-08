import requests
from nakuru.entities.components import *

def get_search_anime(message_obj, busy, qq_platform = None):
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
                    data["result"][0]["from"] = time_convert(data["result"][0]["from"])
                    data["result"][0]["to"] = time_convert(data["result"][0]["to"])

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