"""S3FD face detector network."""

from __future__ import annotations

try:
    import torch
    from torch import nn
    import torch.nn.functional as F
except ImportError:torch=nn=F=None

from .s3fd_box_utils import Detect, PriorBox


if nn is not None:
    class L2Norm(nn.Module):
        def __init__(self,n_channels,scale):
            super().__init__();self.n_channels=n_channels;self.gamma=scale;self.eps=1e-10;self.weight=nn.Parameter(torch.empty(n_channels));self.reset_parameters()
        def reset_parameters(self):nn.init.constant_(self.weight,self.gamma)
        def forward(self,x):
            norm=x.pow(2).sum(dim=1,keepdim=True).sqrt()+self.eps;return self.weight[None,:,None,None]*(x/norm)

    def _vgg():
        layers=[];channels=[(3,64),(64,64),"M",(64,128),(128,128),"M",(128,256),(256,256),(256,256),"C",
                            (256,512),(512,512),(512,512),"M",(512,512),(512,512),(512,512),"M"]
        for item in channels:
            if item=="M":layers.append(nn.MaxPool2d(2,2))
            elif item=="C":layers.append(nn.MaxPool2d(2,2,ceil_mode=True))
            else:layers.extend([nn.Conv2d(item[0],item[1],3,padding=1),nn.ReLU(True)])
        layers.extend([nn.Conv2d(512,1024,3,padding=6,dilation=6),nn.ReLU(True),nn.Conv2d(1024,1024,1),nn.ReLU(True)])
        return layers

    def _extras():
        return [nn.Conv2d(1024,256,1),nn.Conv2d(256,512,3,2,1),nn.Conv2d(512,128,1),nn.Conv2d(128,256,3,2,1)]

    class S3FDNet(nn.Module):
        def __init__(self,device="cuda"):
            super().__init__();self.device=device;self.vgg=nn.ModuleList(_vgg());self.extras=nn.ModuleList(_extras())
            self.L2Norm3_3=L2Norm(256,10);self.L2Norm4_3=L2Norm(512,8);self.L2Norm5_3=L2Norm(512,5)
            channels=[256,512,512,1024,512,256];self.loc=nn.ModuleList([nn.Conv2d(c,4,3,padding=1) for c in channels])
            self.conf=nn.ModuleList([nn.Conv2d(channels[0],4,3,padding=1)]+[nn.Conv2d(c,2,3,padding=1) for c in channels[1:]])
            self.softmax=nn.Softmax(dim=-1);self.detect=Detect()
        def forward(self,x):
            size=x.size()[2:];sources=[]
            for index in range(16):x=self.vgg[index](x)
            sources.append(self.L2Norm3_3(x))
            for index in range(16,23):x=self.vgg[index](x)
            sources.append(self.L2Norm4_3(x))
            for index in range(23,30):x=self.vgg[index](x)
            sources.append(self.L2Norm5_3(x))
            for index in range(30,len(self.vgg)):x=self.vgg[index](x)
            sources.append(x)
            for index,layer in enumerate(self.extras):
                x=F.relu(layer(x),inplace=True)
                if index%2==1:sources.append(x)
            loc=[];conf=[];feature_maps=[]
            for index,(feature,loc_layer,conf_layer) in enumerate(zip(sources,self.loc,self.conf)):
                loc_x=loc_layer(feature);score=conf_layer(feature)
                if index==0:
                    background=score[:,:3].max(1,keepdim=True)[0];score=torch.cat((background,score[:,3:4]),1)
                loc.append(loc_x.permute(0,2,3,1).contiguous())
                conf.append(score.permute(0,2,3,1).contiguous())
                feature_maps.append([loc[-1].size(1),loc[-1].size(2)])
            loc=torch.cat([o.view(o.size(0),-1) for o in loc],1)
            conf=torch.cat([o.view(o.size(0),-1) for o in conf],1)
            with torch.no_grad():
                self.priorbox=PriorBox(size,feature_maps);self.priors=self.priorbox.forward()
            return self.detect.forward(loc.view(loc.size(0),-1,4),self.softmax(conf.view(conf.size(0),-1,2)),self.priors.type(type(x.data)).to(self.device))
else:
    class L2Norm:
        def __init__(self,n_channels,scale):raise RuntimeError("S3FD 需要 torch")
        def reset_parameters(self):raise RuntimeError("S3FD 需要 torch")
        def forward(self,x):raise RuntimeError("S3FD 需要 torch")
    class S3FDNet:
        def __init__(self,device="cuda"):raise RuntimeError("S3FD 需要 torch")
        def forward(self,x):raise RuntimeError("S3FD 需要 torch")
