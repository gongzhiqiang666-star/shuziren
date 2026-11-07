
undefined * FUN_1800590d0(undefined8 param_1,longlong *param_2,longlong param_3,longlong param_4)

{
  undefined8 uVar1;
  longlong lVar2;
  undefined *puVar3;
  int iVar4;
  longlong lVar5;
  longlong local_res10;
  undefined8 *local_28;
  undefined8 local_20;
  
  local_28 = (undefined8 *)(PTR_DAT_1801e5048 + 0x4188);
  local_res10 = 0;
  local_20 = 0;
  if (param_4 == 0) {
    if (param_3 == 1) goto LAB_180059218;
LAB_1800591b4:
    PyErr_Format(*(undefined8 *)PyExc_TypeError_exref,
                 "%.200s() takes %.8s %zd positional argument%.1s (%zd given)","get_admin_id",
                 "exactly",1,&DAT_1801c8f1d,param_3);
    iVar4 = 0xe431;
  }
  else {
    lVar2 = param_4;
    if (param_3 == 0) {
      lVar5 = *(longlong *)(param_4 + 0x10);
      local_res10 = FUN_1801bbb60(param_4,(longlong)(param_2 + param_3),(undefined *)*local_28);
      if (local_res10 == 0) {
        lVar2 = PyErr_Occurred();
        if (lVar2 != 0) {
          iVar4 = 0xe421;
          goto LAB_1800591f8;
        }
        goto LAB_1800591b4;
      }
      lVar5 = lVar5 + -1;
    }
    else {
      if (param_3 != 1) goto LAB_1800591b4;
      local_res10 = *param_2;
      lVar5 = *(longlong *)(param_4 + 0x10);
    }
    if ((lVar5 < 1) ||
       (uVar1 = FUN_1801bc4d0(param_4,(longlong)(param_2 + param_3),(longlong *)&local_28,lVar2,
                              (longlong)&local_res10,param_3,"get_admin_id"), -1 < (int)uVar1)) {
LAB_180059218:
      puVar3 = FUN_180059240();
      return puVar3;
    }
    iVar4 = 0xe426;
  }
LAB_1800591f8:
  FUN_1801c1020("main.Api.get_admin_id",iVar4,0x560,PTR_s_packed__build_temp__main_py_1801cc288);
  return (undefined *)0x0;
}

