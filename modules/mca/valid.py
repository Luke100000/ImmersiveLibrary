import io
from typing import Optional

import PIL
import numpy as np
from PIL import Image

from api_types import ContentUpload
from modules.module import Module
from utils import has_tag

# A lookup to verify the skins alpha channel, true values should contain at least some alpha pixels
# fmt: off
# noinspection DuplicatedCode
MASK = np.array([
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, False,
     False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, False,
     False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, False,
     False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, False,
     False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True],
    [True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, True, True, True, True, True, True, True, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, True, True, True,
     True, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, True, True, True, True, True, True, True, True, True, True, True, True],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, True, True, True, True, True, True, True, True, True, True, True, True, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    [False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False,
     False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False]
]).transpose()


# fmt: on


class ValidModule(Module):
    async def pre_upload(self, content: ContentUpload) -> Optional[str]:
        try:
            image = Image.open(io.BytesIO(content.payload))
            image = np.array(image.convert("RGBA"))

            if image.shape != (64, 64, 4):
                return "Shape is not (64, 64, 4)!"
        except PIL.UnidentifiedImageError:
            return "Not an valid image!"

    async def post_upload(self, contentid: int):
        content = await self.database.fetch_one(
            "SELECT data FROM content WHERE oid=:contentid",
            {"contentid": contentid},
        )

        if content is None:
            return

        image = Image.open(io.BytesIO(content[0]))
        image = np.array(image.convert("RGBA"))

        errors = ((image[:, :, -1] == 0) * MASK).sum()
        if errors <= 6:
            if not await has_tag(self.database, contentid, "invalid"):
                await self.database.execute(
                    "INSERT INTO tags (contentid, tag) VALUES(:contentid, :tag)",
                    {"contentid": contentid, "tag": "invalid"},
                )
