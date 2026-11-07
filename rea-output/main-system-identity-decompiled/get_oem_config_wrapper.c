
longlong * FUN_18005ab10(undefined8 param_1,longlong *param_2,longlong param_3,longlong param_4)

{
  undefined8 uVar1;
  longlong lVar2;
  longlong *plVar3;
  int iVar4;
  longlong lVar5;
  longlong local_res10;
  undefined8 *local_28;
  undefined8 local_20;
  
  local_28 = (undefined8 *)(PTR_DAT_1801e5048 + 0x4188);
  local_res10 = 0;
  local_20 = 0;
  if (param_4 == 0) {
    if (param_3 == 1) goto LAB_18005ac58;
LAB_18005abf4:
    PyErr_Format(*(undefined8 *)PyExc_TypeError_exref,
                 "%.200s() takes %.8s %zd positional argument%.1s (%zd given)","get_oem_config",
                 "exactly",1,&DAT_1801c8f1d,param_3);
    iVar4 = 0xe747;
  }
  else {
    lVar2 = param_4;
    if (param_3 == 0) {
      lVar5 = *(longlong *)(param_4 + 0x10);
      local_res10 = FUN_1801bbb60(param_4,(longlong)(param_2 + param_3),(undefined *)*local_28);
      if (local_res10 == 0) {
        lVar2 = PyErr_Occurred();
        if (lVar2 != 0) {
          iVar4 = 0xe737;
          goto LAB_18005ac38;
        }
        goto LAB_18005abf4;
      }
      lVar5 = lVar5 + -1;
    }
    else {
      if (param_3 != 1) goto LAB_18005abf4;
      local_res10 = *param_2;
      lVar5 = *(longlong *)(param_4 + 0x10);
    }
    if ((lVar5 < 1) ||
       (uVar1 = FUN_1801bc4d0(param_4,(longlong)(param_2 + param_3),(longlong *)&local_28,lVar2,
                              (longlong)&local_res10,param_3,"get_oem_config"), -1 < (int)uVar1)) {
LAB_18005ac58:
      plVar3 = FUN_18005ac80();
      return plVar3;
    }
    iVar4 = 0xe73c;
  }
LAB_18005ac38:
  FUN_1801c1020("main.Api.get_oem_config",iVar4,0x571,PTR_s_packed__build_temp__main_py_1801cc288);
  return (longlong *)0x0;
}

