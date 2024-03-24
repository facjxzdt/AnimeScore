import redis
import redis.commands.search.aggregation as aggregations
import redis.commands.search.reducers as reducers
from redis.commands.json.path import Path
from redis.commands.search.field import NumericField, TagField, TextField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query

r = redis.Redis(
  host='r-bp1nx2ynbs04qs0wv2pd.redis.rds.aliyuncs.com',
  port=6379,
  password='18730424270smj',
  decode_responses=True
)

schema = (
  NumericField("$.ank_score", as_name="ank_score"),
  NumericField("$.ank_score", as_name="ank_score"),
  NumericField("$.ank_score", as_name="ank_score"),
  NumericField("$.ank_score", as_name="ank_score")
)