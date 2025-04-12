import fused

@fused.udf
async def udf(
    bounds: fused.types.TileGDF = None,
    year: int = 2023,
    variable: str = "evi2",
    # variable: str = "sif_740",
):
    "This 'WORKS' but is SUPER distorted"
    import os
    from dotenv import load_dotenv

    import odc.stac
    import numpy as np
    import xarray as xr
    import rioxarray
    import pystac
    from scipy.interpolate import griddata

    import geopandas as gpd
    import shapely

    env_file_path = '/tmp/.env'
    load_dotenv(env_file_path, override=True)
    # for k in os.environ:
    #     print(f"xx {k}")    
    auth = os.getenv("NASA_AUTH_STR")
    get_sif_data = fused.load(
        "https://github.com/KeynesYouDigIt/udfs/tree/0a4d65597ba8dd637a4417080f5127d538f75180/community/KeynesYouDigIt/STAC_SIF_and_land"
    ).utils.get_sif_data

    visualize = fused.load(
        "https://github.com/fusedio/udfs/tree/5cfb808/public/common/"
    ).utils.visualize


    # TODO - don't hardcode bbox
    print("GRABBING BBOX")
    # Ridiculous and silly guess at QR/BZ Farmland for a POC
    mex_box = gpd.GeoDataFrame(
        {"x": [115], "y": [229], "z": [9]}, 
        geometry=[
            shapely.box(
                -89.149375,
                17.798733095556155,
                -88.90090625,
                18.0834624514267062
            )
        ],
        crs=4326)

    print("GRABBING LAND PROD DATA")

    import inspect

    import stacrs
    print(inspect.iscoroutinefunction(stacrs.search))  # Should return True

    item_dicts = stacrs.search(
        "https://data.ldn.auspatious.com/geo_ls_lp/geo_ls_lp_0_1_0.parquet",
        bbox=mex_box.total_bounds,
        datetime=f"{year}-01-01T00:00:00.000Z/{year}-12-31T23:59:59.999Z",
    )
    lpd = [pystac.Item.from_dict(d) for d in item_dicts]

    # Make me a for loop
    # save and add assets (it1.SIF_740, it1.SIF-Unadjusted)
    
    for lpd_item in lpd:
        print(f"current item {lpd_item}")
        # NOTE overlap_buffer_size is very liberal right now!!!
        # might look into shrinking if necessary.
        # review after .visualize is complete
        # -- (is it distorted? too big? should be bigger than other lpd vars like ndvi, evi2)
        # THIS IS ASSUMING 4326 (but its not clear if theres a way to confirm the CRS anyways...)
        print("GRABBING SIF DATA")
        sif_matching = get_sif_data(auth=auth, bbox=lpd_item.bbox, overlap_buffer_size=10)

        # Convert SIF data to raster using interpolation
        x_array = sif_matching['x'].values
        y_array = sif_matching['y'].values
        sif_values = sif_matching['SIF_740'].values
        grid_resolution = 0.01

        # Create a grid of lat/long coordinates
        grid_x = np.arange(x_array.min(), x_array.max(), grid_resolution)
        grid_y = np.arange(y_array.min(), y_array.max(), grid_resolution)
        grid_x, grid_y = np.meshgrid(grid_x, grid_y)

        # Interpolate the SIF values onto the grid
        grid_sif = griddata(
            points=(x_array, y_array),
            values=sif_values,
            xi=(grid_x, grid_y),
            method='linear',  # Interpolation method (linear, nearest, cubic)
            fill_value=np.nan  # might need to be 0? we'll see how tif/visualizer does with nans
        )

        raster = xr.DataArray(
            grid_sif,
            dims=['y', 'x'],
            coords={
                'y': grid_y[:, 0],  # Latitude coordinates
                'x': grid_x[0, :]   # Longitude coordinates
            }
        )
        raster = raster.rio.set_spatial_dims(x_dim='x', y_dim='y')
        raster.rio.write_crs('EPSG:4326', inplace=True)  # WGS84

        # Save as a GeoTIFF
        
        sif_raster_path = f'{lpd_item.id}_sif_740_rasterized.tif'
        full_local_path = os.path.abspath(sif_raster_path)
        raster.rio.to_raster(full_local_path)
        # TODO --- if its a good idea, upload to s3 instead of this local thing
        lpd_item.add_asset(
            'sif_740',  # Key for the asset
            pystac.Asset(
                href=full_local_path,
                media_type='image/tiff; application=geotiff',
                roles=['data']
            )
        )

    power = 13 - mex_box.z[0]
    resolution = 30 if power < 0 else int(20 * 2**power)


    data = odc.stac.load(
        lpd,
        crs="EPSG:3857",   #"EPSG:4326",  ### HUGE ISSUE ----- RECAST IF NEEDED PLS. "EPSG:3857",
        bands=[variable], # ['sif_740'], # ['ndvi'],
        resolution=resolution,
        bbox=mex_box.total_bounds,
    ).squeeze()

    import palettable
    # Create a mask where data is nan
    mask = (~data[variable].isnull()).squeeze().to_numpy()

    # Visualize that data as an RGB image.
    rgb_image = visualize(
        data=data[variable],
        mask=mask,
        min=0,
        max=360,
        colormap=palettable.matplotlib.Viridis_20,
    )

    return rgb_image