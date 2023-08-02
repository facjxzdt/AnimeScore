# AnimeScore
***
### 它可以做什么
> 这是一个自动获取Bangumi放送中动画全球评分的脚本，并支持生成csv文件
> ，以及可以自定总分权重  

> 数据源:Bangumi Anilist Anikore Filmarks MyAnimeList

> #### 推荐环境:python3.11 
## 如何使用
### 1. 安装依赖
#### 在项目根目录下执行
    pip install -r requirements.txt

### 2.设置配置文件(可选)
> 一般来说，脚本的默认设置已经满足普通使用的需求，无需更改
#### 编辑`data`目录下的`config.py`
```python
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
log_level = "INFO"
```
`real_headers`:设置脚本访问网站时的header头  

`retry_max`:设置脚本重试次数  

`timeout`:设置脚本请求超时时间  

`time_sleep`:设置脚本请求失败后多长时间再次重试
### 如需自定义权重，请仿照默认权重进行设置
```python
weights_xxx = \
    {'bgm_score': 0.5, 'fm_score': 0.3, 'mal_score': 0.2}

weights = 'weights_xxx'
```
`weights_xxx`:你所自定义的权重名称

`weights = weights_xxx`:设置脚本所使用的权重

### 3.运行脚本
#### 在`app`目录下执行`python app.py`
### 注意：请确保电脑可以顺利访问数据源的五个网站
#### 待爬取完成后，在`data`文件夹里的`score.csv`就是输出结果

## 关于爬取失败的处理方法
> ### 1.由于本脚本使用Bangumi的日文原名进行精确查询，
> ### 未免会有爬取不到的情况，脚本使用`None`进行代替

> ### 2.国漫精确度非常低 里番不会进行爬取

> ### 3.如果在设置中设置了某个网站的权重，且某部动画缺
> ### 少该网站的评分信息，在总分栏以`None`代替

> ### 4.实测，Bangumi Myanimelist Filmarks精确度最高
> ### 若这三个站爬取不到，基本其他站点也爬取不到，要
> ### 不就是错误数据，故默认权重只启用了这三个站点

> ### 5.关于识别率：2023年7月新番 使用默认权重 出分率
> ### 约为65%

## TODO:
### 1.api实现
### 2.生成html