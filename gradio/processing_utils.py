from PIL import Image, ImageOps
from io import BytesIO
import base64
import requests
import tempfile
import shutil
import os
import numpy as np
from gradio import encryptor
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore") # Ignore pydub warning if ffmpeg is not installed
    from pydub import AudioSegment

#########################
# IMAGE PRE-PROCESSING
#########################
def decode_base64_to_image(encoding):
    content = encoding.split(';')[1]
    image_encoded = content.split(',')[1]
    return Image.open(BytesIO(base64.b64decode(image_encoded)))


def get_url_or_file_as_bytes(path):
    try:
        return requests.get(path).content
    except (requests.exceptions.MissingSchema, requests.exceptions.InvalidSchema):
        with open(path, "rb") as f:   
            return f.read()


def encode_url_or_file_to_base64(path, type="image", ext=None, header=True):
    try:
        requests.get(path)
        return encode_url_to_base64(path, type, ext, header)
    except (requests.exceptions.MissingSchema, requests.exceptions.InvalidSchema):
        return encode_file_to_base64(path, type, ext, header)


def encode_file_to_base64(f, type="image", ext=None, header=True):
    with open(f, "rb") as file:
        encoded_string = base64.b64encode(file.read())
        base64_str = str(encoded_string, 'utf-8')
        if not header:
            return base64_str
        if ext is None:
            ext = f.split(".")[-1]
        return "data:" + type + "/" + ext + ";base64," + base64_str


def encode_url_to_base64(url, type="image", ext=None, header=True):
    encoded_string = base64.b64encode(requests.get(url).content)
    base64_str = str(encoded_string, 'utf-8')
    if not header:
        return base64_str
    if ext is None:
        ext = url.split(".")[-1]
    return "data:" + type + "/" + ext + ";base64," + base64_str


def encode_plot_to_base64(plt):
    with BytesIO() as output_bytes:
        plt.savefig(output_bytes, format="png")
        bytes_data = output_bytes.getvalue()
    base64_str = str(base64.b64encode(bytes_data), 'utf-8')
    return "data:image/png;base64," + base64_str

def encode_array_to_base64(image_array):
    with BytesIO() as output_bytes:
        PIL_image = Image.fromarray(_convert(image_array, np.uint8, force_copy=False))
        PIL_image.save(output_bytes, 'PNG')
        bytes_data = output_bytes.getvalue()
    base64_str = str(base64.b64encode(bytes_data), 'utf-8')
    return "data:image/png;base64," + base64_str


def resize_and_crop(img, size, crop_type='center'):
    """
    Resize and crop an image to fit the specified size.
    args:
        size: `(width, height)` tuple.
        crop_type: can be 'top', 'middle' or 'bottom', depending on this
            value, the image will cropped getting the 'top/left', 'middle' or
            'bottom/right' of the image to fit the size.
    raises:
        ValueError: if an invalid `crop_type` is provided.
    """
    if crop_type == "top":
        center = (0, 0)
    elif crop_type == "center":
        center = (0.5, 0.5)
    else:
        raise ValueError
    return ImageOps.fit(img, size, centering=center) 

##################
# Audio
##################

def audio_from_file(filename, crop_min=0, crop_max=100):
    audio = AudioSegment.from_file(filename)
    if crop_min != 0 or crop_max != 100:
        audio_start = len(audio) * crop_min / 100
        audio_end = len(audio) * crop_max / 100
        audio = audio[audio_start : audio_end]
    data = np.array(audio.get_array_of_samples())
    if (audio.channels > 1):
        data = data.reshape(-1, audio.channels)
    return audio.frame_rate, data

def audio_to_file(sample_rate, data, filename):
    audio = AudioSegment(
        data.tobytes(), 
        frame_rate=sample_rate,
        sample_width=data.dtype.itemsize, 
        channels=(1 if len(data.shape) == 1 else data.shape[1])
    )
    audio.export(filename, format="wav")

##################
# OUTPUT
##################

