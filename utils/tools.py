import data.config
import httpx


class Tools:
    def __init__(self):
        self.chinese_threshold = data.config.chinese_check_threshold
        self.chinese_check_enable = data.config.enable_chinese_check

    def check_animes_name(
        self, animes_name: str
    ):  # 检测是否为中文(国漫识别率过低 中文字符串占75%以上即为国漫)
        if self.chinese_check_enable:
            chinese_char = 0
            for _char in animes_name:
                if "\u4e00" <= _char <= "\u9fa5":
                    chinese_char += 1
            if round(chinese_char / len(animes_name), 2) >= self.chinese_threshold:
                return False
        return True

    def check_net(self):
        url_list = [
            "https://www.anikore.jp",
            "https://graphql.anilist.co",
            "https://api.bgm.tv",
            "https://filmarks.com",
            "https://myanimelist.net",
        ]
        try:
            for i in range(0, 5):
                resp = httpx.get(url_list[i], timeout=data.config.timeout)
                resp.raise_for_status()
        except:
            return False
        return True
