from . import _ncomp
from .version import __version__
import numpy as np
import xarray as xr
import dask.array as da
from dask.array.core import map_blocks

class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class ChunkError(Error):
    """Exception raised when a Dask array is chunked in a way that is
    incompatible with an _ncomp function."""
    pass

def linint2(fi, xo, yo, icycx, msg=None, meta=True, xi=None, yi=None):
    """Interpolates a regular grid to a rectilinear one using bi-linear
    interpolation.

    linint2 uses bilinear interpolation to interpolate from one
    rectilinear grid to another. The input grid may be cyclic in the x
    direction. The interpolation is first performed in the x direction,
    and then in the y direction.

    Args:

        fi (:class:`xarray.DataArray` or :class:`numpy.ndarray`):
            An array of two or more dimensions. If xi is passed in as an
            argument, then the size of the rightmost dimension of fi
            must match the rightmost dimension of xi. Similarly, if yi
            is passed in as an argument, then the size of the second-
            rightmost dimension of fi must match the rightmost dimension
            of yi.

            If missing values are present, then linint2 will perform the
            bilinear interpolation at all points possible, but will
            return missing values at coordinates which could not be
            used.

            Note:

                This variable must be
                supplied as a :class:`xarray.DataArray` in order to copy
                the dimension names to the output. Otherwise, default
                names will be used.

        xo (:class:`xarray.DataArray` or :class:`numpy.ndarray`):
            A one-dimensional array that specifies the X coordinates of
            the return array. It must be strictly monotonically
            increasing, but may be unequally spaced.

            For geo-referenced data, xo is generally the longitude
            array.

            If the output coordinates (xo) are outside those of the
            input coordinates (xi), then the fo values at those
            coordinates will be set to missing (i.e. no extrapolation is
            performed).

        yo (:class:`xarray.DataArray` or :class:`numpy.ndarray`):
            A one-dimensional array that specifies the Y coordinates of
            the return array. It must be strictly monotonically
            increasing, but may be unequally spaced.

            For geo-referenced data, yo is generally the latitude array.

            If the output coordinates (yo) are outside those of the
            input coordinates (yi), then the fo values at those
            coordinates will be set to missing (i.e. no extrapolation is
            performed).

        icycx (:obj:`bool`):
            An option to indicate whether the rightmost dimension of fi
            is cyclic. This should be set to True only if you have
            global data, but your longitude values don't quite wrap all
            the way around the globe. For example, if your longitude
            values go from, say, -179.75 to 179.75, or 0.5 to 359.5,
            then you would set this to True.

        msg (:obj:`numpy.number`):
            A numpy scalar value that represent a missing value in fi.
            This argument allows a user to use a missing value scheme
            other than NaN or masked arrays, similar to what NCL allows.

        meta (:obj:`bool`):
            Set to False to disable metadata; default is True.

        xi (:class:`numpy.ndarray`):
            An array that specifies the X coordinates of the fi array.
            Most frequently, this is a 1D strictly monotonically
            increasing array that may be unequally spaced. In some
            cases, xi can be a multi-dimensional array (see next
            paragraph). The rightmost dimension (call it nxi) must have
            at least two elements, and is the last (fastest varying)
            dimension of fi.

            If xi is a multi-dimensional array, then each nxi subsection
            of xi must be strictly monotonically increasing, but may be
            unequally spaced. All but its rightmost dimension must be
            the same size as all but fi's rightmost two dimensions.

            For geo-referenced data, xi is generally the longitude
            array.

            Note:
                If left unspecified, the rightmost coordinate dimension
                of fi will be used. This parameter must be specified as
                a keyword argument.

        yi (:class:`numpy.ndarray`):
            An array that specifies the Y coordinates of the fi array.
            Most frequently, this is a 1D strictly monotonically
            increasing array that may be unequally spaced. In some
            cases, yi can be a multi-dimensional array (see next
            paragraph). The rightmost dimension (call it nyi) must have
            at least two elements, and is the second-to-last dimension
            of fi.

            If yi is a multi-dimensional array, then each nyi subsection
            of yi must be strictly monotonically increasing, but may be
            unequally spaced. All but its rightmost dimension must be
            the same size as all but fi's rightmost two dimensions.

            For geo-referenced data, yi is generally the latitude array.

            Note:
                If left unspecified, the second-to-rightmost coordinate
                dimension of fi will be used. This parameter must be
                specified as a keyword argument.

    Returns:
        :class:`xarray.DataArray`: The interpolated grid. If the *meta*
        parameter is True, then the result will include named dimensions
        matching the input array. The returned value will have the same
        dimensions as fi, except for the rightmost two dimensions which
        will have the same dimension sizes as the lengths of yo and xo.
        The return type will be double if fi is double, and float
        otherwise.

    Examples:

        Example 1: Using linint2 with :class:`xarray.DataArray` input

        .. code-block:: python

            import numpy as np
            import xarray as xr
            import geocat.comp

            fi_np = np.random.rand(30, 80)  # random 30x80 array

            # xi and yi do not have to be equally spaced, but they are
            # in this example
            xi = np.arange(80)
            yi = np.arange(30)

            # create target coordinate arrays, in this case use the same
            # min/max values as xi and yi, but with different spacing
            xo = np.linspace(xi.min(), xi.max(), 100)
            yo = np.linspace(yi.min(), yi.max(), 50)

            # create :class:`xarray.DataArray` and chunk it using the
            # full shape of the original array.
            # note that xi and yi are attached as coordinate arrays
            fi = xr.DataArray(fi_np,
                              dims=['lat', 'lon'],
                              coords={'lat': yi, 'lon': xi}
                             ).chunk(fi_np.shape)

            fo = geocat.comp.linint2(fi, xo, yo, 0)

    """

    if not isinstance(fi, xr.DataArray):
        fi = xr.DataArray(fi)

    if xi is None:
        xi = fi.coords[fi.dims[-1]].values
    elif isinstance(xi, xr.DataArray):
        xi = xi.values

    if yi is None:
        yi = fi.coords[fi.dims[-2]].values
    elif isinstance(yi, xr.DataArray):
        yi = yi.values

    # ensure xo and yo are numpy.ndarrays
    if isinstance(xo, xr.DataArray):
        xo = xo.values
    if isinstance(yo, xr.DataArray):
        yo = yo.values

    fi_data = fi.data

    if isinstance(fi_data, da.Array):
        chunks = list(fi.chunks)

        # ensure rightmost dimensions of input are not chunked
        if chunks[-2:] != [yi.shape, xi.shape]:
            raise ChunkError("linint2: the two rightmost dimensions of fi must"
                             " not be chunked.")

        # ensure rightmost dimensions of output are not chunked
        chunks[-2:] = (yo.shape, xo.shape)

        # map_blocks maps each chunk of fi_data to a separate invocation of
        # _ncomp._linint2. The "chunks" keyword argument should be the chunked
        # dimensionality of the expected output; the number of chunks should
        # match that of fi_data. Additionally, "drop_axis" and "new_axis" in
        # this case indicate that the two rightmost dimensions of the input
        # will be dropped from the output array, and that two new axes will be
        # added instead.
        fo = map_blocks(_ncomp._linint2, xi, yi, fi_data, xo, yo, icycx, msg,
                        chunks=chunks, dtype=fi.dtype,
                        drop_axis=[fi.ndim-2, fi.ndim-1],
                        new_axis=[fi.ndim-2, fi.ndim-1])
    elif isinstance(fi_data, np.ndarray):
        fo = _ncomp._linint2(xi, yi, fi_data, xo, yo, icycx, msg)
    else:
        raise TypeError

    if meta:
        coords = {k:v if k not in fi.dims[-2:]
                  else (xo if k == fi.dims[-1] else yo)
                  for (k, v) in fi.coords.items()}

        fo = xr.DataArray(fo, attrs=fi.attrs, dims=fi.dims,
                              coords=coords)
    else:
        fo = xr.DataArray(fo)

    return fo

