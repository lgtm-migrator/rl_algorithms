"""Learner for DQN Agent.

- Author: Chris Yoon
- Contact: chris.yoon@medipixel.io
"""
import argparse
from collections import OrderedDict
from copy import deepcopy
from typing import Tuple, Union

import numpy as np
import torch
import torch.nn as nn
from torch.nn.utils import clip_grad_norm_
import torch.optim as optim

from rl_algorithms.common.abstract.learner import Learner, TensorTuple
import rl_algorithms.common.helper_functions as common_utils
from rl_algorithms.common.networks.brain import Brain
from rl_algorithms.registry import LEARNERS, build_loss
from rl_algorithms.utils.config import ConfigDict


@LEARNERS.register_module
class DQNLearner(Learner):
    """Learner for DQN Agent.

    Attributes:
        args (argparse.Namespace): arguments including hyperparameters and training settings
        hyper_params (ConfigDict): hyper-parameters
        log_cfg (ConfigDict): configuration for saving log and checkpoint
        dqn (nn.Module): dqn model to predict state Q values
        dqn_target (nn.Module): target dqn model to predict state Q values
        dqn_optim (Optimizer): optimizer for training dqn

    """

    def __init__(
        self,
        args: argparse.Namespace,
        env_info: ConfigDict,
        hyper_params: ConfigDict,
        log_cfg: ConfigDict,
        backbone: ConfigDict,
        head: ConfigDict,
        optim_cfg: ConfigDict,
        loss_type: ConfigDict,
    ):
        Learner.__init__(self, args, env_info, hyper_params, log_cfg)
        self.backbone_cfg = backbone
        self.head_cfg = head
        self.head_cfg.configs.state_size = self.env_info.observation_space.shape
        self.head_cfg.configs.output_size = 3
        self.optim_cfg = optim_cfg
        self.loss_type = loss_type
        self._init_network()

    # pylint: disable=attribute-defined-outside-init
    def _init_network(self):
        """Initialize networks and optimizers."""
        self.dqn = Brain(self.backbone_cfg, self.head_cfg).to(self.device)
        self.dqn_target = Brain(self.backbone_cfg, self.head_cfg).to(self.device)
        self.loss_fn = build_loss(self.loss_type)

        self.dqn_target.load_state_dict(self.dqn.state_dict())

        # create optimizer
        self.dqn_optim = optim.Adam(
            self.dqn.parameters(),
            lr=self.optim_cfg.lr_dqn,
            weight_decay=self.optim_cfg.weight_decay,
            eps=self.optim_cfg.adam_eps,
        )

        # load the optimizer and model parameters
        if self.args.load_from is not None:
            self.load_params(self.args.load_from)

    def update_model(
        self, experience: Union[TensorTuple, Tuple[TensorTuple]], is_per: bool = True
    ) -> Tuple[torch.Tensor, torch.Tensor, list, np.ndarray]:  # type: ignore
        """Update dqn and dqn target."""
        experience_1 = experience
        if is_per:
            weights, indices = experience_1[-3:-1]

        gamma = self.hyper_params.gamma ** self.hyper_params.n_step

        dq_loss_element_wise, q_values = self.loss_fn(
            self.dqn, self.dqn_target, experience_1, gamma, self.head_cfg
        )
        if is_per:
            dq_loss = torch.mean(dq_loss_element_wise * weights)
        else:
            dq_loss = torch.mean(dq_loss_element_wise)

        # q_value regularization
        q_regular = torch.norm(q_values, 2).mean() * self.hyper_params.w_q_reg

        # total loss
        loss = dq_loss + q_regular

        self.dqn_optim.zero_grad()
        loss.backward()
        clip_grad_norm_(self.dqn.parameters(), self.hyper_params.gradient_clip)
        self.dqn_optim.step()

        # update target networks
        common_utils.soft_update(self.dqn, self.dqn_target, self.hyper_params.tau)

        # update priorities in PER
        if is_per:
            loss_for_prior = dq_loss_element_wise.detach().cpu().numpy()
            new_priorities = loss_for_prior + self.hyper_params.per_eps

        if self.head_cfg.configs.use_noisy_net:
            self.dqn.head.reset_noise()
            self.dqn_target.head.reset_noise()
        if is_per:
            return (
                loss.item(),
                q_values.mean().item(),
                indices,
                new_priorities,
            )
        else:
            return (
                loss.item(),
                q_values.mean().item(),
            )

    def save_params(self, n_episode: int):
        """Save model and optimizer parameters."""
        params = {
            "dqn_state_dict": self.dqn.state_dict(),
            "dqn_target_state_dict": self.dqn_target.state_dict(),
            "dqn_optim_state_dict": self.dqn_optim.state_dict(),
        }

        Learner._save_params(self, params, n_episode)

    # pylint: disable=attribute-defined-outside-init
    def load_params(self, path: str):
        """Load model and optimizer parameters."""
        Learner.load_params(self, path)

        params = torch.load(path)
        self.dqn.load_state_dict(params["dqn_state_dict"])
        self.dqn_target.load_state_dict(params["dqn_target_state_dict"])
        self.dqn_optim.load_state_dict(params["dqn_optim_state_dict"])
        print("[INFO] loaded the model and optimizer from", path)

    def get_state_dict(self) -> OrderedDict:
        """Return state dicts, mainly for distributed worker."""
        dqn = deepcopy(self.dqn)
        return dqn.cpu().state_dict()

    def get_policy(self) -> nn.Module:
        """Return model (policy) used for action selection, used only in grad cam."""
        return self.dqn
