# 设置headers头
real_headers = {'User-Agent':
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}

# 权重设置 默认中日英5:3:2
weights_default = \
    {'bgm_score': 0.5, 'fm_score': 0.3, 'mal_score': 0.2}  # 默认权重(使用bgm fm mal三家数据源)
weight_all = \
    {'bgm_score': 0.5, 'fm_score': 0.2, 'ank_score': 0.1, 'mal_score': 0.075, 'anl_score': 0.125}  # 五个站点都可用时的权重设置
weight_ank = \
    {'bgm_score': 0.5, 'fm_score': 0.2, 'ank_score': 0.1, 'mal_score': 0.2}  # 当anl不可用时
weight_anl = \
    {'bgm_score': 0.5, 'fm_score': 0.3, 'mal_score': 0.1, 'anl_score': 0.1}  # 当ank不可用时

weights = 'weights_default'

#重试次数 时间
retry_max = 5
timeout = 10
time_sleep = 5