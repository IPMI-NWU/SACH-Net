import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from .sync_batchnorm.batchnorm import SynchronizedBatchNorm2d
from .S3_DSConv import DSConv
from .save_feature_map import save_map
class DecoderBlock(nn.Module):
    def __init__(self, in_channels, n_filters,kernel_size,stride,extend_scope ,BatchNorm,inp=False):
        super(DecoderBlock, self).__init__()
        self.kernel_size=kernel_size+6
        self.inp = inp
        if in_channels>=8:
            self.conv1 = nn.Conv2d(in_channels, in_channels // 4, 1)
            self.bn1 = BatchNorm(in_channels//4)
            self.relu1 = nn.ReLU()

            self.deconv3 = DSConv(in_channels // 4,in_channels // 4,kernel_size=self.kernel_size,stride=stride,extend_scope=extend_scope,morph=2)
            self.deconv4 = DSConv(in_channels // 4,in_channels // 4,kernel_size=self.kernel_size,stride=stride,extend_scope=extend_scope,morph=3)
            self.bn2 = BatchNorm(in_channels//2)
            self.relu2 = nn.ReLU()
            self.conv3 = nn.Conv2d(
                in_channels // 2, n_filters, 1)
            self.bn3 = BatchNorm(n_filters)
            self.relu3 = nn.ReLU()
        elif in_channels>=4:
            self.conv1 = nn.Conv2d(in_channels, in_channels // 4, 1)
            self.bn1 = BatchNorm(in_channels // 4)
            self.relu1 = nn.ReLU()

            self.deconv3 = DSConv(in_channels // 4, in_channels // 2, kernel_size=self.kernel_size, stride=stride,
                                  extend_scope=extend_scope, morph=2)
            self.deconv4 = DSConv(in_channels // 4, in_channels // 2, kernel_size=self.kernel_size, stride=stride,
                                  extend_scope=extend_scope, morph=3)
            self.bn2 = BatchNorm(in_channels)
            self.relu2 = nn.ReLU()
            self.conv3 = nn.Conv2d(
                in_channels, n_filters, 1)
            self.bn3 = BatchNorm(n_filters)
            self.relu3 = nn.ReLU()
        else:

            self.deconv3 = DSConv(in_channels, in_channels*4, kernel_size=self.kernel_size, stride=stride,
                                  extend_scope=extend_scope, morph=2)
            self.deconv4 = DSConv(in_channels, in_channels*4, kernel_size=self.kernel_size, stride=stride,
                                  extend_scope=extend_scope, morph=3)
            self.bn2 = BatchNorm(in_channels*8)
            self.relu2 = nn.ReLU()
            self.conv3 = nn.Conv2d(
                in_channels*8, n_filters, 1)
            self.bn3 = BatchNorm(n_filters)
            self.relu3 = nn.ReLU()



        self.in_channels=in_channels
        self._init_weight()

    def forward(self, x, inp = False):
        if self.in_channels>=4:
            x = self.conv1(x)
            x = self.bn1(x)
            x = self.relu1(x)

        x3=self.deconv3(x)
        x4=self.deconv4(x)

        x = torch.cat((x3, x4), 1)
        if self.inp:
            x = F.interpolate(x, scale_factor=2)
        x = self.bn2(x)
        x = self.relu2(x)
        x = self.conv3(x)
        x = self.bn3(x)
        x = self.relu3(x)
        return x

    def _init_weight(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                torch.nn.init.kaiming_normal_(m.weight)
            elif isinstance(m, nn.ConvTranspose2d):
                torch.nn.init.kaiming_normal_(m.weight)
            elif isinstance(m, SynchronizedBatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def h_transform(self, x):
        shape = x.size()
        x = torch.nn.functional.pad(x, (0, shape[-1]))
        x = x.reshape(shape[0], shape[1], -1)[..., :-shape[-1]]
        x = x.reshape(shape[0], shape[1], shape[2], 2*shape[3]-1)
        return x

    def inv_h_transform(self, x):
        shape = x.size()
        x = x.reshape(shape[0], shape[1], -1).contiguous()
        x = torch.nn.functional.pad(x, (0, shape[-2]))
        x = x.reshape(shape[0], shape[1], shape[-2], 2*shape[-2])
        x = x[..., 0: shape[-2]]
        return x

    def v_transform(self, x):
        x = x.permute(0, 1, 3, 2)
        shape = x.size()
        x = torch.nn.functional.pad(x, (0, shape[-1]))
        x = x.reshape(shape[0], shape[1], -1)[..., :-shape[-1]]
        x = x.reshape(shape[0], shape[1], shape[2], 2*shape[3]-1)
        return x.permute(0, 1, 3, 2)

    def inv_v_transform(self, x):
        x = x.permute(0, 1, 3, 2)
        shape = x.size()
        x = x.reshape(shape[0], shape[1], -1)
        x = torch.nn.functional.pad(x, (0, shape[-2]))
        x = x.reshape(shape[0], shape[1], shape[-2], 2*shape[-2])
        x = x[..., 0: shape[-2]]
        return x.permute(0, 1, 3, 2)

class DecoderConv(nn.Module):

    def __init__(self, in_ch, out_ch,BatchNorm):
        super(DecoderConv, self).__init__()
        self.conv = nn.Conv2d(in_ch, out_ch, 3, padding=1)
        self.bn = BatchNorm(out_ch)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        x = self.conv(x)
        x = self.bn(x)
        x = self.relu(x)

        return x

class Decoder(nn.Module):
    def __init__(self, num_classes, backbone, BatchNorm,show=0):
        super(Decoder, self).__init__()
        if backbone == 'resnet':
            in_inplanes = 256
        else:
            raise NotImplementedError

        self.decoder4 = DecoderConv(in_inplanes, 256, BatchNorm=BatchNorm)

        self.decoder3 = DecoderBlock(512, 128,kernel_size=3,stride=1,extend_scope=1, BatchNorm=BatchNorm)

        self.decoder2 = DecoderBlock(256, 64, kernel_size=3,stride=1,extend_scope=1,BatchNorm=BatchNorm, inp=True)

        self.decoder1 = DecoderBlock(128, 64,kernel_size=3,stride=1,extend_scope=1,BatchNorm=BatchNorm, inp=True)


        self.conv_e3 = nn.Sequential(nn.Conv2d(1024, 256, 1, bias=False),
                                       BatchNorm(256),
                                       nn.ReLU())

        self.conv_e2 = nn.Sequential(nn.Conv2d(512, 128, 1, bias=False),
                                     BatchNorm(128),
                                     nn.ReLU())

        self.conv_e1 = nn.Sequential(nn.Conv2d(256, 64, 1, bias=False),
                                     BatchNorm(64),
                                     nn.ReLU())
        self.flag=show
        self._init_weight()


    def forward(self, e1, e2, e3, e4):
        d4 = torch.cat((self.decoder4(e4), self.conv_e3(e3)), dim=1)
        c=0
        if self.flag==1:
            save_map(d4,'7',c)
        d3 = torch.cat((self.decoder3(d4), self.conv_e2(e2)), dim=1)
        if self.flag == 1:
            save_map(d3,'8',c)
        d2 = torch.cat((self.decoder2(d3), self.conv_e1(e1)), dim=1)
        if self.flag == 1:
            save_map(d2,'9',c)
        d1 = self.decoder1(d2)
        if self.flag == 1:
            save_map(d1,'10',c)
        x = F.interpolate(d1, scale_factor=2, mode='bilinear', align_corners=True)

        return x

    def _init_weight(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                torch.nn.init.kaiming_normal_(m.weight)
            elif isinstance(m, SynchronizedBatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

def build_decoder(num_classes, backbone, BatchNorm):
    return Decoder(num_classes, backbone, BatchNorm)