
longlong * FUN_180050310(undefined8 param_1,longlong *param_2,longlong param_3,longlong param_4)

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
    if (param_3 == 1) goto LAB_180050458;
LAB_1800503f4:
    PyErr_Format(*(undefined8 *)PyExc_TypeError_exref,
                 "%.200s() takes %.8s %zd positional argument%.1s (%zd given)",
                 "get_background_image","exactly",1,&DAT_1801c8f1d,param_3);
    iVar4 = 0xd3c4;
  }
  else {
    lVar2 = param_4;
    if (param_3 == 0) {
      lVar5 = *(longlong *)(param_4 + 0x10);
      local_res10 = FUN_1801bbb60(param_4,(longlong)(param_2 + param_3),(undefined *)*local_28);
      if (local_res10 == 0) {
        lVar2 = PyErr_Occurred();
        if (lVar2 != 0) {
          iVar4 = 0xd3b4;
          goto LAB_180050438;
        }
        goto LAB_1800503f4;
      }
      lVar5 = lVar5 + -1;
    }
    else {
      if (param_3 != 1) goto LAB_1800503f4;
      local_res10 = *param_2;
      lVar5 = *(longlong *)(param_4 + 0x10);
    }
    if ((lVar5 < 1) ||
       (uVar1 = FUN_1801bc4d0(param_4,(longlong)(param_2 + param_3),(longlong *)&local_28,lVar2,
                              (longlong)&local_res10,param_3,"get_background_image"),
       -1 < (int)uVar1)) {
LAB_180050458:
      plVar3 = FUN_180050480();
      return plVar3;
    }
    iVar4 = 0xd3b9;
  }
LAB_180050438:
  FUN_1801c1020("main.Api.get_background_image",iVar4,0x4db,
                PTR_s_packed__build_temp__main_py_1801cc288);
  return (longlong *)0x0;
}

