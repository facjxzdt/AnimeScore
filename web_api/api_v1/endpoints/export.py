"""Export current data instead of serving obsolete checked-in score files."""

import csv
import io
import json
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import Response

from services.catalog import ATTRIBUTION, get_repository
from web_api.api_v1.deps import cached_items, get_airing_items, get_subscribed_items

router = APIRouter()
ExportType = Literal["airing", "subscribed", "all"]


def export_items(kind: str) -> list[dict]:
    if kind == "subscribed":
        return get_subscribed_items()
    if kind == "all":
        return cached_items(get_repository().snapshot().entries)
    return get_airing_items()


@router.get("/json")
def export_json(type: ExportType = "airing"):
    items = export_items(type)
    content = json.dumps({"source": ATTRIBUTION, "items": items, "total": len(items)}, ensure_ascii=False)
    return Response(content, media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{type}_anime.json"'})


@router.get("/csv")
def export_csv(type: ExportType = "airing"):
    output = io.StringIO(newline="")
    fields = ["name", "name_cn", "name_en", "type", "begin", "bgm_id", "mal_id", "anilist_id",
              "bgm", "mal", "anilist", "total", "data_source"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in export_items(type):
        row = {**item, **item.get("ids", {}), **item.get("scores", {})}
        # Spreadsheet programs can otherwise execute upstream titles as formulas.
        row = {key: "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
               for key, value in row.items()}
        writer.writerow(row)
    return Response("\ufeff" + output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{type}_anime.csv"'})
