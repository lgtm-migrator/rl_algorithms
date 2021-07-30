# -*- coding: utf-8 -*-
"""Demo buffer for GAIL algorithm."""

import pickle
from typing import List, Tuple

import numpy as np
import torch

from rl_algorithms.common.abstract.buffer import BaseBuffer

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


class GAILBuffer(BaseBuffer):
    """Buffer to store expert states and actions.

    Attributes:
        input_buf (np.ndarray): observations
        label_buf (np.ndarray): actions
    """

    def __init__(self, dataset_path: str):
        """Initialize a Buffer.

        Args:
            dataset_path (str): path of the demo dataset
        """

        self.input_buf: np.ndarray = None
        self.label_buf: np.ndarray = None

        self.load_demo(dataset_path)

    def load_demo(self, dataset_path: str):
        """load demo data."""
        with open(dataset_path, "rb") as f:
            demo = list(pickle.load(f))
        demo = np.array(demo)
        self.input_buf = np.array(list(map(np.array, demo[:, 0])))  # obs
        self.label_buf = np.array(list(map(np.array, demo[:, 1])))  # acts

    def add(self):
        pass

    def sample(self, batch_size, indices: List[int] = None) -> Tuple[np.ndarray, ...]:
        """Randomly sample a batch of experiences from memory."""
        assert 0 < batch_size < len(self)

        if indices is None:
            indices = np.random.choice(len(self), size=batch_size)

        states = self.input_buf[indices]
        actions = self.label_buf[indices]

        return torch.Tensor(states).to(device), torch.Tensor(actions).to(device)

    def __len__(self) -> int:
        """Return the current size of internal memory."""
        return len(self.input_buf)


class GAIfOBuffer(GAILBuffer):
    """Buffer to store expert states and actions.

    Attributes:
        input_buf (np.ndarray): observations
        label_buf (np.ndarray): next observations
    """

    def load_demo(self, dataset_path: str):
        """load demo data."""
        with open(dataset_path, "rb") as f:
            demo = list(pickle.load(f))
        demo = np.array(demo)
        self.input_buf = np.array(list(map(np.array, demo[:, 0])))  # obs
        self.label_buf = np.array(list(map(np.array, demo[:, 3])))  # nobs
