# 设置headers头
real_headers = {'User-Agent':
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}

# 权重设置 默认中日英5:3:2
weights_default = \
    {'bgm_score': 0.5, 'fm_score': 0.3, 'mal_score': 0.2}  # 默认权重(使用bgm fm mal三家数据源)
weights_all = \
    {'bgm_score': 0.5, 'fm_score': 0.2, 'ank_score': 0.1, 'mal_score': 0.075, 'anl_score': 0.125}  # 五个站点都可用时的权重设置
weights_ank = \
    {'bgm_score': 0.5, 'fm_score': 0.2, 'ank_score': 0.1, 'mal_score': 0.2}  # 当anl不可用时
weights_anl = \
    {'bgm_score': 0.5, 'fm_score': 0.3, 'mal_score': 0.1, 'anl_score': 0.1}  # 当ank不可用时

weights = 'weights_default'

# 重试次数 时间
retry_max = 5
timeout = 10
time_sleep = 5

# 日志设置
log_level = "DEBUG"
# 是否启用国漫识别(当动画名中文字符达到阈值时跳过统计)
enable_chinese_check = False
# 国漫识别阈值
chinese_check_threshold = 0.75

#meilisearcch设置
meili_url = 'https://ms-5d76c6d3887c-4928.sgp.meilisearch.io'
meili_key = 'd1979b54ec31bf4b8c2150afa08c67207ed88fbe'

#api设置
key = 'test'
ttl = 600
max_size = 100