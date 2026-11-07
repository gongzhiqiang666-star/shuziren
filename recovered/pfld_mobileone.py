"""PFLD-GhostOne landmark backbone reconstructed from the bundled checkpoint."""

from __future__ import annotations

try:
    import torch
    from torch import nn
    import torch.nn.functional as F
except ImportError:torch=nn=F=None

from .mobileone_blocks import MobileOneBlock,GhostOneBottleneck,Conv_Block


if nn is not None:
    class PFLD_GhostOne(nn.Module):
        def __init__(self,width_factor=.5,input_size=192,landmark_number=110,inference_mode=False):
            super().__init__();self.inference_mode=inference_mode;self.num_conv_branches=6
            branches=self.num_conv_branches;c=lambda value:int(value*width_factor)
            self.conv1=MobileOneBlock(3,c(64),3,2,1,inference_mode=inference_mode,num_conv_branches=branches)
            self.conv2=MobileOneBlock(c(64),c(64),3,1,1,groups=c(64),inference_mode=inference_mode,num_conv_branches=branches)
            self.conv3_1=GhostOneBottleneck(c(64),c(96),c(80),2,inference_mode,branches)
            self.conv3_2=GhostOneBottleneck(c(80),c(120),c(80),1,inference_mode,branches)
            self.conv3_3=GhostOneBottleneck(c(80),c(120),c(80),1,inference_mode,branches)
            self.conv4_1=GhostOneBottleneck(c(80),c(200),c(96),2,inference_mode,branches)
            self.conv4_2=GhostOneBottleneck(c(96),c(240),c(96),1,inference_mode,branches)
            self.conv4_3=GhostOneBottleneck(c(96),c(240),c(96),1,inference_mode,branches)
            self.conv5_1=GhostOneBottleneck(c(96),c(336),c(144),2,inference_mode,branches)
            self.conv5_2=GhostOneBottleneck(c(144),c(504),c(144),1,inference_mode,branches)
            self.conv5_3=GhostOneBottleneck(c(144),c(504),c(144),1,inference_mode,branches)
            self.conv5_4=GhostOneBottleneck(c(144),c(504),c(144),1,inference_mode,branches)
            self.conv6=GhostOneBottleneck(c(144),c(216),c(16),1,inference_mode,branches)
            self.conv7=MobileOneBlock(c(16),c(32),3,1,1,inference_mode=inference_mode,num_conv_branches=branches)
            self.conv8=Conv_Block(c(32),c(128),input_size//16,1,0,has_bn=False)
            self.avg_pool1=nn.AvgPool2d(input_size//2);self.avg_pool2=nn.AvgPool2d(input_size//4)
            self.avg_pool3=nn.AvgPool2d(input_size//8);self.avg_pool4=nn.AvgPool2d(input_size//16)
            self.conv_out=nn.Conv2d(c(512),landmark_number*2,1,1,0)
            self.localization=nn.Sequential(
                nn.Conv2d(1,8,kernel_size=7),nn.MaxPool2d(2,stride=2),nn.ReLU(True),
                nn.Conv2d(8,10,kernel_size=5),nn.MaxPool2d(2,stride=2),nn.ReLU(True),
            )
        def forward(self,x):
            x=self.conv2(self.conv1(x));x1=self.avg_pool1(x)
            x=self.conv3_3(self.conv3_2(self.conv3_1(x)));x2=self.avg_pool2(x)
            x=self.conv4_3(self.conv4_2(self.conv4_1(x)));x3=self.avg_pool3(x)
            x=self.conv5_4(self.conv5_3(self.conv5_2(self.conv5_1(x))));x4=self.avg_pool4(x)
            x=self.conv8(self.conv7(self.conv6(x)));x5=x
            multi_scale=torch.cat([x1,x2,x3,x4,x5],1)
            landmarks=self.conv_out(multi_scale)
            return landmarks.view(landmarks.size(0),-1)
else:
    class PFLD_GhostOne:
        def __init__(self,width_factor=.5,input_size=192,landmark_number=110,inference_mode=False):raise RuntimeError("PFLD 网络需要 torch")
        def forward(self,x):raise RuntimeError("PFLD 网络需要 torch")
