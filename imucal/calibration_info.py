"""Base Class for all CalibrationInfo objects."""
import json
from dataclasses import dataclass, fields, asdict
from pathlib import Path
from typing import Tuple, Union, TypeVar, ClassVar, Optional, Type

import numpy as np
from typing_extensions import Literal

CalInfo = TypeVar("CalInfo", bound="CalibrationInfo")


class NumpyEncoder(json.JSONEncoder):
    """Custom encoder for numpy array."""

    def default(self, obj):  # noqa: arguments-differ
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return json.JSONEncoder.default(self, obj)


@dataclass(eq=False)
class CalibrationInfo:
    """Abstract BaseClass for all Calibration Info objects."""

    CAL_TYPE: ClassVar[str]  # noqa: invalid-name
    acc_unit: Optional[str] = None
    gyr_unit: Optional[str] = None
    from_acc_unit: Optional[str] = None
    from_gyr_unit: Optional[str] = None
    comment: Optional[str] = None

    _cal_paras: ClassVar[Tuple[str, ...]]

    _cal_type_explanation = """
    Note:
        All `CalibrationInfo` subclasses implement a `CAL_TYPE` attribute.
        If the calibration is exported into any format, this information is stored as well.
        If imported, all constructor methods intelligently infer the correct CalibrationInfo subclass based on
        this parameter.

        Example:
            >>> json_string = "{cal_type: 'Ferraris', ...}"
            >>> CalibrationInfo.from_json(json_string)
            <FerrarisCalibrationInfo ...>

    """

    __doc__ += _cal_type_explanation

    def calibrate(self, acc: np.ndarray, gyro: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Abstract method to perform a calibration on both acc and gyro.

        This absolutely needs to implement by any daughter class

        Parameter
        ---------
        acc :
            3D acceleration
        gyro :
            3D gyroscope values

        """
        raise NotImplementedError("This method needs to be implemented by a subclass")

    def calibrate_gyro(self, gyro: np.ndarray) -> np.ndarray:
        """Abstract method to perform a calibration on both acc and gyro.

        This can implement by any daughter class, if separte calibration of acc makes sense for the calibration type.
        If not, an explicit error should be thrown

        Parameter
        ---------
        gro :
            3D gyroscope values

        """
        raise NotImplementedError("This method needs to be implemented by a subclass")

    def calibrate_acc(self, acc: np.ndarray) -> np.ndarray:
        """Abstract method to perform a calibration on the gyro.

        This can implement by any daughter class, if separte calibration of acc makes sense for the calibration type.
        If not, an explicit error should be thrown

        Parameter
        ---------
        acc :
            3D acceleration

        """
        raise NotImplementedError("This method needs to be implemented by a subclass")

    def __eq__(self, other):
        """Check if two calibrations are identical.

        Note, we use a custom function for that, as we need to compare the numpy arrays.
        """
        # Check type:
        if not isinstance(other, self.__class__):
            raise ValueError("Comparison is only defined between two {} object!".format(self.__class__.__name__))

        # Test keys equal:
        if fields(self) != fields(other):
            return False

        # Test method equal
        if not self.CAL_TYPE == other.CAL_TYPE:
            return False

        # Test all values
        for f in fields(self):
            a1 = getattr(self, f.name)
            a2 = getattr(other, f.name)
            if isinstance(a1, np.ndarray):
                equal = np.array_equal(a1, a2)
            else:
                equal = a1 == a2
            if not equal:
                return False
        return True

    def _to_list_dict(self):
        d = asdict(self)
        d["cal_type"] = self.CAL_TYPE
        return d

    @classmethod
    def _from_list_dict(cls, list_dict):
        for k in cls._cal_paras:
            list_dict[k] = np.array(list_dict[k])
        return cls(**list_dict)

    @classmethod
    def _get_subclasses(cls):
        for subclass in cls.__subclasses__():
            yield from subclass._get_subclasses()
            yield subclass

    @classmethod
    def find_subclass_from_cal_type(cls, cal_type):
        """Get a SensorCalibration subclass that handles the specified calibration type."""
        return next(x for x in CalibrationInfo._get_subclasses() if x.CAL_TYPE == cal_type)

    def to_json(self) -> str:
        """Convert all calibration matrices into a json string."""
        data_dict = self._to_list_dict()
        return json.dumps(data_dict, indent=4, cls=NumpyEncoder)

    @classmethod
    def from_json(cls: Type[CalInfo], json_str: str) -> CalInfo:
        """Create a calibration object from a json string (created by `CalibrationInfo.to_json`).

        Parameter
        ---------
        json_str: valid json string object

        Returns
        -------
        cal_info
            A CalibrationInfo object.
            The exact child class is determined by the `cal_type` key in the json string.

        """
        raw_json = json.loads(json_str)
        subclass = cls.find_subclass_from_cal_type(raw_json.pop("cal_type"))
        return subclass._from_list_dict(raw_json)

    def to_json_file(self, path: Union[str, Path]):
        """Dump acc calibration matrices into a file in json format.

        Parameter
        ---------
        path :
            path to the json file

        """
        data_dict = self._to_list_dict()
        return json.dump(data_dict, open(path, "w"), cls=NumpyEncoder, indent=4)

    @classmethod
    def from_json_file(cls: Type[CalInfo], path: Union[str, Path]) -> CalInfo:
        """Create a calibration object from a valid json file (created by `CalibrationInfo.to_json_file`).

        Parameter
        ---------
        path :
            Path to the json file

        Returns
        -------
        cal_info
            A CalibrationInfo object.
            The exact child class is determined by the `cal_type` key in the json string.

        """
        raw_json = json.load(open(path, "r"))
        subclass = cls.find_subclass_from_cal_type(raw_json.pop("cal_type"))
        return subclass._from_list_dict(raw_json)

    def to_hdf5(self, path: Union[str, Path]):
        """Save calibration matrices to hdf5 file format.

        Parameter
        ---------
        path :
            Path to the hdf5 file

        """
        import h5py  # noqa: import-outside-toplevel

        with h5py.File(path, "w") as hdf:
            for k in fields(self):
                value = getattr(self, k.name)
                if k.name in self._cal_paras:
                    hdf.create_dataset(k.name, data=value.tolist())
                else:
                    if value:
                        hdf[k.name] = value
            hdf["cal_type"] = self.CAL_TYPE

    @classmethod
    def from_hdf5(cls: Type[CalInfo], path: Union[str, Path]):
        """Read calibration data stored in hdf5 fileformat (created by `CalibrationInfo.save_to_hdf5`).

        Parameter
        ---------
        path :
            Path to the hdf5 file

        Returns
        -------
        cal_info
            A CalibrationInfo object.
            The exact child class is determined by the `cal_type` key in the json string.

        """
        import h5py  # noqa: import-outside-toplevel

        with h5py.File(path, "r") as hdf:
            values = dict()
            subcls = cls.find_subclass_from_cal_type(hdf["cal_type"][...])
            for k in fields(subcls):
                tmp = hdf.get(k.name)
                if k.name in subcls._cal_paras:
                    values[k.name] = np.array(tmp)
                elif tmp:
                    values[k.name] = tmp.value
                else:
                    values[k.name] = None

        return subcls(**values)


def load_calibration_info(
    path: Union[Path, str],
    format: Optional[Literal["hdf", "json"]] = None,
    base_class: Type[CalibrationInfo] = CalibrationInfo,
):
    """Load any calibration info object from file.

    Parameters
    ----------
    path
        Path name to the file (can be .json or .hdf)
    format
        Format of the file (either `hdf` or `json`).
        If None, we try to figure out the correct format based on the file suffix.
    base_class
        This method finds the correct calibration info type by inspecting all subclasses of `base_class`.
        Usually that should be kept at the default value.

    Notes
    -----
    This function determines the correct calibration info class to use based on the `cal_type` parameter stored in the
    file.
    For this to work, the correct calibration info class must be accessible.
    This means, if you created a new calibration info class, you need to make sure that it is imported (or at least
    the file it is defined in), before using this function.

    """
    format_options = {"json": "from_json_file", "hdf": "from_hdf5"}
    path = Path(path)
    if format is None:
        # Determine format from file ending:
        suffix = path.suffix
        if suffix == "json":
            format = "json"
        elif suffix in ["hdf", "h5"]:
            format = "hdf"
        else:
            raise ValueError("The loader format could not be determined from the file suffix."
                             "Please specify `format` explicitly.")
    if format not in format_options:
        raise ValueError("`format` must be one of {}".format(list(format_options.keys())))

    return getattr(base_class, format_options[format])(path)
