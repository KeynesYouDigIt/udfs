import fused

def udf(
    bbox: fused.types.TileGDF = None,
    year: int = 2023,
):
    import odc.stac
    import numpy as np
    import xarray as xr
    import rioxarray
    import pystac
    from scipy.interpolate import griddata

    # TODO - internal deps.
    # force add here or create importable-deps?
    # try the later first.
    from src.HARDCODEDBBOXES import get_default_bbox_qr_mex
    from src.LANDPROD_SEARCH_DONOTPUSH import get_land_prod_data
    from src.SIFDATAPRIVATEDONOTPUSH import get_sif_data


    # TODO - don't hardcode bbox
    print("GRABBING BBOX")
    mex_box = get_default_bbox_qr_mex()

    print("GRABBING LAND PROD DATA")
    import asyncio
    lpd = asyncio.run(get_land_prod_data(year=year, bbox=mex_box))
    return

    # Make me a for loop
    # save and add assets (it1.SIF_740, it1.SIF-Unadjusted)
    
    for lpd_item in lpd:
        # NOTE overlap_buffer_size is very liberal right now!!!
        # might look into shrinking if necessary.
        # review after .visualize is complete
        # -- (is it distorted? too big? should be bigger than other lpd vars like ndvi, evi2)
        # THIS IS ASSUMING 4326 (but its not clear if theres a way to confirm the CRS anyways...)
        print("GRABBING SIF DATA")
        sif_matching = get_sif_data(lpd_item.bbox, overlap_buffer_size=3)

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
        import os
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
        bands=['sif_740'], # ['sif_740'], # ['ndvi'],
        resolution=resolution,
        bbox=mex_box.total_bounds,
    ).squeeze()

    # TODO
    # FOR EACH 
    # check CRS
    # check relevant temporal data

if __name__ in "__main__":
    udf()