from itertools import product
from typing import Optional, Iterable, TypeVar, Type, Tuple

import numpy as np
import pandas as pd
from numpy.linalg import inv

from imucal.calibration_info import CalibrationInfo
from imucal.calibration_gui import CalibrationGui
from imucal.ferraris_calibration_info import FerrarisCalibrationInfo

T = TypeVar('T', bound='FerrarisCalibration')


class FerrarisCalibration:
    acc_x_p: np.ndarray
    acc_x_a: np.ndarray
    acc_y_p: np.ndarray
    acc_y_a: np.ndarray
    acc_z_p: np.ndarray
    acc_z_a: np.ndarray
    gyr_x_p: np.ndarray
    gyr_x_a: np.ndarray
    gyr_y_p: np.ndarray
    gyr_y_a: np.ndarray
    gyr_z_p: np.ndarray
    gyr_z_a: np.ndarray

    acc_x_rot: np.ndarray
    acc_y_rot: np.ndarray
    acc_z_rot: np.ndarray
    gyr_x_rot: np.ndarray
    gyr_y_rot: np.ndarray
    gyr_z_rot: np.ndarray

    sampling_rate: float
    grav: float
    expected_angle: float

    EXPECTED_ANGLE: float = 360.
    DEFAULT_GRAV: float = 9.81
    ACC_COLS = ('acc_x', 'acc_y', 'acc_z')
    GYRO_COLS = ('gyr_x', 'gyr_y', 'gyr_z')
    FERRARIS_SECTIONS = ('x_p', 'x_a', 'y_p', 'y_a', 'z_p', 'z_a', 'x_rot', 'y_rot', 'z_rot')

    _CALIBRATION_INFO = FerrarisCalibrationInfo

    _fields = tuple('{}_{}'.format(x, y) for x, y in product(('acc', 'gyr'), FERRARIS_SECTIONS))

    def __init__(self, sampling_rate: float, grav: Optional[float] = None, expected_angle: Optional[float] = None,
                 **kwargs) -> None:
        for field in self._fields:
            setattr(self, field, kwargs.get(field, None))

        self.sampling_rate = sampling_rate
        self.grav = grav or self.DEFAULT_GRAV
        self.expected_angle = expected_angle or self.EXPECTED_ANGLE
        super().__init__()

    @classmethod
    def from_df(cls: Type[T],
                df: pd.DataFrame,
                sampling_rate: float,
                grav: Optional[float] = None,
                expected_angle: Optional[float] = None,
                acc_cols: Optional[Iterable[str]] = None,
                gyro_cols: Optional[Iterable[str]] = None
                ) -> T:
        # TODO: need proper documentation
        if acc_cols is None:
            acc_cols = list(cls.ACC_COLS)
        if gyro_cols is None:
            gyro_cols = list(cls.GYRO_COLS)

        grav = grav or cls.DEFAULT_GRAV
        acc_df = df[list(acc_cols)]
        gyro_df = df[list(gyro_cols)]
        acc_dict = acc_df.groupby(level=0).apply(lambda x: x.values).to_dict()
        gyro_dict = gyro_df.groupby(level=0).apply(lambda x: x.values).to_dict()
        acc_dict = {'acc_' + k: v for k, v in acc_dict.items()}
        gyro_dict = {'gyr_' + k: v for k, v in gyro_dict.items()}

        return cls(sampling_rate, grav, expected_angle, **acc_dict, **gyro_dict)

    @classmethod
    def from_section_list(cls: Type[T],
                          data: pd.DataFrame,
                          section_list: pd.DataFrame,
                          sampling_rate: float,
                          grav: Optional[float] = None,
                          expected_angle: Optional[float] = None,
                          acc_cols: Optional[Iterable[str]] = None,
                          gyro_cols: Optional[Iterable[str]] = None
                          ) -> T:
        df = _convert_data_from_section_list_to_df(data, section_list)
        return cls.from_df(df, sampling_rate, expected_angle=expected_angle, grav=grav, acc_cols=acc_cols, gyro_cols=gyro_cols)

    @classmethod
    def from_interactive_plot(cls: Type[T],
                              data: pd.DataFrame,
                              sampling_rate: float,
                              expected_angle: Optional[float] = None,
                              grav: Optional[float] = None,
                              acc_cols: Optional[Iterable[str]] = None,
                              gyro_cols: Optional[Iterable[str]] = None
                              ) -> Tuple[T, pd.DataFrame]:
        # TODO: proper documentation
        if acc_cols is None:
            acc_cols = list(cls.ACC_COLS)
        if gyro_cols is None:
            gyro_cols = list(cls.GYRO_COLS)

        acc = data[acc_cols].values
        gyro = data[gyro_cols].values

        section_list = _find_calibration_sections_interactive(acc, gyro)
        return cls.from_section_list(data, section_list, sampling_rate, expected_angle=expected_angle, grav=grav, acc_cols=acc_cols,
                                     gyro_cols=gyro_cols), section_list

    def compute_calibration_matrix(self) -> CalibrationInfo:
        cal_mat = self._CALIBRATION_INFO()

        ###############################################################################################################
        # Compute Acceleration Matrix

        # Calculate means from all static phases and stack them into 3x3 matrices
        # Note: Each measurement should be a column
        U_a_p = np.vstack((
            np.mean(self.acc_x_p, axis=0),
            np.mean(self.acc_y_p, axis=0),
            np.mean(self.acc_z_p, axis=0),
        )).T
        U_a_n = np.vstack((
            np.mean(self.acc_x_a, axis=0),
            np.mean(self.acc_y_a, axis=0),
            np.mean(self.acc_z_a, axis=0),
        )).T

        # Eq. 19
        U_a_s = U_a_p + U_a_n

        # Bias Matrix
        # Eq. 20
        B_a = U_a_s / 2

        # Bias Vector
        b_a = np.diag(B_a)
        cal_mat.b_a = b_a

        # Compute Scaling and Rotation
        # No need for bias correction, since it cancels out!
        # Eq. 21
        U_a_d = U_a_p - U_a_n

        # Calculate Scaling matrix
        # Eq. 23
        k_a_sq = 1 / (4 * self.grav ** 2) * np.diag(U_a_d @ U_a_d.T)
        K_a = np.diag(np.sqrt(k_a_sq))
        cal_mat.K_a = K_a

        # Calculate Rotation matrix
        # Eq. 22
        R_a = inv(K_a) @ U_a_d / (2 * self.grav)
        cal_mat.R_a = R_a

        ###############################################################################################################
        # Calculate Gyroscope Matrix

        # Gyro Bias from the static phases of the acc calibration
        # One static phase would be sufficient, but why not use all of them if you have them.
        # Note that this calibration ignores any influences due to the earth rotation.

        b_g = np.mean(np.vstack((
            self.gyr_x_p,
            self.gyr_x_a,
            self.gyr_y_p,
            self.gyr_y_a,
            self.gyr_z_p,
            self.gyr_z_a,
        )), axis=0)

        cal_mat.b_g = b_g

        # Acceleration sensitivity

        # Note: Each measurement should be a column
        U_g_p = np.vstack((
            np.mean(self.gyr_x_p, axis=0),
            np.mean(self.gyr_y_p, axis=0),
            np.mean(self.gyr_z_p, axis=0),
        )).T
        U_g_a = np.vstack((
            np.mean(self.gyr_x_a, axis=0),
            np.mean(self.gyr_y_a, axis=0),
            np.mean(self.gyr_z_a, axis=0),
        )).T

        # Eq. 9
        K_ga = (U_g_p - U_g_a) / (2 * self.grav)
        cal_mat.K_ga = K_ga

        # Gyroscope Scaling and Rotation

        # First apply partial calibration to remove offset and acc influence
        acc_x_rot_cor = cal_mat.calibrate_acc(self.acc_x_rot)
        acc_y_rot_cor = cal_mat.calibrate_acc(self.acc_y_rot)
        acc_z_rot_cor = cal_mat.calibrate_acc(self.acc_z_rot)
        gyr_x_rot_cor = cal_mat._calibrate_gyro_offsets(self.gyr_x_rot, acc_x_rot_cor)
        gyr_y_rot_cor = cal_mat._calibrate_gyro_offsets(self.gyr_y_rot, acc_y_rot_cor)
        gyr_z_rot_cor = cal_mat._calibrate_gyro_offsets(self.gyr_z_rot, acc_z_rot_cor)

        # Integrate gyro readings
        # Eg. 13/14
        W_s = np.zeros((3, 3))
        W_s[:, 0] = np.sum(gyr_x_rot_cor, axis=0) / self.sampling_rate
        W_s[:, 1] = np.sum(gyr_y_rot_cor, axis=0) / self.sampling_rate
        W_s[:, 2] = np.sum(gyr_z_rot_cor, axis=0) / self.sampling_rate

        # Eq.15
        expected_angles = self.expected_angle * np.identity(3)
        multiplied = W_s @ inv(expected_angles)

        # Eq. 12
        k_g_sq = np.diag(multiplied @ multiplied.T)
        K_g = np.diag(np.sqrt(k_g_sq))
        cal_mat.K_g = K_g

        R_g = inv(K_g) @ multiplied
        cal_mat.R_g = R_g

        return cal_mat


def _find_calibration_sections_interactive(acc: np.ndarray, gyro: np.ndarray):
    """
    Prepares the calibration data for the later calculation of calibration matrices.

    :param acc: numpy array with the shape (n, 3) where n is the number of samples
    :param gyro: numpy array with the shape (n, 3) where n is the number of samples
    :param debug_plot: set true to see, whether data cutting was successful
    """

    # remove the unnecessary data

    plot = CalibrationGui(acc, gyro, FerrarisCalibration.FERRARIS_SECTIONS)

    section_list = plot.section_list

    check_all = (all(v) for v in section_list.values())
    if not all(check_all):
        raise ValueError('Some regions are missing in the section list. Label all regions before closing the plot')

    section_list = pd.DataFrame(section_list, index=('start', 'end')).T

    return section_list


def _convert_data_from_section_list_to_df(data: pd.DataFrame, section_list: pd.DataFrame):
    out = dict()

    for label, row in section_list.iterrows():
        out[label] = data.iloc[row.start:row.end]

    return pd.concat(out)
