"""MobileOne, Ghost, and MobileNet blocks used by the PFLD landmark model."""

from __future__ import annotations

from collections import OrderedDict

try:
    import torch
    from torch import nn
    import torch.nn.functional as F
except ImportError:
    torch=nn=F=None


def _require_torch():
    if nn is None:raise RuntimeError("PFLD 网络需要 torch")


if nn is not None:
    def Conv_Block(in_channel,out_channel,kernel_size,stride,padding,group=1,has_bn=True,is_linear=False):
        layers=[nn.Conv2d(in_channel,out_channel,kernel_size,stride,padding,groups=group,bias=False)]
        if has_bn:layers.append(nn.BatchNorm2d(out_channel))
        if not is_linear:layers.append(nn.ReLU())
        return nn.Sequential(*layers)

    class SEBlock(nn.Module):
        def __init__(self,in_channels,rd_ratio=.0625):
            super().__init__();reduced=int(in_channels*rd_ratio);self.reduce=nn.Conv2d(in_channels,reduced,1);self.expand=nn.Conv2d(reduced,in_channels,1)
        def forward(self,inputs):
            scale=F.avg_pool2d(inputs,kernel_size=inputs.shape[2:]);scale=F.relu(self.reduce(scale));scale=torch.sigmoid(self.expand(scale));return inputs*scale

    class MobileOneBlock(nn.Module):
        def __init__(self,in_channels,out_channels,kernel_size,stride=1,padding=0,dilation=1,groups=1,inference_mode=False,use_se=False,num_conv_branches=1,is_linear=False):
            super().__init__();self.inference_mode=inference_mode;self.groups=groups;self.stride=stride;self.padding=padding;self.dilation=dilation
            self.kernel_size=kernel_size;self.in_channels=in_channels;self.out_channels=out_channels;self.num_conv_branches=num_conv_branches;self.activation=nn.Identity() if is_linear else nn.ReLU();self.se=SEBlock(out_channels) if use_se else nn.Identity()
            if inference_mode:self.reparam_conv=nn.Conv2d(in_channels,out_channels,kernel_size,stride,padding,dilation,groups,bias=True)
            else:
                self.rbr_skip=nn.BatchNorm2d(in_channels) if out_channels==in_channels and stride==1 else None
                self.rbr_scale=self._conv_bn(1,0) if kernel_size>1 else None
                self.rbr_conv=nn.ModuleList([self._conv_bn(kernel_size,padding) for _ in range(num_conv_branches)])
        def _conv_bn(self,kernel_size,padding):
            return nn.Sequential(OrderedDict(conv=nn.Conv2d(self.in_channels,self.out_channels,kernel_size,self.stride,padding,self.dilation,self.groups,bias=False),bn=nn.BatchNorm2d(self.out_channels)))
        def forward(self,x):
            if self.inference_mode:return self.activation(self.se(self.reparam_conv(x)))
            identity=0 if self.rbr_skip is None else self.rbr_skip(x);scale=0 if self.rbr_scale is None else self.rbr_scale(x)
            return self.activation(self.se(identity+scale+sum(branch(x) for branch in self.rbr_conv)))
        def _fuse_bn_tensor(self,branch):
            if branch is None:return 0,0
            if isinstance(branch,nn.Sequential):kernel=branch.conv.weight;running_mean=branch.bn.running_mean;running_var=branch.bn.running_var;gamma=branch.bn.weight;beta=branch.bn.bias;eps=branch.bn.eps
            else:
                if not hasattr(self,"id_tensor"):
                    input_dim=self.in_channels//self.groups;kernel=torch.zeros((self.in_channels,input_dim,self.kernel_size,self.kernel_size),device=branch.weight.device)
                    for i in range(self.in_channels):kernel[i,i%input_dim,self.kernel_size//2,self.kernel_size//2]=1
                    self.id_tensor=kernel
                kernel=self.id_tensor;running_mean=branch.running_mean;running_var=branch.running_var;gamma=branch.weight;beta=branch.bias;eps=branch.eps
            std=(running_var+eps).sqrt();return kernel*(gamma/std).reshape(-1,1,1,1),beta-running_mean*gamma/std
        def _get_kernel_bias(self):
            kernel=0;bias=0
            for branch in self.rbr_conv:
                k,b=self._fuse_bn_tensor(branch);kernel+=k;bias+=b
            k,b=self._fuse_bn_tensor(self.rbr_scale)
            if isinstance(k,torch.Tensor):
                pad=self.kernel_size//2;k=F.pad(k,[pad,pad,pad,pad]);kernel+=k;bias+=b
            k,b=self._fuse_bn_tensor(self.rbr_skip);kernel+=k;bias+=b;return kernel,bias
        def reparameterize(self):
            if self.inference_mode:return
            kernel,bias=self._get_kernel_bias();self.reparam_conv=nn.Conv2d(self.in_channels,self.out_channels,self.kernel_size,self.stride,self.padding,self.dilation,self.groups,bias=True)
            self.reparam_conv.weight.data=kernel;self.reparam_conv.bias.data=bias
            for parameter in self.parameters():parameter.detach_()
            del self.rbr_conv
            if hasattr(self,"rbr_scale"):del self.rbr_scale
            if hasattr(self,"rbr_skip"):del self.rbr_skip
            self.inference_mode=True

    class GhostModule(nn.Module):
        def __init__(self,in_channel,out_channel,is_linear=False):
            super().__init__();self.out_channel=out_channel;init=(out_channel+1)//2;new=init;self.primary_conv=Conv_Block(in_channel,init,1,1,0,is_linear=is_linear);self.cheap_operation=Conv_Block(init,new,3,1,1,group=init,is_linear=is_linear)
        def forward(self,x):
            primary=self.primary_conv(x);return torch.cat([primary,self.cheap_operation(primary)],1)[:,:self.out_channel,:,:]

    class GhostBottleneck(nn.Module):
        def __init__(self,in_channel,hidden_channel,out_channel,stride):
            super().__init__();self.ghost_conv=nn.Sequential(GhostModule(in_channel,hidden_channel),nn.Identity() if stride==1 else Conv_Block(hidden_channel,hidden_channel,3,stride,1,group=hidden_channel,is_linear=True),GhostModule(hidden_channel,out_channel,True));self.shortcut=nn.Identity() if stride==1 and in_channel==out_channel else nn.Sequential(Conv_Block(in_channel,in_channel,3,stride,1,group=in_channel,is_linear=True),Conv_Block(in_channel,out_channel,1,1,0,is_linear=True))
        def forward(self,x):return self.ghost_conv(x)+self.shortcut(x)

    class GhostOneModule(nn.Module):
        def __init__(self,in_channel,out_channel,is_linear=False,inference_mode=False,num_conv_branches=1):
            super().__init__();self.out_channel=out_channel;init=(out_channel+1)//2;self.primary_conv=MobileOneBlock(in_channel,init,1,inference_mode=inference_mode,num_conv_branches=num_conv_branches,is_linear=is_linear);self.cheap_operation=MobileOneBlock(init,init,3,padding=1,groups=init,inference_mode=inference_mode,num_conv_branches=num_conv_branches,is_linear=is_linear)
        def forward(self,x):
            primary=self.primary_conv(x);return torch.cat([primary,self.cheap_operation(primary)],1)

    class GhostOneBottleneck(nn.Module):
        def __init__(self,in_channel,hidden_channel,out_channel,stride,inference_mode=False,num_conv_branches=1):
            super().__init__();assert stride in (1,2);self.inference_mode=inference_mode;self.num_conv_branches=num_conv_branches;self.ghost_conv=nn.Sequential(GhostOneModule(in_channel,hidden_channel,inference_mode=inference_mode,num_conv_branches=num_conv_branches),nn.Sequential() if stride==1 else MobileOneBlock(hidden_channel,hidden_channel,3,stride,1,groups=hidden_channel,inference_mode=inference_mode,num_conv_branches=num_conv_branches,is_linear=True),GhostOneModule(hidden_channel,out_channel,True,inference_mode,num_conv_branches=num_conv_branches))
        def forward(self,x):return self.ghost_conv(x)

    class InvertedResidual(nn.Module):
        def __init__(self,in_channel,out_channel,stride,use_res_connect,expand_ratio):
            super().__init__();hidden=round(in_channel*expand_ratio);layers=[]
            if expand_ratio!=1:layers.append(Conv_Block(in_channel,hidden,1,1,0))
            layers.extend([Conv_Block(hidden,hidden,3,stride,1,group=hidden),Conv_Block(hidden,out_channel,1,1,0,is_linear=True)]);self.inv_res=nn.Sequential(*layers);self.use_res_connect=use_res_connect
        def forward(self,x):return x+self.inv_res(x) if self.use_res_connect else self.inv_res(x)
else:
    def Conv_Block(in_channel,out_channel,kernel_size,stride,padding,group=1,has_bn=True,is_linear=False):_require_torch()
    class SEBlock:
        def __init__(self,in_channels,rd_ratio=.0625):_require_torch()
        def forward(self,inputs):_require_torch()
    class MobileOneBlock:
        def __init__(self,in_channels,out_channels,kernel_size,stride=1,padding=0,dilation=1,groups=1,inference_mode=False,use_se=False,num_conv_branches=1,is_linear=False):_require_torch()
        def _conv_bn(self,kernel_size,padding):_require_torch()
        def forward(self,x):_require_torch()
        def _fuse_bn_tensor(self,branch):_require_torch()
        def _get_kernel_bias(self):_require_torch()
        def reparameterize(self):_require_torch()
    class GhostModule:
        def __init__(self,in_channel,out_channel,is_linear=False):_require_torch()
        def forward(self,x):_require_torch()
    class GhostBottleneck:
        def __init__(self,in_channel,hidden_channel,out_channel,stride):_require_torch()
        def forward(self,x):_require_torch()
    class GhostOneModule:
        def __init__(self,in_channel,out_channel,is_linear=False,inference_mode=False,num_conv_branches=1):_require_torch()
        def forward(self,x):_require_torch()
    class GhostOneBottleneck:
        def __init__(self,in_channel,hidden_channel,out_channel,stride,inference_mode=False,num_conv_branches=1):_require_torch()
        def forward(self,x):_require_torch()
    class InvertedResidual:
        def __init__(self,in_channel,out_channel,stride,use_res_connect,expand_ratio):_require_torch()
        def forward(self,x):_require_torch()
