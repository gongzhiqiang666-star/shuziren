
/* WARNING: Function: __security_check_cookie replaced with injection: security_check_cookie */

longlong * FUN_180064dd0(undefined8 param_1,longlong *param_2,longlong param_3,longlong param_4)

{
  longlong *plVar1;
  undefined8 uVar2;
  longlong lVar3;
  longlong lVar4;
  longlong *plVar5;
  int iVar6;
  longlong lVar7;
  undefined8 *puVar8;
  undefined1 auStackY_98 [32];
  longlong local_58;
  longlong lStack_50;
  undefined8 *local_48;
  undefined *local_40;
  undefined8 local_38;
  ulonglong local_30;
  
  local_30 = DAT_1801e4000 ^ (ulonglong)auStackY_98;
  plVar1 = param_2 + param_3;
  plVar5 = (longlong *)0x0;
  local_38 = 0;
  local_58 = 0;
  lStack_50 = 0;
  puVar8 = (undefined8 *)(PTR_DAT_1801e5048 + 0x4188);
  local_40 = PTR_DAT_1801e5048 + 0x4790;
  local_48 = puVar8;
  if (param_4 == 0) {
    if (param_3 == 2) {
      lVar4 = param_2[1];
      lVar3 = *param_2;
      goto LAB_180064fff;
    }
LAB_180064f97:
    PyErr_Format(*(undefined8 *)PyExc_TypeError_exref,
                 "%.200s() takes %.8s %zd positional argument%.1s (%zd given)","save_token",
                 "exactly");
    iVar6 = 0xfb2b;
    goto LAB_180064fdb;
  }
  if (param_3 != 0) {
    if (param_3 == 1) {
      local_58 = *param_2;
    }
    else {
      if (param_3 != 2) goto LAB_180064f97;
      lStack_50 = param_2[1];
      local_58 = *param_2;
    }
  }
  lVar7 = *(longlong *)(param_4 + 0x10);
  if (param_3 == 0) {
    local_58 = FUN_1801bbb60(param_4,(longlong)plVar1,(undefined *)*puVar8);
    if (local_58 == 0) {
      lVar3 = PyErr_Occurred();
      if (lVar3 != 0) {
        iVar6 = 0xfb0f;
        goto LAB_180064fdb;
      }
      goto LAB_180064f97;
    }
    lVar7 = lVar7 + -1;
LAB_180064eb0:
    lVar3 = local_58;
    lStack_50 = FUN_1801bbb60(param_4,(longlong)plVar1,*(undefined **)(PTR_DAT_1801e5048 + 0x4790));
    if (lStack_50 == 0) {
      lVar3 = PyErr_Occurred();
      if (lVar3 == 0) {
        PyErr_Format(*(undefined8 *)PyExc_TypeError_exref,
                     "%.200s() takes %.8s %zd positional argument%.1s (%zd given)","save_token",
                     "exactly");
        iVar6 = 0xfb19;
      }
      else {
        iVar6 = 0xfb17;
      }
      goto LAB_180064fdb;
    }
    lVar7 = lVar7 + -1;
  }
  else {
    lVar3 = local_58;
    if (param_3 == 1) goto LAB_180064eb0;
  }
  lVar4 = lStack_50;
  if ((lVar7 < 1) ||
     (uVar2 = FUN_1801bc4d0(param_4,(longlong)plVar1,(longlong *)&local_48,puVar8,
                            (longlong)&local_58,param_3,"save_token"), lVar4 = lStack_50,
     lVar3 = local_58, -1 < (int)uVar2)) {
LAB_180064fff:
    if (*(code **)(lVar4 + 8) == PyUnicode_Type_exref) {
      plVar5 = FUN_180065090(*(code **)(lVar4 + 8),lVar3,lVar4);
    }
    else if (PyUnicode_Type_exref == (code *)0x0) {
      PyErr_SetString(*(undefined8 *)PyExc_SystemError_exref,"Missing type object");
    }
    else {
      PyErr_Format(*(undefined8 *)PyExc_TypeError_exref,
                   "Argument \'%.200s\' has incorrect type (expected %.200s, got %.200s)","token",
                   *(undefined8 *)(PyUnicode_Type_exref + 0x18));
    }
    return plVar5;
  }
  iVar6 = 0xfb1e;
LAB_180064fdb:
  FUN_1801c1020("main.Api.save_token",iVar6,0x60f,PTR_s_packed__build_temp__main_py_1801cc288);
  return (longlong *)0x0;
}