def rcm2rgrid(lat2d, lon2d, fi, lat1d, lon1d, msg=None, meta=True, xi=None, yi=None):

    # Basic sanity checks
    if lat2d.shape[0] != lon2d.shape[0] or lat2d.shape[1] != lon2d.shape[1]:
        raise Exception("ERROR rcm2rgrid: The input lat/lon grids must be the same size !")

    if lat2d.shape[0] < 2 or lon2d.shape[0] < 2 or lat2d.shape[1] < 2 or lon2d.shape[1] < 2:
        raise Exception("ERROR rcm2rgrid: The input/output lat/lon grids must have at least 2 elements !")
        
    if fi.ndim < 2:
        raise Exception("ERROR rcm2rgrid: fi must be at least two dimensions !\n")

    if fi.shape[fi.ndim - 2] != lat2d.shape[0] or fi.shape[fi.ndim - 1] != lon2d.shape[1]:
        raise Exception("ERROR rcm2rgrid: The rightmost dimensions of fi must be (nlat2d x nlon2d),"
                        "where nlat2d and nlon2d are the size of the lat2d/lon2d arrays !")

    if lat2d[0,0] < lat2d[-1,0] and lat2d[0,1] < lat2d[-1,1]:
        raise Exception("ERROR rcm2rgrid: lat2d dimensions have to be ordered from south-to-north !")

    if lon2d[0,0] < lon2d[-1,0] and lon2d[0,1] < lon2d[-1,1]:
        raise Exception("ERROR rcm2rgrid: lon2d dimensions have to be ordered from west-to-east !")

    if isinstance(lat2d, xr.DataArray):
        lat2d = lat2d.values

    if isinstance(lon2d, xr.DataArray):
        lon2d = lon2d.values

    if not isinstance(fi, xr.DataArray):
        fi = xr.DataArray(fi)

    # ensure lat1d and lon1d are numpy.ndarrays
    if isinstance(lat1d, xr.DataArray):
        lat1d = lat1d.values
    if isinstance(lon1d, xr.DataArray):
        lon1d = lon1d.values

    fi_data = fi.data

    if isinstance(fi_data, da.Array):
        chunks = list(fi.chunks)

        # ensure rightmost dimensions of input are not chunked
        if chunks[-2:] != [lon2d.shape, lat2d.shape]:
            raise ChunkError("rcm2rgrid: the two rightmost dimensions of fi must"
                             " not be chunked.")

        # ensure rightmost dimensions of output are not chunked
        chunks[-2:] = (lon1d.shape, lat1d.shape)

        fo = map_blocks(_ncomp._rcm2rgrid, lat2d, lon2d, fi_data, lat1d, lon1d, msg,
                        chunks=chunks, dtype=fi.dtype,
                        drop_axis=[fi.ndim-2, fi.ndim-1],
                        new_axis=[fi.ndim-2, fi.ndim-1])
    elif isinstance(fi_data, np.ndarray):
        fo = _ncomp._rcm2rgrid(lat2d, lon2d, fi_data, lat1d, lon1d, msg)
    else:
        raise TypeError

    if meta:
        coords = {k:v if k not in fi.dims[-2:]
                  else (lat1d if k == fi.dims[-1] else lon1d)
                  for (k, v) in fi.coords.items()}

        fo = xr.DataArray(fo, attrs=fi.attrs, dims=fi.dims,
                          coords=coords)
    else:
        fo = xr.DataArray(fo)

    return fo

