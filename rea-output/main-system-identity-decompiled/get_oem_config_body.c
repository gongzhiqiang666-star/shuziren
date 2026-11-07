
/* WARNING: Function: __security_check_cookie replaced with injection: security_check_cookie */
/* WARNING: Removing unreachable block (ram,0x00018005ba63) */
/* WARNING: Removing unreachable block (ram,0x00018005ba6a) */

longlong * FUN_18005ac80(void)

{
  code *pcVar1;
  undefined *puVar2;
  undefined *puVar3;
  undefined8 *puVar4;
  int iVar5;
  int iVar6;
  longlong *plVar7;
  longlong *plVar8;
  longlong lVar9;
  ulonglong uVar11;
  longlong *plVar12;
  longlong *plVar13;
  longlong lVar14;
  longlong *plVar15;
  uint uVar16;
  undefined8 *puVar17;
  undefined *puVar18;
  int iVar19;
  longlong *plVar20;
  undefined1 auStack_138 [32];
  code *local_118;
  longlong *local_110;
  longlong *local_108;
  longlong *local_100;
  longlong *local_f8;
  longlong *local_f0;
  longlong *local_e8;
  longlong *local_e0;
  longlong *local_d8;
  longlong *local_d0;
  code *local_c8;
  longlong *local_c0;
  longlong *local_b8;
  longlong local_b0;
  longlong *local_a8;
  longlong *local_a0;
  longlong *local_98;
  longlong *local_90 [4];
  longlong *local_70;
  longlong *local_68;
  undefined8 local_60;
  longlong *local_58;
  longlong *local_50;
  undefined8 local_48;
  undefined8 local_40;
  undefined8 local_38;
  ulonglong local_30;
  undefined8 uVar10;
  
  local_30 = DAT_1801e4000 ^ (ulonglong)auStack_138;
  plVar15 = (longlong *)0x0;
  plVar20 = (longlong *)0x0;
  plVar12 = (longlong *)0x0;
  local_a0 = (longlong *)0x0;
  plVar13 = (longlong *)0x0;
  local_a8 = (longlong *)0x0;
  local_e8 = (longlong *)0x0;
  local_110 = (longlong *)0x0;
  local_b0 = _PyThreadState_UncheckedGet();
  puVar4 = *(undefined8 **)(local_b0 + 0x90);
  do {
    puVar17 = puVar4;
    local_c8 = (code *)puVar17[1];
    if ((local_c8 != (code *)0x0) && (local_c8 != _Py_NoneStruct_exref)) break;
    puVar4 = (undefined8 *)puVar17[3];
  } while ((undefined8 *)puVar17[3] != (undefined8 *)0x0);
  local_b8 = (longlong *)*puVar17;
  local_c0 = (longlong *)puVar17[2];
  if (local_b8 != (longlong *)0x0) {
    *local_b8 = *local_b8 + 1;
  }
  if (local_c8 != (code *)0x0) {
    *(longlong *)local_c8 = *(longlong *)local_c8 + 1;
  }
  if (local_c0 != (longlong *)0x0) {
    *local_c0 = *local_c0 + 1;
  }
  puVar18 = PTR_DAT_1801e5048;
  if (DAT_1801f1650 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
    if (DAT_1801ef970 == (longlong *)0x0) {
      uVar10 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x37e0);
      plVar7 = (longlong *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar10);
      puVar18 = PTR_DAT_1801e5048;
      if ((plVar7 == (longlong *)0x0) &&
         (lVar14 = PyErr_Occurred(), puVar18 = PTR_DAT_1801e5048, lVar14 == 0)) {
        PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar10);
        puVar18 = PTR_DAT_1801e5048;
      }
    }
    else {
      *DAT_1801ef970 = *DAT_1801ef970 + 1;
      plVar7 = DAT_1801ef970;
    }
  }
  else {
    lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x37e0);
    plVar7 = (longlong *)
             _PyDict_GetItem_KnownHash
                       (*(longlong *)PTR_DAT_1801e5048,lVar14,*(undefined8 *)(lVar14 + 0x18));
    puVar18 = PTR_DAT_1801e5048;
    DAT_1801f1650 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
    DAT_1801ef970 = plVar7;
    if (plVar7 == (longlong *)0x0) {
      lVar9 = PyErr_Occurred();
      if (lVar9 == 0) {
        plVar7 = (longlong *)FUN_1801bb940(lVar14);
        puVar18 = PTR_DAT_1801e5048;
      }
      else {
        plVar7 = (longlong *)0x0;
        puVar18 = PTR_DAT_1801e5048;
      }
    }
    else {
      *plVar7 = *plVar7 + 1;
    }
  }
  if (plVar7 != (longlong *)0x0) {
    if (*(code **)(plVar7[1] + 0x90) == (code *)0x0) {
      plVar13 = (longlong *)PyObject_GetAttr(plVar7,*(undefined8 *)(puVar18 + 0x3898));
    }
    else {
      plVar13 = (longlong *)(**(code **)(plVar7[1] + 0x90))();
    }
    if (plVar13 == (longlong *)0x0) {
      iVar6 = 0x574;
      iVar19 = 0xe79d;
      plVar20 = plVar15;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    *plVar7 = *plVar7 + -1;
    if (*plVar7 == 0) {
      _Py_Dealloc(plVar7);
    }
    if (*(code **)(plVar13[1] + 0x90) == (code *)0x0) {
      plVar7 = (longlong *)PyObject_GetAttr(plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x30a0));
    }
    else {
      plVar7 = (longlong *)(**(code **)(plVar13[1] + 0x90))();
    }
    if (plVar7 == (longlong *)0x0) {
      iVar6 = 0x574;
      iVar19 = 0xe7a0;
      plVar20 = plVar15;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    *plVar13 = *plVar13 + -1;
    if (*plVar13 == 0) {
      _Py_Dealloc(plVar13);
    }
    puVar18 = PTR_DAT_1801e5048;
    plVar13 = (longlong *)0x0;
    if (DAT_1801f0198 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
      if (DAT_1801f02c8 == (longlong *)0x0) {
        uVar10 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x37e0);
        plVar12 = (longlong *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar10);
        puVar18 = PTR_DAT_1801e5048;
        if ((plVar12 == (longlong *)0x0) &&
           (lVar14 = PyErr_Occurred(), puVar18 = PTR_DAT_1801e5048, lVar14 == 0)) {
          PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar10);
          puVar18 = PTR_DAT_1801e5048;
        }
      }
      else {
        *DAT_1801f02c8 = *DAT_1801f02c8 + 1;
        plVar12 = DAT_1801f02c8;
      }
    }
    else {
      lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x37e0);
      plVar12 = (longlong *)
                _PyDict_GetItem_KnownHash
                          (*(longlong *)PTR_DAT_1801e5048,lVar14,*(undefined8 *)(lVar14 + 0x18));
      puVar18 = PTR_DAT_1801e5048;
      DAT_1801f0198 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
      DAT_1801f02c8 = plVar12;
      if (plVar12 == (longlong *)0x0) {
        lVar9 = PyErr_Occurred();
        if (lVar9 == 0) {
          plVar12 = (longlong *)FUN_1801bb940(lVar14);
          puVar18 = PTR_DAT_1801e5048;
        }
        else {
          plVar12 = (longlong *)0x0;
          puVar18 = PTR_DAT_1801e5048;
        }
      }
      else {
        *plVar12 = *plVar12 + 1;
      }
    }
    if (plVar12 == (longlong *)0x0) {
      iVar6 = 0x574;
      iVar19 = 0xe7a3;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    if (*(code **)(plVar12[1] + 0x90) == (code *)0x0) {
      local_110 = (longlong *)PyObject_GetAttr(plVar12,*(undefined8 *)(puVar18 + 0x3898));
    }
    else {
      local_110 = (longlong *)(**(code **)(plVar12[1] + 0x90))();
    }
    if (local_110 == (longlong *)0x0) {
      iVar6 = 0x574;
      iVar19 = 0xe7a5;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    *plVar12 = *plVar12 + -1;
    if (*plVar12 == 0) {
      _Py_Dealloc(plVar12);
    }
    if (*(code **)(local_110[1] + 0x90) == (code *)0x0) {
      plVar12 = (longlong *)PyObject_GetAttr(local_110,*(undefined8 *)(PTR_DAT_1801e5048 + 0x22f8));
    }
    else {
      plVar12 = (longlong *)(**(code **)(local_110[1] + 0x90))();
    }
    if (plVar12 == (longlong *)0x0) {
      iVar6 = 0x574;
      iVar19 = 0xe7a8;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    *local_110 = *local_110 + -1;
    if (*local_110 == 0) {
      _Py_Dealloc();
    }
    if (DAT_1801f16e0 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
      if (DAT_1801f09c0 == (longlong *)0x0) {
        uVar10 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x27d0);
        local_110 = (longlong *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar10);
        if ((local_110 == (longlong *)0x0) && (lVar14 = PyErr_Occurred(), lVar14 == 0)) {
          PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar10);
        }
      }
      else {
        *DAT_1801f09c0 = *DAT_1801f09c0 + 1;
        local_110 = DAT_1801f09c0;
      }
    }
    else {
      lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x27d0);
      local_110 = (longlong *)
                  _PyDict_GetItem_KnownHash
                            (*(longlong *)PTR_DAT_1801e5048,lVar14,*(undefined8 *)(lVar14 + 0x18));
      DAT_1801f16e0 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
      DAT_1801f09c0 = local_110;
      if (local_110 == (longlong *)0x0) {
        lVar9 = PyErr_Occurred();
        if (lVar9 == 0) {
          local_110 = (longlong *)FUN_1801bb940(lVar14);
        }
        else {
          local_110 = (longlong *)0x0;
        }
      }
      else {
        *local_110 = *local_110 + 1;
      }
    }
    if (local_110 == (longlong *)0x0) {
      iVar6 = 0x574;
      iVar19 = 0xe7ab;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    plVar13 = (longlong *)0x0;
    lVar14 = 0;
    if (((code *)plVar12[1] == PyMethod_Type_exref) &&
       (plVar13 = (longlong *)plVar12[3], plVar13 != (longlong *)0x0)) {
      plVar15 = (longlong *)plVar12[2];
      *plVar13 = *plVar13 + 1;
      *plVar15 = *plVar15 + 1;
      *plVar12 = *plVar12 + -1;
      if (*plVar12 == 0) {
        _Py_Dealloc(plVar12);
      }
      lVar14 = 1;
      plVar12 = plVar15;
    }
    local_90[1] = plVar13;
    local_90[2] = local_110;
    plVar15 = (longlong *)
              FUN_1801bbf50((longlong)plVar12,local_90 + (2 - lVar14),(ulonglong)((int)lVar14 + 1));
    if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
      _Py_Dealloc(plVar13);
    }
    *local_110 = *local_110 + -1;
    if (*local_110 == 0) {
      _Py_Dealloc();
    }
    local_110 = (longlong *)0x0;
    if (plVar15 == (longlong *)0x0) {
      iVar6 = 0x574;
      iVar19 = 0xe7c0;
      plVar13 = (longlong *)0x0;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    *plVar12 = *plVar12 + -1;
    if (*plVar12 == 0) {
      _Py_Dealloc(plVar12);
    }
    plVar13 = (longlong *)0x0;
    lVar14 = 0;
    if (((code *)plVar7[1] == PyMethod_Type_exref) &&
       (plVar13 = (longlong *)plVar7[3], plVar13 != (longlong *)0x0)) {
      plVar20 = (longlong *)plVar7[2];
      *plVar13 = *plVar13 + 1;
      *plVar20 = *plVar20 + 1;
      *plVar7 = *plVar7 + -1;
      if (*plVar7 == 0) {
        _Py_Dealloc(plVar7);
      }
      lVar14 = 1;
      plVar7 = plVar20;
    }
    local_48 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x1ad8);
    local_40 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x4d40);
    local_38 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x3728);
    local_58 = plVar13;
    local_50 = plVar15;
    plVar8 = (longlong *)
             FUN_1801bbf50((longlong)plVar7,local_90 + (8 - lVar14),(ulonglong)((int)lVar14 + 4));
    if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
      _Py_Dealloc(plVar13);
    }
    plVar12 = (longlong *)0x0;
    *plVar15 = *plVar15 + -1;
    if (*plVar15 == 0) {
      _Py_Dealloc(plVar15);
    }
    plVar13 = (longlong *)0x0;
    if (plVar8 == (longlong *)0x0) {
      iVar6 = 0x574;
      iVar19 = 0xe7d7;
      plVar20 = (longlong *)0x0;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    *plVar7 = *plVar7 + -1;
    if (*plVar7 == 0) {
      _Py_Dealloc(plVar7);
    }
    puVar18 = PTR_DAT_1801e5048;
    plVar15 = (longlong *)0x0;
    plVar20 = (longlong *)0x0;
    local_a0 = plVar8;
    if (DAT_1801f05a0 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
      if (DAT_1801f16b0 == (longlong *)0x0) {
        uVar10 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x37e0);
        plVar7 = (longlong *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar10);
        puVar18 = PTR_DAT_1801e5048;
        if ((plVar7 == (longlong *)0x0) &&
           (lVar14 = PyErr_Occurred(), puVar18 = PTR_DAT_1801e5048, lVar14 == 0)) {
          PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar10);
          puVar18 = PTR_DAT_1801e5048;
        }
      }
      else {
        *DAT_1801f16b0 = *DAT_1801f16b0 + 1;
        plVar7 = DAT_1801f16b0;
      }
    }
    else {
      lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x37e0);
      plVar7 = (longlong *)
               _PyDict_GetItem_KnownHash
                         (*(longlong *)PTR_DAT_1801e5048,lVar14,*(undefined8 *)(lVar14 + 0x18));
      puVar18 = PTR_DAT_1801e5048;
      DAT_1801f05a0 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
      DAT_1801f16b0 = plVar7;
      if (plVar7 == (longlong *)0x0) {
        lVar9 = PyErr_Occurred();
        if (lVar9 == 0) {
          plVar7 = (longlong *)FUN_1801bb940(lVar14);
          puVar18 = PTR_DAT_1801e5048;
        }
        else {
          plVar7 = (longlong *)0x0;
          puVar18 = PTR_DAT_1801e5048;
        }
      }
      else {
        *plVar7 = *plVar7 + 1;
      }
    }
    if (plVar7 == (longlong *)0x0) {
      iVar6 = 0x575;
      iVar19 = 0xe7e5;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    if (*(code **)(plVar7[1] + 0x90) == (code *)0x0) {
      plVar13 = (longlong *)PyObject_GetAttr(plVar7,*(undefined8 *)(puVar18 + 0x3898));
    }
    else {
      plVar13 = (longlong *)(**(code **)(plVar7[1] + 0x90))();
    }
    if (plVar13 == (longlong *)0x0) {
      iVar6 = 0x575;
      iVar19 = 0xe7e7;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    *plVar7 = *plVar7 + -1;
    if (*plVar7 == 0) {
      _Py_Dealloc(plVar7);
    }
    if (*(code **)(plVar13[1] + 0x90) == (code *)0x0) {
      plVar7 = (longlong *)PyObject_GetAttr(plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2660));
    }
    else {
      plVar7 = (longlong *)(**(code **)(plVar13[1] + 0x90))();
    }
    if (plVar7 == (longlong *)0x0) {
      iVar6 = 0x575;
      iVar19 = 0xe7ea;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    *plVar13 = *plVar13 + -1;
    if (*plVar13 == 0) {
      _Py_Dealloc();
    }
    lVar14 = 0;
    if (((code *)plVar7[1] == PyMethod_Type_exref) &&
       (plVar15 = (longlong *)plVar7[3], plVar15 != (longlong *)0x0)) {
      plVar13 = (longlong *)plVar7[2];
      *plVar15 = *plVar15 + 1;
      *plVar13 = *plVar13 + 1;
      *plVar7 = *plVar7 + -1;
      if (*plVar7 == 0) {
        _Py_Dealloc(plVar7);
      }
      lVar14 = 1;
      plVar7 = plVar13;
    }
    local_90[3] = plVar15;
    local_70 = plVar8;
    plVar20 = (longlong *)
              FUN_1801bbf50((longlong)plVar7,local_90 + (4 - lVar14),(ulonglong)((int)lVar14 + 1));
    if ((plVar15 != (longlong *)0x0) && (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
      _Py_Dealloc(plVar15);
    }
    plVar13 = (longlong *)0x0;
    if (plVar20 == (longlong *)0x0) {
      iVar6 = 0x575;
      iVar19 = 0xe7ff;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    *plVar7 = *plVar7 + -1;
    if (*plVar7 == 0) {
      _Py_Dealloc(plVar7);
    }
    plVar7 = (longlong *)0x0;
    iVar6 = FUN_1801c28c0((undefined *)plVar20);
    if (iVar6 < 0) {
      iVar6 = 0x575;
      iVar19 = 0xe803;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    *plVar20 = *plVar20 + -1;
    if (*plVar20 == 0) {
      _Py_Dealloc(plVar20);
    }
    if (iVar6 != 0) {
      plVar20 = (longlong *)PyTuple_New(2);
      if (plVar20 == (longlong *)0x0) {
        iVar6 = 0x578;
        iVar19 = 0xe82c;
        puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      }
      else {
        *plVar8 = *plVar8 + 1;
        puVar18 = PTR_DAT_1801e5048;
        plVar20[3] = (longlong)plVar8;
        plVar15 = *(longlong **)(puVar18 + 0x3c90);
        *plVar15 = *plVar15 + 1;
        plVar20[4] = *(longlong *)(puVar18 + 0x3c90);
        plVar7 = (longlong *)PyDict_New();
        if (plVar7 == (longlong *)0x0) {
          iVar6 = 0x578;
          iVar19 = 0xe834;
          puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
        }
        else {
          iVar6 = PyDict_SetItem(plVar7,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2518),
                                 *(undefined8 *)(PTR_DAT_1801e5048 + 0x4a60));
          if (iVar6 < 0) {
            iVar6 = 0x578;
            iVar19 = 0xe836;
            puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
          }
          else {
            plVar13 = (longlong *)FUN_1801bbe10(DAT_1801ef4b0,plVar20,plVar7);
            if (plVar13 == (longlong *)0x0) {
              iVar6 = 0x578;
              iVar19 = 0xe837;
              puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
            }
            else {
              *plVar20 = *plVar20 + -1;
              if (*plVar20 == 0) {
                _Py_Dealloc(plVar20);
              }
              plVar20 = (longlong *)0x0;
              *plVar7 = *plVar7 + -1;
              if (*plVar7 == 0) {
                _Py_Dealloc(plVar7);
              }
              plVar7 = (longlong *)0x0;
              local_e0 = FUN_1801bc150((longlong)plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2668)
                                      );
              if (local_e0 == (longlong *)0x0) {
                iVar6 = 0x578;
                iVar19 = 0xe83b;
                puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
              }
              else {
                plVar20 = FUN_1801bc150((longlong)plVar13,
                                        *(undefined8 *)(PTR_DAT_1801e5048 + 0x2588));
                if (plVar20 == (longlong *)0x0) {
                  iVar19 = 0xe83d;
                }
                else {
                  plVar12 = (longlong *)0x0;
                  uVar11 = 0;
                  if (((code *)plVar20[1] == PyMethod_Type_exref) &&
                     (plVar12 = (longlong *)plVar20[3], plVar12 != (longlong *)0x0)) {
                    plVar15 = (longlong *)plVar20[2];
                    *plVar12 = *plVar12 + 1;
                    *plVar15 = *plVar15 + 1;
                    *plVar20 = *plVar20 + -1;
                    if (*plVar20 == 0) {
                      _Py_Dealloc();
                    }
                    uVar11 = 1;
                    plVar20 = plVar15;
                  }
                  local_60 = 0;
                  local_68 = plVar12;
                  plVar15 = (longlong *)
                            FUN_1801bbf50((longlong)plVar20,local_90 + (6 - uVar11),uVar11);
                  if ((plVar12 != (longlong *)0x0) && (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
                    _Py_Dealloc(plVar12);
                  }
                  if (plVar15 != (longlong *)0x0) {
                    *plVar20 = *plVar20 + -1;
                    if (*plVar20 == 0) {
                      _Py_Dealloc(plVar20);
                    }
                    *plVar13 = *plVar13 + -1;
                    local_a8 = plVar15;
                    if (*plVar13 == 0) {
                      _Py_Dealloc(plVar13);
                    }
                    local_100 = (longlong *)_PyThreadState_UncheckedGet();
                    puVar4 = (undefined8 *)local_100[0x12];
                    do {
                      puVar17 = puVar4;
                      pcVar1 = (code *)puVar17[1];
                      if ((pcVar1 != (code *)0x0) && (pcVar1 != _Py_NoneStruct_exref)) break;
                      puVar4 = (undefined8 *)puVar17[3];
                    } while ((undefined8 *)puVar17[3] != (undefined8 *)0x0);
                    local_d0 = (longlong *)*puVar17;
                    plVar12 = (longlong *)puVar17[2];
                    if (local_d0 != (longlong *)0x0) {
                      *local_d0 = *local_d0 + 1;
                    }
                    if (pcVar1 != (code *)0x0) {
                      *(longlong *)pcVar1 = *(longlong *)pcVar1 + 1;
                    }
                    if (plVar12 != (longlong *)0x0) {
                      *plVar12 = *plVar12 + 1;
                    }
                    puVar18 = PTR_DAT_1801e5048;
                    local_118 = pcVar1;
                    local_d8 = plVar12;
                    if (DAT_1801eff78 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
                      if (DAT_1801f0918 == (longlong *)0x0) {
                        uVar10 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x30c0);
                        plVar13 = (longlong *)
                                  FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar10);
                        puVar18 = PTR_DAT_1801e5048;
                        if ((plVar13 == (longlong *)0x0) &&
                           (lVar14 = PyErr_Occurred(), puVar18 = PTR_DAT_1801e5048, lVar14 == 0)) {
                          PyErr_Format(*(undefined8 *)PyExc_NameError_exref,
                                       "name \'%U\' is not defined",uVar10);
                          puVar18 = PTR_DAT_1801e5048;
                        }
                      }
                      else {
                        *DAT_1801f0918 = *DAT_1801f0918 + 1;
                        plVar13 = DAT_1801f0918;
                      }
                    }
                    else {
                      lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x30c0);
                      plVar13 = (longlong *)
                                _PyDict_GetItem_KnownHash
                                          (*(longlong *)PTR_DAT_1801e5048,lVar14,
                                           *(undefined8 *)(lVar14 + 0x18));
                      puVar18 = PTR_DAT_1801e5048;
                      DAT_1801eff78 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
                      DAT_1801f0918 = plVar13;
                      if (plVar13 == (longlong *)0x0) {
                        lVar9 = PyErr_Occurred();
                        if (lVar9 == 0) {
                          plVar13 = (longlong *)FUN_1801bb940(lVar14);
                          puVar18 = PTR_DAT_1801e5048;
                        }
                        else {
                          plVar13 = (longlong *)0x0;
                          puVar18 = PTR_DAT_1801e5048;
                        }
                      }
                      else {
                        *plVar13 = *plVar13 + 1;
                      }
                    }
                    if (plVar13 == (longlong *)0x0) {
                      iVar6 = 0xe86b;
                      plVar15 = (longlong *)0x0;
                    }
                    else {
                      if (*(code **)(plVar13[1] + 0x90) == (code *)0x0) {
                        plVar20 = (longlong *)
                                  PyObject_GetAttr(plVar13,*(undefined8 *)(puVar18 + 0x32f0));
                      }
                      else {
                        plVar20 = (longlong *)(**(code **)(plVar13[1] + 0x90))();
                      }
                      plVar15 = plVar20;
                      if (plVar20 == (longlong *)0x0) {
                        iVar6 = 0xe86d;
                      }
                      else {
                        *plVar13 = *plVar13 + -1;
                        if (*plVar13 == 0) {
                          _Py_Dealloc();
                        }
                        plVar13 = (longlong *)0x0;
                        uVar16 = 0;
                        if (((code *)plVar20[1] == PyMethod_Type_exref) &&
                           (plVar13 = (longlong *)plVar20[3], uVar16 = 0, plVar13 != (longlong *)0x0
                           )) {
                          plVar15 = (longlong *)plVar20[2];
                          *plVar13 = *plVar13 + 1;
                          *plVar15 = *plVar15 + 1;
                          *plVar20 = *plVar20 + -1;
                          if (*plVar20 == 0) {
                            _Py_Dealloc(plVar20);
                          }
                          uVar16 = 1;
                        }
                        local_90[0] = local_a8;
                        local_98 = plVar13;
                        plVar8 = (longlong *)
                                 FUN_1801bbf50((longlong)plVar15,local_90 + -(ulonglong)uVar16,
                                               (ulonglong)(uVar16 + 1));
                        if ((plVar13 != (longlong *)0x0) &&
                           (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
                          _Py_Dealloc(plVar13);
                        }
                        plVar13 = (longlong *)0x0;
                        if (plVar8 != (longlong *)0x0) {
                          *plVar15 = *plVar15 + -1;
                          if (*plVar15 == 0) {
                            _Py_Dealloc(plVar15);
                          }
                          plVar7 = (longlong *)0x0;
                          plVar20 = (longlong *)0x0;
                          if ((local_d0 != (longlong *)0x0) &&
                             (*local_d0 = *local_d0 + -1, *local_d0 == 0)) {
                            _Py_Dealloc();
                          }
                          if ((pcVar1 != (code *)0x0) &&
                             (*(longlong *)pcVar1 = *(longlong *)pcVar1 + -1,
                             *(longlong *)pcVar1 == 0)) {
                            _Py_Dealloc(pcVar1);
                          }
                          local_e8 = plVar8;
                          if ((plVar12 != (longlong *)0x0) &&
                             (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
                            _Py_Dealloc(plVar12);
                          }
                          plVar12 = local_e0;
                          plVar15 = (longlong *)
                                    FUN_1801bbe10((longlong)local_e0,
                                                  *(undefined8 *)(PTR_DAT_1801e5048 + 0x4fd0),0);
                          *plVar12 = *plVar12 + -1;
                          if (*plVar12 == 0) {
                            _Py_Dealloc(plVar12);
                          }
                          if (plVar15 == (longlong *)0x0) {
                            iVar6 = 0x578;
                            iVar19 = 0xe8cd;
                          }
                          else {
                            *plVar15 = *plVar15 + -1;
                            if (*plVar15 == 0) {
                              _Py_Dealloc(plVar15);
                            }
                            plVar12 = plVar8;
                            if ((*(uint *)(plVar8[1] + 0xa8) & 0x20000000) == 0) {
                              plVar12 = (longlong *)PyDict_New();
                              if (plVar12 == (longlong *)0x0) {
                                iVar6 = 0x57c;
                                iVar19 = 0xe8ef;
                                plVar13 = (longlong *)0x0;
                                goto LAB_18005be32;
                              }
                              *plVar8 = *plVar8 + -1;
                              local_e8 = plVar12;
                              if (*plVar8 == 0) {
                                _Py_Dealloc(plVar8);
                                local_e8 = plVar12;
                              }
                            }
                            plVar13 = (longlong *)PyDict_New();
                            if (plVar13 == (longlong *)0x0) {
                              iVar19 = 0xe905;
                            }
                            else {
                              iVar6 = PyDict_SetItem(plVar13,*(undefined8 *)
                                                              (PTR_DAT_1801e5048 + 0x43f8),
                                                     *(undefined8 *)(PTR_DAT_1801e5048 + 0x45b8));
                              if (iVar6 < 0) {
                                iVar19 = 0xe907;
                              }
                              else if (plVar12 == (longlong *)0x0) {
                                PyErr_Format(*(undefined8 *)PyExc_UnboundLocalError_exref,
                                             "local variable \'%s\' referenced before assignment",
                                             "config");
                                iVar19 = 0xe908;
                              }
                              else {
                                iVar6 = PyDict_SetItem(plVar13,*(undefined8 *)
                                                                (PTR_DAT_1801e5048 + 0x1f30),plVar12
                                                      );
                                lVar14 = local_b0;
                                if (-1 < iVar6) goto LAB_18005c384;
                                iVar19 = 0xe909;
                              }
                            }
                            iVar6 = 0x57d;
                          }
LAB_18005be32:
                          local_110 = (longlong *)0x0;
                          plVar12 = (longlong *)0x0;
                          puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                          goto LAB_18005be3c;
                        }
                        iVar6 = 0xe882;
                      }
                    }
                    puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                    local_f0 = (longlong *)0x0;
                    if ((plVar15 != (longlong *)0x0) && (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
                      _Py_Dealloc(plVar15);
                    }
                    local_108 = (longlong *)0x0;
                    if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
                      _Py_Dealloc(plVar13);
                    }
                    local_f8 = (longlong *)0x0;
                    local_110 = (longlong *)0x0;
                    FUN_1801c1020("main.Api.get_oem_config",iVar6,0x579,puVar18);
                    uVar10 = FUN_1801bc330((longlong)local_100,&local_f0,&local_108,&local_f8);
                    plVar20 = local_f0;
                    plVar13 = local_f8;
                    plVar7 = local_108;
                    if ((int)uVar10 < 0) {
                      iVar19 = 0xe89e;
                    }
                    else {
                      plVar15 = (longlong *)PyTuple_Pack(3,local_f0,local_108,local_f8);
                      plVar12 = local_e0;
                      if (plVar15 == (longlong *)0x0) {
                        iVar19 = 0xe8a2;
                      }
                      else {
                        plVar8 = (longlong *)FUN_1801bbe10((longlong)local_e0,plVar15,0);
                        *plVar12 = *plVar12 + -1;
                        if (*plVar12 == 0) {
                          _Py_Dealloc(plVar12);
                        }
                        *plVar15 = *plVar15 + -1;
                        if (*plVar15 == 0) {
                          _Py_Dealloc(plVar15);
                        }
                        plVar12 = (longlong *)0x0;
                        if (plVar8 == (longlong *)0x0) {
                          iVar19 = 0xe8a7;
                        }
                        else {
                          iVar6 = FUN_1801c28c0((undefined *)plVar8);
                          *plVar8 = *plVar8 + -1;
                          if (*plVar8 == 0) {
                            _Py_Dealloc(plVar8);
                          }
                          if (iVar6 < 0) {
                            iVar19 = 0xe8ab;
                          }
                          else {
                            if (iVar6 != 0) {
                              if ((plVar20 != (longlong *)0x0) &&
                                 (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
                                _Py_Dealloc(plVar20);
                              }
                              plVar20 = (longlong *)0x0;
                              if ((plVar7 != (longlong *)0x0) &&
                                 (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
                                _Py_Dealloc(plVar7);
                              }
                              plVar7 = (longlong *)0x0;
                              if ((plVar13 != (longlong *)0x0) &&
                                 (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
                                _Py_Dealloc(plVar13);
                              }
                              plVar13 = (longlong *)0x0;
                              FUN_1801bc0e0((longlong)local_100,local_d0,pcVar1,local_d8);
                              PyErr_Format(*(undefined8 *)PyExc_UnboundLocalError_exref,
                                           "local variable \'%s\' referenced before assignment",
                                           "config");
                              iVar6 = 0x57b;
                              local_110 = (longlong *)0x0;
                              iVar19 = 0xe8e3;
                              puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                              goto LAB_18005be3c;
                            }
                            lVar14 = PyThreadState_Get();
                            FUN_1801bb760(lVar14,plVar20,plVar7,plVar13);
                            plVar20 = (longlong *)0x0;
                            plVar7 = (longlong *)0x0;
                            plVar13 = (longlong *)0x0;
                            iVar19 = 0xe8b3;
                          }
                        }
                      }
                    }
                    puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                    plVar12 = (longlong *)0x0;
                    iVar6 = 0x578;
                    FUN_1801bc0e0((longlong)local_100,local_d0,local_118,local_d8);
                    goto LAB_18005be3c;
                  }
                  iVar19 = 0xe851;
                }
                puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                plVar7 = (longlong *)0x0;
                iVar6 = 0x578;
                *local_e0 = *local_e0 + -1;
                plVar12 = (longlong *)0x0;
                if (*local_e0 == 0) {
                  _Py_Dealloc();
                }
              }
            }
          }
        }
      }
      goto LAB_18005be3c;
    }
    plVar20 = (longlong *)PyDict_New();
    if (plVar20 == (longlong *)0x0) {
      iVar6 = 0x576;
      iVar19 = 0xe810;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    iVar6 = PyDict_SetItem(plVar20,*(undefined8 *)(PTR_DAT_1801e5048 + 0x43f8),
                           *(undefined8 *)(PTR_DAT_1801e5048 + 0x45b8));
    if (iVar6 < 0) {
      iVar6 = 0x576;
      iVar19 = 0xe812;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    plVar7 = (longlong *)PyDict_New();
    if (plVar7 == (longlong *)0x0) {
      iVar6 = 0x576;
      iVar19 = 0xe813;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    iVar6 = PyDict_SetItem(plVar20,*(undefined8 *)(PTR_DAT_1801e5048 + 0x1f30),plVar7);
    if (iVar6 < 0) {
      iVar6 = 0x576;
      iVar19 = 0xe815;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005be3c;
    }
    *plVar7 = *plVar7 + -1;
    lVar14 = local_b0;
    plVar13 = plVar20;
    if (*plVar7 == 0) {
      _Py_Dealloc(plVar7);
      lVar14 = local_b0;
    }
LAB_18005c384:
    FUN_1801bc0e0(lVar14,local_b8,local_c8,local_c0);
    goto LAB_18005c397;
  }
  iVar6 = 0x574;
  iVar19 = 0xe79b;
  plVar20 = plVar15;
  puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
LAB_18005be3c:
  if ((plVar20 != (longlong *)0x0) && (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
    _Py_Dealloc(plVar20);
  }
  local_f0 = (longlong *)0x0;
  if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
    _Py_Dealloc(plVar7);
  }
  plVar20 = (longlong *)0x0;
  local_108 = (longlong *)0x0;
  if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
    _Py_Dealloc(plVar13);
  }
  local_f8 = (longlong *)0x0;
  if ((plVar12 != (longlong *)0x0) && (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
    _Py_Dealloc(plVar12);
  }
  if ((local_110 != (longlong *)0x0) && (*local_110 = *local_110 + -1, *local_110 == 0)) {
    _Py_Dealloc();
  }
  lVar14 = local_b0;
  puVar2 = *(undefined **)PyExc_Exception_exref;
  puVar3 = *(undefined **)(local_b0 + 0x58);
  if (puVar3 == puVar2) {
LAB_18005befd:
    FUN_1801c1020("main.Api.get_oem_config",iVar19,iVar6,puVar18);
    uVar10 = FUN_1801bc330(lVar14,&local_f8,&local_108,&local_f0);
    plVar20 = local_108;
    if ((int)uVar10 < 0) {
      iVar6 = 0x57e;
      iVar19 = 0xe928;
      plVar13 = local_f8;
      plVar12 = local_f0;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
    }
    else {
      lVar9 = *local_108;
      *local_108 = lVar9 + 1;
      if ((code *)local_108[1] == PyUnicode_Type_exref) {
        *local_108 = lVar9 + 2;
        plVar13 = local_108;
      }
      else {
        plVar13 = (longlong *)PyObject_Str(local_108);
      }
      if (plVar13 == (longlong *)0x0) {
        iVar6 = 0x57f;
        iVar19 = 0xe937;
LAB_18005c060:
        puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
        local_110 = (longlong *)0x0;
        local_108 = (longlong *)0x0;
        local_100 = (longlong *)0x0;
        lVar14 = _PyThreadState_UncheckedGet();
      }
      else {
        plVar12 = (longlong *)PyUnicode_Concat(*(undefined8 *)(PTR_DAT_1801e5048 + 0x1060),plVar13);
        if (plVar12 == (longlong *)0x0) {
          iVar6 = 0x57f;
          iVar19 = 0xe939;
          plVar15 = plVar12;
LAB_18005c15a:
          puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
          local_110 = (longlong *)0x0;
          local_108 = (longlong *)0x0;
          local_100 = (longlong *)0x0;
          lVar14 = _PyThreadState_UncheckedGet();
          *plVar13 = *plVar13 + -1;
          if (*plVar13 == 0) {
            _Py_Dealloc(plVar13);
          }
          plVar12 = plVar15;
          if (plVar15 == (longlong *)0x0) goto LAB_18005c1a1;
        }
        else {
          *plVar13 = *plVar13 + -1;
          if (*plVar13 == 0) {
            _Py_Dealloc(plVar13);
          }
          plVar15 = (longlong *)0x0;
          local_98 = (longlong *)0x0;
          local_90[0] = plVar12;
          plVar13 = (longlong *)FUN_1801bbf50(DAT_1801f1718,local_90,0x8000000000000001);
          puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
          if (plVar13 != (longlong *)0x0) {
            *plVar12 = *plVar12 + -1;
            if (*plVar12 == 0) {
              _Py_Dealloc(plVar12);
            }
            *plVar13 = *plVar13 + -1;
            if (*plVar13 == 0) {
              _Py_Dealloc(plVar13);
            }
            plVar13 = (longlong *)PyDict_New();
            if (plVar13 == (longlong *)0x0) {
              iVar6 = 0x580;
              iVar19 = 0xe949;
              goto LAB_18005c060;
            }
            iVar6 = PyDict_SetItem(plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x43f8),
                                   *(undefined8 *)(PTR_DAT_1801e5048 + 0x25f0));
            if (iVar6 < 0) {
              iVar19 = 0xe94b;
            }
            else {
              if ((code *)plVar20[1] == PyUnicode_Type_exref) {
                *plVar20 = *plVar20 + 1;
                plVar15 = plVar20;
              }
              else {
                plVar15 = (longlong *)PyObject_Str(plVar20);
              }
              if (plVar15 == (longlong *)0x0) {
                iVar19 = 0xe94c;
              }
              else {
                iVar6 = PyDict_SetItem(plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x3480),plVar15);
                if (iVar6 < 0) {
                  iVar19 = 0xe94e;
                }
                else {
                  *plVar15 = *plVar15 + -1;
                  if (*plVar15 == 0) {
                    _Py_Dealloc(plVar15);
                  }
                  plVar15 = (longlong *)PyDict_New();
                  if (plVar15 == (longlong *)0x0) {
                    iVar19 = 0xe950;
                  }
                  else {
                    iVar6 = PyDict_SetItem(plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x1f30),
                                           plVar15);
                    if (-1 < iVar6) {
                      *plVar15 = *plVar15 + -1;
                      if (*plVar15 == 0) {
                        _Py_Dealloc(plVar15);
                      }
                      *local_f0 = *local_f0 + -1;
                      if (*local_f0 == 0) {
                        _Py_Dealloc();
                      }
                      *plVar20 = *plVar20 + -1;
                      if (*plVar20 == 0) {
                        _Py_Dealloc(plVar20);
                      }
                      *local_f8 = *local_f8 + -1;
                      if (*local_f8 == 0) {
                        _Py_Dealloc();
                      }
                      *plVar20 = *plVar20 + -1;
                      if (*plVar20 == 0) {
                        _Py_Dealloc(plVar20);
                      }
                      goto LAB_18005c384;
                    }
                    iVar19 = 0xe952;
                  }
                }
              }
            }
            iVar6 = 0x580;
            goto LAB_18005c15a;
          }
          iVar6 = 0x57f;
          iVar19 = 0xe93c;
          local_110 = (longlong *)0x0;
          local_108 = (longlong *)0x0;
          local_100 = (longlong *)0x0;
          lVar14 = _PyThreadState_UncheckedGet();
        }
        *plVar12 = *plVar12 + -1;
        if (*plVar12 == 0) {
          _Py_Dealloc(plVar12);
        }
      }
LAB_18005c1a1:
      puVar4 = *(undefined8 **)(lVar14 + 0x90);
      local_d0 = (longlong *)*puVar4;
      local_e0 = (longlong *)puVar4[1];
      local_118 = (code *)puVar4[2];
      *puVar4 = 0;
      puVar4[1] = 0;
      puVar4[2] = 0;
      uVar10 = FUN_1801bc330(lVar14,&local_110,&local_108,&local_100);
      if ((int)uVar10 < 0) {
        local_d8 = *(longlong **)(lVar14 + 0x68);
        plVar13 = *(longlong **)(lVar14 + 0x58);
        plVar12 = *(longlong **)(lVar14 + 0x60);
        *(undefined8 *)(lVar14 + 0x58) = 0;
        *(undefined8 *)(lVar14 + 0x60) = 0;
        *(undefined8 *)(lVar14 + 0x68) = 0;
      }
      else {
        local_d8 = local_100;
        plVar13 = local_110;
        plVar12 = local_108;
      }
      *plVar20 = *plVar20 + -1;
      if (*plVar20 == 0) {
        _Py_Dealloc(plVar20);
      }
      FUN_1801bc0e0(lVar14,local_d0,local_e0,local_118);
      FUN_1801bb760(lVar14,plVar13,plVar12,local_d8);
      plVar13 = local_f8;
      lVar14 = local_b0;
      plVar12 = local_f0;
    }
  }
  else {
    plVar13 = (longlong *)0x0;
    plVar12 = (longlong *)0x0;
    if (puVar3 != (undefined *)0x0) {
      if ((*(uint *)(*(longlong *)(puVar2 + 8) + 0xa8) & 0x4000000) == 0) {
        uVar11 = FUN_1801bdde0(puVar3,puVar2);
        iVar5 = (int)uVar11;
      }
      else {
        uVar10 = FUN_1801bb510(puVar3,(longlong)puVar2);
        iVar5 = (int)uVar10;
      }
      if (iVar5 != 0) goto LAB_18005befd;
    }
  }
  puVar4 = *(undefined8 **)(lVar14 + 0x90);
  plVar15 = (longlong *)*puVar4;
  local_118 = (code *)puVar4[2];
  plVar7 = (longlong *)puVar4[1];
  *puVar4 = local_b8;
  puVar4[1] = local_c8;
  puVar4[2] = local_c0;
  if ((plVar15 != (longlong *)0x0) && (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
    _Py_Dealloc(plVar15);
  }
  if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
    _Py_Dealloc(plVar7);
  }
  if ((local_118 != (code *)0x0) &&
     (*(longlong *)local_118 = *(longlong *)local_118 + -1, *(longlong *)local_118 == 0)) {
    _Py_Dealloc();
  }
  if ((plVar12 != (longlong *)0x0) && (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
    _Py_Dealloc(plVar12);
  }
  if ((plVar20 != (longlong *)0x0) && (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
    _Py_Dealloc(plVar20);
  }
  if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
    _Py_Dealloc(plVar13);
  }
  FUN_1801c1020("main.Api.get_oem_config",iVar19,iVar6,puVar18);
  plVar13 = (longlong *)0x0;
LAB_18005c397:
  if ((local_a0 != (longlong *)0x0) && (*local_a0 = *local_a0 + -1, *local_a0 == 0)) {
    _Py_Dealloc();
  }
  if ((local_a8 != (longlong *)0x0) && (*local_a8 = *local_a8 + -1, *local_a8 == 0)) {
    _Py_Dealloc();
  }
  if ((local_e8 != (longlong *)0x0) && (*local_e8 = *local_e8 + -1, *local_e8 == 0)) {
    _Py_Dealloc(local_e8);
  }
  return plVar13;
}

