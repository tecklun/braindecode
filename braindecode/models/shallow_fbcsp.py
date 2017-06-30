import numpy as np
from torch import nn
from torch.nn import init

from braindecode.modules.expression import Expression
from braindecode.torchext.functions import safe_log, square
from braindecode.torchext.util import np_to_var


class ShallowFBCSPNet(object):
    # TODO: auto final dense length for shallow
    def __init__(self, in_chans,
                 n_classes,
                 input_time_length=None,
                 n_filters_time=40,
                 filter_time_length=25,
                 n_filters_spat=40,
                 pool_time_length=75,
                 pool_time_stride=15,
                 final_conv_length=30,
                 conv_nonlin=square,
                 pool_mode='mean',
                 pool_nonlin=safe_log,
                 split_first_layer=True,
                 batch_norm=True,
                 batch_norm_alpha=0.1,
                 drop_prob=0.5):
        if final_conv_length == 'full':
            assert input_time_length is not None
        self.__dict__.update(locals())
        del self.self

    def create_network(self):
        pool_class = dict(max=nn.MaxPool2d, mean=nn.AvgPool2d)[self.pool_mode]
        model = nn.Sequential()
        if self.split_first_layer:
            model.add_module('dimshuffle',
                             Expression(lambda x: x.permute(0, 3, 2, 1)))
            model.add_module('conv_time', nn.Conv2d(1, self.n_filters_time,
                                                    (
                                                    self.filter_time_length, 1),
                                                    stride=1, ))
            model.add_module('conv_spat',
                             nn.Conv2d(self.n_filters_time, self.n_filters_spat,
                                       (1, self.in_chans), stride=1,
                                       bias=not self.batch_norm))
            n_filters_conv = self.n_filters_spat
        else:
            model.add_module('conv_time',
                             nn.Conv2d(self.in_chans, self.n_filters_time,
                                       (self.filter_time_length, 1),
                                       stride=1,
                                       bias=not self.batch_norm))
            n_filters_conv = self.n_filters_time
        if self.batch_norm:
            model.add_module('bnorm',
                             nn.BatchNorm2d(n_filters_conv,
                                            momentum=self.batch_norm_alpha,
                                            affine=True),)
        model.add_module('conv_nonlin', Expression(self.conv_nonlin))
        model.add_module('pool',
                         pool_class(kernel_size=(self.pool_time_length, 1),
                                    stride=(self.pool_time_stride, 1)))
        model.add_module('pool_nonlin', Expression(self.pool_nonlin))
        model.add_module('drop', nn.Dropout(p=self.drop_prob))
        if self.final_conv_length == 'auto':
            out = model(np_to_var(np.ones(
                (1, self.in_chans, self.input_time_length,1),
                dtype=np.float32)))
            n_out_time = out.cpu().data.numpy().shape[2]
            self.final_conv_length = n_out_time
        model.add_module('conv_classifier',
                             nn.Conv2d(n_filters_conv, self.n_classes,
                                       (self.final_conv_length, 1), bias=True))
        model.add_module('softmax', nn.LogSoftmax())
        model.add_module('squeeze',  Expression(lambda x: x.squeeze()))

        # Initialization, xavier is same as in paper...
        init.xavier_uniform(model.conv_time.weight, gain=1)
        # maybe no bias in case of no split layer and batch norm
        if self.split_first_layer or (not self.batch_norm):
            init.constant(model.conv_time.bias, 0)
        if self.split_first_layer:
            init.xavier_uniform(model.conv_spat.weight, gain=1)
            if not self.batch_norm:
                init.constant(model.conv_spat.bias, 0)
        init.xavier_uniform(model.conv_classifier.weight, gain=1)
        init.constant(model.conv_classifier.bias, 0)

        return model
