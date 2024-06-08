import redis
from redis.commands.search.field import NumericField

r = redis.Redis(
    host="r-bp1nx2ynbs04qs0wv2pd.redis.rds.aliyuncs.com",
    port=6379,
    password="18730424270smj",
    decode_responses=True,
)

schema = (
    NumericField("$.ank_score", as_name="ank_score"),
    NumericField("$.ank_score", as_name="ank_score"),
    NumericField("$.ank_score", as_name="ank_score"),
    NumericField("$.ank_score", as_name="ank_score"),
)