def decode_base64_to_binary(encoding):
    extension = None
    if "," in encoding:
        header, data = encoding.split(",")
        header = header[5:]
        if ";base64" in header:
            header = header[0:header.index(";base64")]
        if "/" in header:
            extension = header[header.index("/") + 1:]
    else:
        data = encoding
    return base64.b64decode(data), extension

def decode_base64_to_file(encoding, encryption_key=None, file_path=None):
    data, mime_extension = decode_base64_to_binary(encoding)
    prefix, extension = None, None
    if file_path is not None:
        filename = os.path.basename(file_path)
        prefix = filename
        if "." in filename:
            prefix = filename[0: filename.index(".")]
            extension = filename[filename.index(".") + 1:]
    if extension is None:
        extension = mime_extension
    if extension is None:
        file_obj = tempfile.NamedTemporaryFile(delete=False, prefix=prefix)
    else:
        file_obj = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix="."+extension)
    if encryption_key is not None:
        data = encryptor.encrypt(encryption_key, data)
    file_obj.write(data)
    file_obj.flush()
    return file_obj

def create_tmp_copy_of_file(file_path):
    file_name = os.path.basename(file_path)
    prefix, extension = file_name, None
    if "." in file_name:
        prefix = file_name[0: file_name.index(".")]
        extension = file_name[file_name.index(".") + 1:]
    if extension is None:
        file_obj = tempfile.NamedTemporaryFile(delete=False, prefix=prefix)
    else:
        file_obj = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix="."+extension)
    shutil.copy2(file_path, file_obj.name)
    return file_obj

