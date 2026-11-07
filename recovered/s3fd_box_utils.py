"""S3FD prior generation, box decoding, and non-maximum suppression."""

from __future__ import annotations

import numpy as np


def decode(loc,priors,variances):
    try:
        import torch
        if torch.is_tensor(loc):
            boxes=torch.cat((priors[:,:2]+loc[:,:2]*variances[0]*priors[:,2:],priors[:,2:]*torch.exp(loc[:,2:]*variances[1])),1)
            boxes[:,:2]-=boxes[:,2:]/2;boxes[:,2:]+=boxes[:,:2];return boxes
    except ImportError:pass
    loc,priors=np.asarray(loc),np.asarray(priors);center=priors[:,:2]+loc[:,:2]*variances[0]*priors[:,2:];size=priors[:,2:]*np.exp(loc[:,2:]*variances[1])
    return np.concatenate((center-size/2,center+size/2),axis=1)


def nms_(dets,thresh):
    dets=np.asarray(dets)
    if not len(dets):return np.asarray([],dtype=np.intp)
    x1,y1,x2,y2,scores=(dets[:,i] for i in range(5));areas=(x2-x1)*(y2-y1);order=scores.argsort()[::-1];keep=[]
    while order.size:
        i=order[0];keep.append(int(i));xx1=np.maximum(x1[i],x1[order[1:]]);yy1=np.maximum(y1[i],y1[order[1:]])
        xx2=np.minimum(x2[i],x2[order[1:]]);yy2=np.minimum(y2[i],y2[order[1:]])
        inter=np.maximum(0,xx2-xx1)*np.maximum(0,yy2-yy1);overlap=inter/(areas[i]+areas[order[1:]]-inter)
        order=order[np.where(overlap<=thresh)[0]+1]
    return np.asarray(keep,dtype=np.intp)


def nms(boxes,scores,overlap=.5,top_k=200):
    import torch
    keep=scores.new_zeros(scores.size(0),dtype=torch.long)
    if boxes.numel()==0:return keep,0
    x1,y1,x2,y2=(boxes[:,i] for i in range(4));area=(x2-x1)*(y2-y1)
    _,idx=scores.sort(0);idx=idx[-top_k:];count=0
    while idx.numel()>0:
        i=idx[-1];keep[count]=i;count+=1
        if idx.size(0)==1:break
        idx=idx[:-1]
        xx1=x1.index_select(0,idx).clamp(min=x1[i]);yy1=y1.index_select(0,idx).clamp(min=y1[i])
        xx2=x2.index_select(0,idx).clamp(max=x2[i]);yy2=y2.index_select(0,idx).clamp(max=y2[i])
        inter=(xx2-xx1).clamp(min=0)*(yy2-yy1).clamp(min=0)
        iou=inter/((area.index_select(0,idx)-inter)+area[i]);idx=idx[iou.le(overlap)]
    return keep,count


class PriorBox:
    def __init__(self,input_size,feature_maps,variance=[.1,.2],min_sizes=[16,32,64,128,256,512],steps=[4,8,16,32,64,128],clip=False):
        self.image_size=(input_size,input_size) if isinstance(input_size,int) else tuple(input_size);self.feature_maps=feature_maps
        self.variance=variance;self.min_sizes=min_sizes;self.steps=steps;self.clip=clip

    def forward(self):
        priors=[];height,width=self.image_size
        for k,(fh,fw) in enumerate(self.feature_maps):
            for i in range(fh):
                for j in range(fw):
                    size=self.min_sizes[k];priors.extend(((j+.5)*self.steps[k]/width,(i+.5)*self.steps[k]/height,size/width,size/height))
        output=np.asarray(priors,np.float32).reshape(-1,4)
        if self.clip:output=np.clip(output,0,1)
        try:
            import torch
            return torch.from_numpy(output)
        except ImportError:return output


class Detect:
    def __init__(self,num_classes=2,top_k=750,nms_thresh=.3,conf_thresh=.05,variance=[.1,.2],nms_top_k=5000):
        self.num_classes=num_classes;self.top_k=top_k;self.nms_thresh=nms_thresh;self.conf_thresh=conf_thresh;self.variance=variance;self.nms_top_k=nms_top_k

    def forward(self,loc_data,conf_data,prior_data):
        try:
            import torch
            if torch.is_tensor(loc_data):
                batch=loc_data.size(0);output=torch.zeros(batch,self.num_classes,self.top_k,5,device=loc_data.device)
                for i in range(batch):
                    boxes=decode(loc_data[i],prior_data,self.variance)
                    for cls in range(1,self.num_classes):
                        scores=conf_data[i,:,cls];mask=scores>self.conf_thresh;b=boxes[mask];s=scores[mask]
                        if not s.numel():continue
                        order=torch.argsort(s,descending=True)[:self.nms_top_k];keep,count=nms(b[order],s[order],self.nms_thresh,self.top_k)
                        count=min(count,self.top_k);output[i,cls,:count]=torch.cat((s[order][keep[:count],None],b[order][keep[:count]]),1)
                return output
        except ImportError:pass
        raise RuntimeError("S3FD Detect.forward 需要 torch tensor")
