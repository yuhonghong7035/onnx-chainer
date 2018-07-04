import collections
import os
import unittest

import mxnet
import numpy as np

import chainer
from chainer import testing
import chainer.functions as F
import chainercv.links as C
import onnx_chainer


@testing.parameterize(
    {'mod': C, 'arch': 'VGG16', 'kwargs': {
        'pretrained_model': None, 'initialW': chainer.initializers.Uniform(1)}},
    {'mod': C, 'arch': 'ResNet50', 'kwargs': {
        'pretrained_model': None,  'initialW': chainer.initializers.Uniform(1), 'arch': 'he'}}
)
class TestWithMXNetBackend(unittest.TestCase):

    def setUp(self):
        self.model = getattr(self.mod, self.arch)(**self.kwargs)

        # To match the behavior with MXNet's default max pooling
        if self.arch == 'ResNet50':
            self.model.pool1 = lambda x: F.max_pooling_2d(
                x, ksize=3, stride=2, cover_all=False)

        self.x = np.random.uniform(
            -1, 1, size=(1, 3, 224, 224)).astype(np.float32)
        self.model(self.x)  # Prevent all NaN output
        self.fn = '{}.onnx'.format(self.arch)

    def test_compatibility(self):
        chainer.config.train = False
        chainer_out = self.model(self.x).array

        onnx_chainer.export(self.model, self.x, self.fn)

        sym, arg, aux = mxnet.contrib.onnx.import_model(self.fn)

        data_names = [graph_input for graph_input in sym.list_inputs()
                      if graph_input not in arg and graph_input not in aux]
        mod = mxnet.mod.Module(
            symbol=sym, data_names=data_names, context=mxnet.cpu(),
            label_names=None)
        mod.bind(
            for_training=False, data_shapes=[(data_names[0], self.x.shape)],
            label_shapes=None)
        mod.set_params(
            arg_params=arg, aux_params=aux, allow_missing=True,
            allow_extra=True)

        Batch = collections.namedtuple('Batch', ['data'])
        mod.forward(Batch([mxnet.nd.array(self.x)]))
        mxnet_outs = mod.get_outputs()
        mxnet_out = mxnet_outs[0].asnumpy()

        np.testing.assert_almost_equal(
            chainer_out, mxnet_out, decimal=5)

        os.remove(self.fn)
