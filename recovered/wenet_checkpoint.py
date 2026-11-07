"""WeNet checkpoint helpers; equivalent Python source is also bundled beside the extension."""

from __future__ import annotations

import datetime
import logging
import os
import re
from collections import OrderedDict
import yaml


def _torch():
    try:import torch
    except ImportError as error:raise RuntimeError("WeNet checkpoint 操作需要 torch") from error
    return torch


def load_checkpoint(model,path):
    torch=_torch();rank=int(os.environ.get("RANK",0));logging.info("[Rank %s] Checkpoint: loading from checkpoint %s",rank,path)
    checkpoint=torch.load(path,map_location="cpu",mmap=True);missing,unexpected=model.load_state_dict(checkpoint,strict=False)
    if rank==0:
        for key in missing:logging.info("missing tensor: %s",key)
        for key in unexpected:logging.info("unexpected tensor: %s",key)
    info_path=re.sub(r"\.pt$",".yaml",path)
    with open(info_path,encoding="utf-8") as source:return yaml.load(source,Loader=yaml.FullLoader) or {}
    return {}


def save_state_dict_and_infos(state_dict,path,infos=None):
    torch=_torch();torch.save(state_dict,path);values=dict(infos or {});values["save_time"]=datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with open(re.sub(r"\.pt$",".yaml",path),"w",encoding="utf-8") as output:yaml.safe_dump(values,output)


def save_checkpoint(model,path,infos=None):
    torch=_torch()
    if isinstance(model,(torch.nn.DataParallel,torch.nn.parallel.DistributedDataParallel)):model=model.module
    save_state_dict_and_infos(model.state_dict(),path,infos)


def filter_modules(model_state_dict,modules):
    keys=model_state_dict.keys();valid=[module for module in modules if any(key.startswith(module) for key in keys)]
    invalid=[module for module in modules if module not in valid]
    if invalid and int(os.environ.get("RANK",0))==0:logging.warning("module(s) %s don't match available modules",invalid)
    return valid


def load_trained_modules(model,args):
    torch=_torch();path=args.enc_init;state=model.state_dict()
    if os.path.isfile(path):
        loaded=torch.load(path,map_location="cpu");modules=filter_modules(loaded,args.enc_init_mods)
        state.update(OrderedDict((key,value) for key,value in loaded.items() if any(key.startswith(module) for module in modules)))
    else:logging.warning("model was not found : %s",path)
    model.load_state_dict(state);return {}
