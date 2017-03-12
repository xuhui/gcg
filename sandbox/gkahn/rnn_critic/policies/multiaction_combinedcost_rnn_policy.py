import tensorflow as tf
import tensorflow.contrib.layers as layers

from rllab.misc.overrides import overrides
from rllab.core.serializable import Serializable
from sandbox.gkahn.rnn_critic.policies.policy import Policy

class MultiactionCombinedcostRNNPolicy(Policy, Serializable):
    def __init__(self,
                 obs_hidden_layers,
                 action_hidden_layers,
                 reward_hidden_layers,
                 rnn_state_dim,
                 activation,
                 rnn_activation,
                 **kwargs):
        """
        :param obs_hidden_layers: layer sizes for preprocessing the observation
        :param action_hidden_layers: layer sizes for preprocessing the action
        :param reward_hidden_layers: layer sizes for processing the reward
        :param rnn_state_dim: dimension of the hidden state
        :param activation: string, e.g. 'tf.nn.relu'
        """
        Serializable.quick_init(self, locals())

        self._obs_hidden_layers = list(obs_hidden_layers)
        self._action_hidden_layers = list(action_hidden_layers)
        self._reward_hidden_layers = list(reward_hidden_layers)
        self._rnn_state_dim = rnn_state_dim
        self._activation = eval(activation)
        self._rnn_activation = eval(rnn_activation)

        Policy.__init__(self, **kwargs)

        assert(self._N > 1)
        assert(self._H > 1)
        assert(self._N == self._H)
        assert(self._cost_type == 'combined')

    ##################
    ### Properties ###
    ##################

    @property
    def N_output(self):
        return self._N

    ###########################
    ### TF graph operations ###
    ###########################

    @overrides
    def _graph_inference(self, tf_obs_ph, tf_actions_ph, d_preprocess):
        with tf.name_scope('inference'):
            tf_obs, tf_actions = self._graph_preprocess_inputs(tf_obs_ph, tf_actions_ph, d_preprocess)

            ### obs --> internal state
            with tf.name_scope('obs_to_istate'):
                layer = tf_obs
                for num_outputs in self._obs_hidden_layers + [self._rnn_state_dim]:
                    layer = layers.fully_connected(layer, num_outputs=num_outputs, activation_fn=self._activation,
                                                   weights_regularizer=layers.l2_regularizer(1.))
                istate = layer

            ### actions --> rnn input at each time step
            with tf.name_scope('actions_to_rnn_input'):
                tf_actions_list = tf.split(1, self._N, tf_actions)
                rnn_inputs = []
                for h in range(self._N):
                    layer = tf_actions_list[h]

                    for i, num_outputs in enumerate(self._action_hidden_layers + [self._rnn_state_dim]):
                        layer = layers.fully_connected(layer, num_outputs=num_outputs, activation_fn=self._activation,
                                                       weights_regularizer=layers.l2_regularizer(1.),
                                                       scope='actions_i{0}'.format(i),
                                                       reuse=(h > 0))
                    rnn_inputs.append(layer)
                rnn_inputs = tf.pack(rnn_inputs, 1)

            ### create rnn
            with tf.name_scope('rnn'):
                with tf.variable_scope('rnn_vars'):
                    rnn_cell = tf.nn.rnn_cell.BasicRNNCell(self._rnn_state_dim, activation=self._rnn_activation)
                    rnn_outputs, rnn_states = tf.nn.dynamic_rnn(rnn_cell, rnn_inputs, initial_state=istate)

            ### internal states --> rewards
            with tf.name_scope('istates_to_rewards'):
                rewards = []
                for h in range(self._N):
                    layer = rnn_outputs[:, h, :]
                    for i, num_outputs in enumerate(self._reward_hidden_layers + [1]):
                        activation = self._activation if i < len(self._reward_hidden_layers) else None
                        layer = layers.fully_connected(layer,
                                                       num_outputs=num_outputs,
                                                       activation_fn=activation,
                                                       weights_regularizer=layers.l2_regularizer(1.),
                                                       scope='rewards_i{0}'.format(i),
                                                       reuse=(h > 0))
                    rewards.append(layer)
                tf_rewards = tf.concat(1, rewards)

            tf_rewards = self._graph_preprocess_outputs(tf_rewards, d_preprocess)

        return tf_rewards
