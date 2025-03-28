import geopandas as gpd
import stacrs
from pystac import Item

async def get_land_prod_data(year: int, bbox:gpd.GeoDataFrame) -> list[Item]:

    # Find Items that intersect the bounding box and time period
    item_dicts = await stacrs.search(
        "https://data.ldn.auspatious.com/geo_ls_lp/geo_ls_lp_0_1_0.parquet",
        bbox=bbox.total_bounds,
        datetime=f"{year}-01-01T00:00:00.000Z/{year}-12-31T23:59:59.999Z",
    )
    items: list[Item] = [Item.from_dict(d) for d in item_dicts]

    print(type(items))
    print(len(items))


    return items