import base64
import json
import io
import os

import requests
import s3fs
import xarray as xr

def _retrieve_nasa_credentials() -> dict:
    """Makes the Oauth calls to authenticate with EDS and return a set of s3
    same-region, read-only credntials.
    """
    login_resp = requests.get(
        "https://data.ornldaac.earthdata.nasa.gov/s3credentials", allow_redirects=False
    )
    login_resp.raise_for_status()

    auth = os.getenv("NASA_AUTH_STR")
    if not auth:
        # see https://docs.fused.io/core-concepts/content-management/environment-variables/
        raise Exception("Must set auth for NASA SIF data!")

    encoded_auth = base64.b64encode(auth.encode("ascii"))

    auth_redirect = requests.post(
        login_resp.headers["location"],
        data={"credentials": encoded_auth},
        headers={"Origin": "https://data.ornldaac.earthdata.nasa.gov/s3credentials"},
        allow_redirects=False,
    )
    auth_redirect.raise_for_status()

    final = requests.get(auth_redirect.headers["location"], allow_redirects=False)

    results = requests.get(
        "https://data.ornldaac.earthdata.nasa.gov/s3credentials",
        cookies={"accessToken": final.cookies["accessToken"]},
    )
    results.raise_for_status()

    return json.loads(results.content)


def _detect_and_set_rio_data(sif_d: xr.Dataset) -> xr.Dataset:
    # KEY ASSUMPTION
    # The global coverage and instrument type (GOME-2) align with WGS84 usage
    # TODO - use some form of automated heuristic to detect CRS if reasonable.
    # TODO - find latitude and longitude labels in metadata if possible and use those.
    # TODO - figure out what to do with obs as a dim, if anything.

    sif_d = (
        sif_d.reset_coords(
            # Moves coordinates from being dimensions to being variables
            # TODO - double check if needed?
            ["Latitude", "Longitude"]
        )
        .set_index(
            # Sets LL as index for rio
            # TODO - double check if needed?
            obs=["Longitude", "Latitude"]
        )
        # .unstack(
        #     "obs"
        # )
        # Rename to what rio expects
        .rename({"Longitude": "x", "Latitude": "y"})
        .rio.write_crs("EPSG:4326")
        .assign_coords(
            {
                # Adds or updates coordinate variables in the format rio expects them in.
                "Latitude": ("y", sif_d["Latitude"].values),
                "Longitude": ("x", sif_d["Longitude"].values),
            }
        )
    )

    return sif_d


def get_sif_data(bbox: list[int], overlap_buffer_size: float = 3.0) -> xr.Dataset:

    credentials = _retrieve_nasa_credentials()
    access_key = credentials["accessKeyId"]
    secret_key = credentials["secretAccessKey"]
    session_token = credentials["sessionToken"]

    fs = s3fs.S3FileSystem(key=access_key, secret=secret_key, token=session_token)

    bucket_name = "ornl-cumulus-prod-protected"
    specific_object_key = "sif-esdr/17-MEASURES-0032/MetOpB_GOME2_SIF/data/NSIFv2.6.2.GOME-2B.20210607_all.nc"

    # TODO - more efficient way to DL/read this stuff?
    with fs.open(f"s3://{bucket_name}/{specific_object_key}", "rb") as s3_file:
        file_like = io.BytesIO(bytes(s3_file.read()))
        # https://docs.xarray.dev/en/stable/generated/xarray.open_mfdataset.html#xarray.open_mfdataset
        sif_d = xr.open_dataset(file_like, engine="h5netcdf")
        # with open(local_file_path, 'wb') as local_file:
        #    local_file_path = 'NSIFv2.6.2.GOME-2B.20210607_all.nc'
        #    local_file.write(s3_file.read())

    # We expand the bbox, just to make sure we get some data.
    lon_min, lat_min, lon_max, lat_max = [round(float(c), 7) for c in bbox] #.total_bounds]
    lon_min -= overlap_buffer_size
    lat_min -= overlap_buffer_size

    lon_max += overlap_buffer_size
    lat_max += overlap_buffer_size

    # Handle longitude wrapping if necessary
    # if lon_min < 0 and sif_d['Longitude'].min() >= 0:
    #     lon_min += 360
    #     lon_max += 360

    sif_d_within_box = sif_d.where(
        (sif_d.Latitude >= lat_min)
        & (sif_d.Latitude <= lat_max)
        & (sif_d.Longitude >= lon_min)
        & (sif_d.Longitude <= lon_max),
        drop=True,
    )

    return _detect_and_set_rio_data(sif_d_within_box)
