
longlong * FUN_1800644b0(undefined8 param_1,longlong *param_2,longlong param_3,longlong param_4)

{
  undefined8 uVar1;
  longlong lVar2;
  longlong lVar3;
  longlong *plVar4;
  int iVar5;
  longlong lVar6;
  longlong lVar7;
  longlong local_res10;
  undefined8 *local_18;
  undefined8 local_10;
  
  lVar2 = 0;
  local_res10 = 0;
  local_18 = (undefined8 *)(PTR_DAT_1801e5048 + 0x4188);
  local_10 = 0;
  if (param_4 == 0) {
    if (param_3 == 1) {
      lVar3 = *param_2;
      goto LAB_1800645f7;
    }
LAB_180064593:
    PyErr_Format(*(undefined8 *)PyExc_TypeError_exref,
                 "%.200s() takes %.8s %zd positional argument%.1s (%zd given)","get_token","exactly"
                 ,1,&DAT_1801c8f1d,param_3);
    iVar5 = 0xf9ab;
  }
  else {
    lVar7 = param_4;
    if (param_3 == 0) {
      lVar6 = *(longlong *)(param_4 + 0x10);
      lVar2 = param_4;
      local_res10 = FUN_1801bbb60(param_4,(longlong)(param_2 + param_3),(undefined *)*local_18);
      if (local_res10 == 0) {
        lVar2 = PyErr_Occurred();
        if (lVar2 != 0) {
          iVar5 = 0xf99b;
          goto LAB_1800645d7;
        }
        goto LAB_180064593;
      }
      lVar6 = lVar6 + -1;
    }
    else {
      if (param_3 != 1) goto LAB_180064593;
      local_res10 = *param_2;
      lVar6 = *(longlong *)(param_4 + 0x10);
    }
    lVar3 = local_res10;
    if ((lVar6 < 1) ||
       (uVar1 = FUN_1801bc4d0(param_4,(longlong)(param_2 + param_3),(longlong *)&local_18,lVar7,
                              (longlong)&local_res10,param_3,"get_token"), lVar3 = local_res10,
       lVar2 = param_4, -1 < (int)uVar1)) {
LAB_1800645f7:
      plVar4 = FUN_180064620(lVar2,lVar3);
      return plVar4;
    }
    iVar5 = 0xf9a0;
  }
LAB_1800645d7:
  FUN_1801c1020("main.Api.get_token",iVar5,0x606,PTR_s_packed__build_temp__main_py_1801cc288);
  return (longlong *)0x0;
}