def _convert(image, dtype, force_copy=False, uniform=False):
    """
    Adapted from: https://github.com/scikit-image/scikit-image/blob/main/skimage/util/dtype.py#L510-L531
    
    Convert an image to the requested data-type.
    Warnings are issued in case of precision loss, or when negative values
    are clipped during conversion to unsigned integer types (sign loss).
    Floating point values are expected to be normalized and will be clipped
    to the range [0.0, 1.0] or [-1.0, 1.0] when converting to unsigned or
    signed integers respectively.
    Numbers are not shifted to the negative side when converting from
    unsigned to signed integer types. Negative values will be clipped when
    converting to unsigned integers.
    Parameters
    ----------
    image : ndarray
        Input image.
    dtype : dtype
        Target data-type.
    force_copy : bool, optional
        Force a copy of the data, irrespective of its current dtype.
    uniform : bool, optional
        Uniformly quantize the floating point range to the integer range.
        By default (uniform=False) floating point values are scaled and
        rounded to the nearest integers, which minimizes back and forth
        conversion errors.
    .. versionchanged :: 0.15
        ``_convert`` no longer warns about possible precision or sign
        information loss. See discussions on these warnings at:
        https://github.com/scikit-image/scikit-image/issues/2602
        https://github.com/scikit-image/scikit-image/issues/543#issuecomment-208202228
        https://github.com/scikit-image/scikit-image/pull/3575
    References
    ----------
    .. [1] DirectX data conversion rules.
           https://msdn.microsoft.com/en-us/library/windows/desktop/dd607323%28v=vs.85%29.aspx
    .. [2] Data Conversions. In "OpenGL ES 2.0 Specification v2.0.25",
           pp 7-8. Khronos Group, 2010.
    .. [3] Proper treatment of pixels as integers. A.W. Paeth.
           In "Graphics Gems I", pp 249-256. Morgan Kaufmann, 1990.
    .. [4] Dirty Pixels. J. Blinn. In "Jim Blinn's corner: Dirty Pixels",
           pp 47-57. Morgan Kaufmann, 1998.
    """
    dtype_range = {bool: (False, True),
                np.bool_: (False, True),
                np.bool8: (False, True),
                float: (-1, 1),
                np.float_: (-1, 1),
                np.float16: (-1, 1),
                np.float32: (-1, 1),
                np.float64: (-1, 1)}

    def _dtype_itemsize(itemsize, *dtypes):
        """Return first of `dtypes` with itemsize greater than `itemsize`
        Parameters
        ----------
        itemsize: int
            The data type object element size.
        Other Parameters
        ----------------
        *dtypes:
            Any Object accepted by `np.dtype` to be converted to a data
            type object
        Returns
        -------
        dtype: data type object
            First of `dtypes` with itemsize greater than `itemsize`.
        """
        return next(dt for dt in dtypes if np.dtype(dt).itemsize >= itemsize)

    def _dtype_bits(kind, bits, itemsize=1):
        """Return dtype of `kind` that can store a `bits` wide unsigned int
        Parameters:
        kind: str
            Data type kind.
        bits: int
            Desired number of bits.
        itemsize: int
            The data type object element size.
        Returns
        -------
        dtype: data type object
            Data type of `kind` that can store a `bits` wide unsigned int
        """

        s = next(i for i in (itemsize, ) + (2, 4, 8) if
                bits < (i * 8) or (bits == (i * 8) and kind == 'u'))

        return np.dtype(kind + str(s))


    def _scale(a, n, m, copy=True):
        """Scale an array of unsigned/positive integers from `n` to `m` bits.
        Numbers can be represented exactly only if `m` is a multiple of `n`.
        Parameters
        ----------
        a : ndarray
            Input image array.
        n : int
            Number of bits currently used to encode the values in `a`.
        m : int
            Desired number of bits to encode the values in `out`.
        copy : bool, optional
            If True, allocates and returns new array. Otherwise, modifies
            `a` in place.
        Returns
        -------
        out : array
            Output image array. Has the same kind as `a`.
        """
        kind = a.dtype.kind
        if n > m and a.max() < 2 ** m:
            mnew = int(np.ceil(m / 2) * 2)
            if mnew > m:
                dtype = "int{}".format(mnew)
            else:
                dtype = "uint{}".format(mnew)
            n = int(np.ceil(n / 2) * 2)
            return a.astype(_dtype_bits(kind, m))
        elif n == m:
            return a.copy() if copy else a
        elif n > m:
            # downscale with precision loss
            if copy:
                b = np.empty(a.shape, _dtype_bits(kind, m))
                np.floor_divide(a, 2**(n - m), out=b, dtype=a.dtype,
                                casting='unsafe')
                return b
            else:
                a //= 2**(n - m)
                return a
        elif m % n == 0:
            # exact upscale to a multiple of `n` bits
            if copy:
                b = np.empty(a.shape, _dtype_bits(kind, m))
                np.multiply(a, (2**m - 1) // (2**n - 1), out=b, dtype=b.dtype)
                return b
            else:
                a = a.astype(_dtype_bits(kind, m, a.dtype.itemsize), copy=False)
                a *= (2**m - 1) // (2**n - 1)
                return a
        else:
            # upscale to a multiple of `n` bits,
            # then downscale with precision loss
            o = (m // n + 1) * n
            if copy:
                b = np.empty(a.shape, _dtype_bits(kind, o))
                np.multiply(a, (2**o - 1) // (2**n - 1), out=b, dtype=b.dtype)
                b //= 2**(o - m)
                return b
            else:
                a = a.astype(_dtype_bits(kind, o, a.dtype.itemsize), copy=False)
                a *= (2**o - 1) // (2**n - 1)
                a //= 2**(o - m)
                return a

    image = np.asarray(image)
    dtypeobj_in = image.dtype
    if dtype is np.floating:
        dtypeobj_out = np.dtype('float64')
    else:
        dtypeobj_out = np.dtype(dtype)
    dtype_in = dtypeobj_in.type
    dtype_out = dtypeobj_out.type
    kind_in = dtypeobj_in.kind
    kind_out = dtypeobj_out.kind
    itemsize_in = dtypeobj_in.itemsize
    itemsize_out = dtypeobj_out.itemsize

    # Below, we do an `issubdtype` check.  Its purpose is to find out
    # whether we can get away without doing any image conversion.  This happens
    # when:
    #
    # - the output and input dtypes are the same or
    # - when the output is specified as a type, and the input dtype
    #   is a subclass of that type (e.g. `np.floating` will allow
    #   `float32` and `float64` arrays through)

    if np.issubdtype(dtype_in, np.obj2sctype(dtype)):
        if force_copy:
            image = image.copy()
        return image

    if kind_in in 'ui':
        imin_in = np.iinfo(dtype_in).min
        imax_in = np.iinfo(dtype_in).max
    if kind_out in 'ui':
        imin_out = np.iinfo(dtype_out).min
        imax_out = np.iinfo(dtype_out).max

    # any -> binary
    if kind_out == 'b':
        return image > dtype_in(dtype_range[dtype_in][1] / 2)

    # binary -> any
    if kind_in == 'b':
        result = image.astype(dtype_out)
        if kind_out != 'f':
            result *= dtype_out(dtype_range[dtype_out][1])
        return result


    # float -> any
    if kind_in == 'f':
        if kind_out == 'f':
            # float -> float
            return image.astype(dtype_out)

        if np.min(image) < -1.0 or np.max(image) > 1.0:
            raise ValueError("Images of type float must be between -1 and 1.")
        # floating point -> integer
        # use float type that can represent output integer type
        computation_type = _dtype_itemsize(itemsize_out, dtype_in,
                                           np.float32, np.float64)

        if not uniform:
            if kind_out == 'u':
                image_out = np.multiply(image, imax_out,
                                        dtype=computation_type)
            else:
                image_out = np.multiply(image, (imax_out - imin_out) / 2,
                                        dtype=computation_type)
                image_out -= 1.0 / 2.
            np.rint(image_out, out=image_out)
            np.clip(image_out, imin_out, imax_out, out=image_out)
        elif kind_out == 'u':
            image_out = np.multiply(image, imax_out + 1,
                                    dtype=computation_type)
            np.clip(image_out, 0, imax_out, out=image_out)
        else:
            image_out = np.multiply(image, (imax_out - imin_out + 1.0) / 2.0,
                                    dtype=computation_type)
            np.floor(image_out, out=image_out)
            np.clip(image_out, imin_out, imax_out, out=image_out)
        return image_out.astype(dtype_out)

    # signed/unsigned int -> float
    if kind_out == 'f':
        # use float type that can exactly represent input integers
        computation_type = _dtype_itemsize(itemsize_in, dtype_out,
                                           np.float32, np.float64)

        if kind_in == 'u':
            # using np.divide or np.multiply doesn't copy the data
            # until the computation time
            image = np.multiply(image, 1. / imax_in,
                                dtype=computation_type)
            # DirectX uses this conversion also for signed ints
            # if imin_in:
            #     np.maximum(image, -1.0, out=image)
        else:
            image = np.add(image, 0.5, dtype=computation_type)
            image *= 2 / (imax_in - imin_in)

        return np.asarray(image, dtype_out)

    # unsigned int -> signed/unsigned int
    if kind_in == 'u':
        if kind_out == 'i':
            # unsigned int -> signed int
            image = _scale(image, 8 * itemsize_in, 8 * itemsize_out - 1)
            return image.view(dtype_out)
        else:
            # unsigned int -> unsigned int
            return _scale(image, 8 * itemsize_in, 8 * itemsize_out)

    # signed int -> unsigned int
    if kind_out == 'u':
        image = _scale(image, 8 * itemsize_in - 1, 8 * itemsize_out)
        result = np.empty(image.shape, dtype_out)
        np.maximum(image, 0, out=result, dtype=image.dtype, casting='unsafe')
        return result

    # signed int -> signed int
    if itemsize_in > itemsize_out:
        return _scale(image, 8 * itemsize_in - 1, 8 * itemsize_out - 1)

    image = image.astype(_dtype_bits('i', itemsize_out * 8))
    image -= imin_in
    image = _scale(image, 8 * itemsize_in, 8 * itemsize_out, copy=False)
    image += imin_out
    return image.astype(dtype_out)
