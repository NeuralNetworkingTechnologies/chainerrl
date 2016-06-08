from cached_property import cached_property
import chainer
from chainer import functions as F
from chainer import cuda
import numpy as np


class QOutput(object):
    """Struct that holds Q-function output and subproducts."""
    pass


class DiscreteQOutput(object):
    """Qfunction output for discrete action space."""

    def __init__(self, q_values, q_values_formatter=lambda x: x):
        assert isinstance(q_values, chainer.Variable)
        self.xp = cuda.get_array_module(q_values.data)
        self.q_values = q_values
        self.n_actions = q_values.data.shape[1]
        self.q_values_formatter = q_values_formatter

    @cached_property
    def greedy_actions(self):
        return chainer.Variable(
            self.q_values.data.argmax(axis=1).astype(np.int32))

    @cached_property
    def max(self):
        return F.select_item(self.q_values, self.greedy_actions)

    def sample_epsilon_greedy_actions(self, epsilon):
        assert self.q_values.data.shape[0] == 1, \
            "This method doesn't support batch computation"
        if np.random.random() < epsilon:
            return chainer.Variable(
                self.xp.asarray([np.random.randint(0, self.n_actions)],
                                dtype=np.int32))
        else:
            return self.greedy_actions

    def evaluate_actions(self, actions):
        assert isinstance(actions, chainer.Variable)
        return F.select_item(self.q_values, actions)

    def compute_advantage(self, actions):
        return self.evaluate_actions(actions) - self.max

    def compute_double_advantage(self, actions, argmax_actions):
        return self.evaluate_actions(actions) - self.evaluate_actions(argmax_actions)

    def __repr__(self):
        return 'DiscreteQOutput greedy_actions:{} q_values:{}'.format(
            self.greedy_actions.data,
            self.q_values_formatter(self.q_values.data))


class ContinuousQOutput(object):
    """Qfunction output for continuous action space.

    See: http://arxiv.org/abs/1603.00748
    """

    def __init__(self, mu, mat, v, action_space):
        self.xp = cuda.get_array_module(mu.data)
        self.mu = mu
        self.mat = mat
        self.v = v
        self.action_space = action_space

        self.batch_size = self.mu.data.shape[0]

    @cached_property
    def greedy_actions(self):
        return self.mu

    @cached_property
    def max(self):
        return F.reshape(self.v, (self.batch_size,))

    def sample_epsilon_greedy_actions(self, epsilon):
        assert self.mu.data.shape[0] == 1, \
            "This method doesn't support batch computation"
        if np.random.random() < epsilon:
            sample = self.action_space.sample().astype(np.float32)
            sample = np.expand_dims(sample, axis=0)
            if self.xp == cuda.cupy:
                sample = cuda.to_gpu(sample)
            return chainer.Variable(sample)
        else:
            return self.greedy_actions

    def evaluate_actions(self, actions):
        assert isinstance(actions, chainer.Variable)
        u_minus_mu = actions - self.mu
        a = - 0.5 * \
            F.batch_matmul(F.batch_matmul(
                u_minus_mu, self.mat, transa=True), u_minus_mu)
        return F.reshape(a, (self.batch_size,)) + F.reshape(self.v, (self.batch_size,))

    def compute_advantage(self, actions):
        return self.evaluate_actions(actions) - self.max

    def compute_double_advantage(self, actions, argmax_actions):
        return self.evaluate_actions(actions) - self.evaluate_actions(argmax_actions)

    def __repr__(self):
        return 'ContinuousQOutput greedy_actions:{} v:{}'.format(
            self.greedy_actions.data, self.v.data)