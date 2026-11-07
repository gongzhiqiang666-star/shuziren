
/* WARNING: Function: __security_check_cookie replaced with injection: security_check_cookie */

undefined * FUN_180142690(undefined8 param_1,longlong *param_2,longlong param_3,longlong param_4)

{
  longlong *plVar1;
  undefined8 uVar2;
  undefined *puVar3;
  code *pcVar4;
  int iVar5;
  longlong lVar6;
  longlong *plVar7;
  char *pcVar8;
  undefined *puVar9;
  undefined1 auStackY_c8 [32];
  longlong *local_88;
  undefined *puStack_80;
  undefined *local_78;
  undefined8 *local_70;
  undefined *local_68;
  undefined *local_60;
  undefined8 local_58;
  ulonglong local_50;
  
  local_50 = DAT_1801e4000 ^ (ulonglong)auStackY_c8;
  plVar1 = param_2 + param_3;
  local_78 = (undefined *)0x0;
  local_58 = 0;
  local_88 = (longlong *)0x0;
  puStack_80 = (undefined *)0x0;
  local_68 = PTR_DAT_1801e5048 + 0x3b60;
  local_60 = PTR_DAT_1801e5048 + 0x2158;
  local_70 = (undefined8 *)(PTR_DAT_1801e5048 + 0x4188);
  if (param_4 == 0) {
    if (param_3 != 3) {
LAB_180142921:
      PyErr_Format(*(undefined8 *)PyExc_TypeError_exref,
                   "%.200s() takes %.8s %zd positional argument%.1s (%zd given)",
                   "generate_ip_agent_publish_meta","exactly");
      iVar5 = 0x295e6;
      goto LAB_180142965;
    }
    puVar3 = (undefined *)param_2[1];
    plVar7 = (longlong *)*param_2;
    puVar9 = (undefined *)param_2[2];
  }
  else {
    if (param_3 != 0) {
      if (param_3 == 1) {
        local_88 = (longlong *)*param_2;
      }
      else {
        if (param_3 != 2) {
          if (param_3 != 3) goto LAB_180142921;
          local_78 = (undefined *)param_2[2];
        }
        puStack_80 = (undefined *)param_2[1];
        local_88 = (longlong *)*param_2;
      }
    }
    lVar6 = *(longlong *)(param_4 + 0x10);
    if (param_3 == 0) {
      local_88 = (longlong *)FUN_1801bbb60(param_4,(longlong)plVar1,(undefined *)*local_70);
      if (local_88 == (longlong *)0x0) {
        lVar6 = PyErr_Occurred();
        if (lVar6 != 0) {
          iVar5 = 0x295be;
          goto LAB_180142965;
        }
        goto LAB_180142921;
      }
      lVar6 = lVar6 + -1;
LAB_1801427a3:
      plVar7 = local_88;
      puStack_80 = (undefined *)
                   FUN_1801bbb60(param_4,(longlong)plVar1,
                                 *(undefined **)(PTR_DAT_1801e5048 + 0x3b60));
      if (puStack_80 == (undefined *)0x0) {
        lVar6 = PyErr_Occurred();
        if (lVar6 == 0) {
          PyErr_Format(*(undefined8 *)PyExc_TypeError_exref,
                       "%.200s() takes %.8s %zd positional argument%.1s (%zd given)",
                       "generate_ip_agent_publish_meta","exactly");
          iVar5 = 0x295c8;
        }
        else {
          iVar5 = 0x295c6;
        }
        goto LAB_180142965;
      }
      lVar6 = lVar6 + -1;
LAB_1801427d0:
      puVar3 = puStack_80;
      local_78 = (undefined *)
                 FUN_1801bbb60(param_4,(longlong)plVar1,*(undefined **)(PTR_DAT_1801e5048 + 0x2158))
      ;
      if (local_78 == (undefined *)0x0) {
        lVar6 = PyErr_Occurred();
        if (lVar6 == 0) {
          PyErr_Format(*(undefined8 *)PyExc_TypeError_exref,
                       "%.200s() takes %.8s %zd positional argument%.1s (%zd given)",
                       "generate_ip_agent_publish_meta","exactly");
          iVar5 = 0x295d2;
        }
        else {
          iVar5 = 0x295d0;
        }
        goto LAB_180142965;
      }
      lVar6 = lVar6 + -1;
    }
    else {
      if (param_3 == 1) goto LAB_1801427a3;
      puVar3 = puStack_80;
      plVar7 = local_88;
      if (param_3 == 2) goto LAB_1801427d0;
    }
    puVar9 = local_78;
    if ((0 < lVar6) &&
       (uVar2 = FUN_1801bc4d0(param_4,(longlong)plVar1,(longlong *)&local_70,local_78,
                              (longlong)&local_88,param_3,"generate_ip_agent_publish_meta"),
       puVar3 = puStack_80, plVar7 = local_88, puVar9 = local_78, (int)uVar2 < 0)) {
      iVar5 = 0x295d7;
LAB_180142965:
      FUN_1801c1020("main.Api.generate_ip_agent_publish_meta",iVar5,0x13b5,
                    PTR_s_packed__build_temp__main_py_1801cc288);
      return (undefined *)0x0;
    }
  }
  if (*(code **)(puVar3 + 8) == PyUnicode_Type_exref) {
    if (*(code **)(puVar9 + 8) == PyDict_Type_exref) {
      puVar3 = FUN_180142a40(param_1,plVar7,puVar3,puVar9);
      return puVar3;
    }
    if (PyDict_Type_exref != (code *)0x0) {
      pcVar8 = "data";
      pcVar4 = PyDict_Type_exref;
      goto LAB_1801429e3;
    }
  }
  else if (PyUnicode_Type_exref != (code *)0x0) {
    pcVar8 = "project_id";
    pcVar4 = PyUnicode_Type_exref;
LAB_1801429e3:
    PyErr_Format(*(undefined8 *)PyExc_TypeError_exref,
                 "Argument \'%.200s\' has incorrect type (expected %.200s, got %.200s)",pcVar8,
                 *(undefined8 *)(pcVar4 + 0x18));
    return (undefined *)0x0;
  }
  PyErr_SetString(*(undefined8 *)PyExc_SystemError_exref,"Missing type object");
  return (undefined *)0x0;
}