def rgrid2rcm(lat1d, lon1d, fi, lat2d, lon2d, msg=None, meta=True, xi=None, yi=None):

    # Basic sanity checks
    if lat2d.shape[0] != lon2d.shape[0] or lat2d.shape[1] != lon2d.shape[1]:
        raise Exception("ERROR rgrid2rcm: The output lat2D/lon2D grids must be the same size !")

    if lat2d.shape[0] < 2 or lon2d.shape[0] < 2 or lat2d.shape[1] < 2 or lon2d.shape[1] < 2:
        raise Exception("ERROR rgrid2rcm: The input/output lat/lon grids must have at least 2 elements !")
        
    if fi.ndim < 2:
        raise Exception("ERROR rgrid2rcm: fi must be at least two dimensions !\n")

    if fi.shape[fi.ndim - 2] != lat1d.shape[0] or fi.shape[fi.ndim - 1] != lon1d.shape[0]:
        raise Exception("ERROR rgrid2rcm: The rightmost dimensions of fi must be (nlat1d x nlon1d),"
                        "where nlat1d and nlon1d are the size of the lat1d/lon1d arrays !")

    if isinstance(lat1d, xr.DataArray):
        lat1d = lat1d.values

    if isinstance(lon1d, xr.DataArray):
        lon1d = lon1d.values

    if not isinstance(fi, xr.DataArray):
        fi = xr.DataArray(fi)

    # ensure lat2d and lon2d are numpy.ndarrays
    if isinstance(lat2d, xr.DataArray):
        lat2d = lat2d.values
    if isinstance(lon2d, xr.DataArray):
        lon2d = lon2d.values

    fi_data = fi.data

    if isinstance(fi_data, da.Array):
        chunks = list(fi.chunks)

        # ensure rightmost dimensions of input are not chunked
        if chunks[-2:] != [lon1d.shape, lat1d.shape]:
            raise ChunkError("rgrid2rcm: the two rightmost dimensions of fi must"
                             " not be chunked.")

        # ensure rightmost dimensions of output are not chunked
        chunks[-2:] = (lon2d.shape, lat2d.shape)

        fo = map_blocks(_ncomp._rgrid2rcm, lat1d, lon1d, fi_data, lat2d, lon2d, msg,
                        chunks=chunks, dtype=fi.dtype,
                        drop_axis=[fi.ndim-2, fi.ndim-1],
                        new_axis=[fi.ndim-2, fi.ndim-1])
    elif isinstance(fi_data, np.ndarray):
        fo = _ncomp._rgrid2rcm(lat1d, lon1d, fi_data, lat2d, lon2d, msg)
    else:
        raise TypeError

    if meta:
        coords = {k:v if k not in fi.dims[-2:]
                  else (lat2d if k == fi.dims[-1] else lon2d)
                  for (k, v) in fi.coords.items()}

        fo = xr.DataArray(fo, attrs=fi.attrs, dims=fi.dims,
                          coords=coords)
    else:
        fo = xr.DataArray(fo)

    return fo

