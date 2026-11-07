
/* WARNING: Function: __security_check_cookie replaced with injection: security_check_cookie */

undefined * FUN_180059240(void)

{
  undefined *puVar1;
  undefined *puVar2;
  undefined8 *puVar3;
  int iVar4;
  int iVar5;
  code *pcVar6;
  longlong *plVar7;
  longlong *plVar8;
  longlong lVar9;
  code *pcVar10;
  code *pcVar11;
  ulonglong uVar13;
  longlong lVar14;
  code *pcVar15;
  code *pcVar16;
  undefined8 *puVar17;
  int iVar18;
  undefined *puVar19;
  code *pcVar20;
  longlong *plVar21;
  undefined1 auStack_168 [32];
  code *local_148;
  code *local_140;
  code *local_138;
  code *local_130;
  longlong *local_128;
  code *local_120;
  code *local_118;
  longlong *local_110;
  longlong *local_108;
  longlong local_100;
  longlong *local_f8;
  code *local_f0;
  longlong *local_e8;
  longlong *local_e0;
  longlong *local_d8;
  longlong local_d0;
  longlong *local_c8;
  code *local_c0;
  code *local_b8;
  longlong *local_b0;
  longlong *local_a8 [4];
  undefined8 local_88;
  code *local_80;
  code *local_78 [3];
  longlong *local_60;
  longlong *local_58 [4];
  ulonglong local_38;
  undefined8 uVar12;
  
  local_38 = DAT_1801e4000 ^ (ulonglong)auStack_168;
  plVar8 = (longlong *)0x0;
  plVar21 = (longlong *)0x0;
  local_c8 = (longlong *)0x0;
  local_f8 = (longlong *)0x0;
  local_118 = (code *)0x0;
  local_130 = (code *)0x0;
  local_128 = (longlong *)0x0;
  local_d0 = _PyThreadState_UncheckedGet();
  puVar3 = *(undefined8 **)(local_d0 + 0x90);
  do {
    puVar17 = puVar3;
    local_f0 = (code *)puVar17[1];
    if ((local_f0 != (code *)0x0) && (local_f0 != _Py_NoneStruct_exref)) break;
    puVar3 = (undefined8 *)puVar17[3];
  } while ((undefined8 *)puVar17[3] != (undefined8 *)0x0);
  local_d8 = (longlong *)*puVar17;
  local_e0 = (longlong *)puVar17[2];
  if (local_d8 != (longlong *)0x0) {
    *local_d8 = *local_d8 + 1;
  }
  if (local_f0 != (code *)0x0) {
    *(longlong *)local_f0 = *(longlong *)local_f0 + 1;
  }
  if (local_e0 != (longlong *)0x0) {
    *local_e0 = *local_e0 + 1;
  }
  puVar19 = PTR_DAT_1801e5048;
  if (DAT_1801f17b0 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
    if (DAT_1801f0948 == (code *)0x0) {
      uVar12 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x37e0);
      pcVar6 = (code *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar12);
      puVar19 = PTR_DAT_1801e5048;
      if ((pcVar6 == (code *)0x0) &&
         (lVar14 = PyErr_Occurred(), puVar19 = PTR_DAT_1801e5048, lVar14 == 0)) {
        PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar12);
        puVar19 = PTR_DAT_1801e5048;
      }
    }
    else {
      *(longlong *)DAT_1801f0948 = *(longlong *)DAT_1801f0948 + 1;
      pcVar6 = DAT_1801f0948;
    }
  }
  else {
    lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x37e0);
    pcVar6 = (code *)_PyDict_GetItem_KnownHash
                               (*(longlong *)PTR_DAT_1801e5048,lVar14,*(undefined8 *)(lVar14 + 0x18)
                               );
    puVar19 = PTR_DAT_1801e5048;
    DAT_1801f17b0 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
    DAT_1801f0948 = pcVar6;
    if (pcVar6 == (code *)0x0) {
      lVar9 = PyErr_Occurred();
      if (lVar9 == 0) {
        pcVar6 = (code *)FUN_1801bb940(lVar14);
        puVar19 = PTR_DAT_1801e5048;
      }
      else {
        pcVar6 = (code *)0x0;
        puVar19 = PTR_DAT_1801e5048;
      }
    }
    else {
      *(longlong *)pcVar6 = *(longlong *)pcVar6 + 1;
    }
  }
  if (pcVar6 != (code *)0x0) {
    if (*(code **)(*(longlong *)(pcVar6 + 8) + 0x90) == (code *)0x0) {
      pcVar16 = (code *)PyObject_GetAttr(pcVar6,*(undefined8 *)(puVar19 + 0x3898));
    }
    else {
      pcVar16 = (code *)(**(code **)(*(longlong *)(pcVar6 + 8) + 0x90))();
    }
    if (pcVar16 == (code *)0x0) {
      iVar5 = 0x563;
      iVar18 = 0xe487;
      plVar21 = plVar8;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    *(longlong *)pcVar6 = *(longlong *)pcVar6 + -1;
    if (*(longlong *)pcVar6 == 0) {
      _Py_Dealloc(pcVar6);
    }
    if (*(code **)(*(longlong *)(pcVar16 + 8) + 0x90) == (code *)0x0) {
      pcVar6 = (code *)PyObject_GetAttr(pcVar16,*(undefined8 *)(PTR_DAT_1801e5048 + 0x30a0));
    }
    else {
      pcVar6 = (code *)(**(code **)(*(longlong *)(pcVar16 + 8) + 0x90))();
    }
    if (pcVar6 == (code *)0x0) {
      iVar5 = 0x563;
      iVar18 = 0xe48a;
      plVar21 = plVar8;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    *(longlong *)pcVar16 = *(longlong *)pcVar16 + -1;
    if (*(longlong *)pcVar16 == 0) {
      _Py_Dealloc(pcVar16);
    }
    puVar19 = PTR_DAT_1801e5048;
    pcVar16 = (code *)0x0;
    if (DAT_1801f1048 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
      if (DAT_1801f0310 == (code *)0x0) {
        uVar12 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x37e0);
        pcVar15 = (code *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar12);
        puVar19 = PTR_DAT_1801e5048;
        local_130 = pcVar15;
        if ((pcVar15 == (code *)0x0) &&
           (lVar14 = PyErr_Occurred(), puVar19 = PTR_DAT_1801e5048, lVar14 == 0)) {
          PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar12);
          puVar19 = PTR_DAT_1801e5048;
        }
      }
      else {
        *(longlong *)DAT_1801f0310 = *(longlong *)DAT_1801f0310 + 1;
        local_130 = DAT_1801f0310;
        pcVar15 = DAT_1801f0310;
      }
    }
    else {
      lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x37e0);
      pcVar15 = (code *)_PyDict_GetItem_KnownHash
                                  (*(longlong *)PTR_DAT_1801e5048,lVar14,
                                   *(undefined8 *)(lVar14 + 0x18));
      puVar19 = PTR_DAT_1801e5048;
      DAT_1801f1048 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
      DAT_1801f0310 = pcVar15;
      local_130 = pcVar15;
      if (pcVar15 == (code *)0x0) {
        lVar9 = PyErr_Occurred();
        if (lVar9 == 0) {
          pcVar15 = (code *)FUN_1801bb940(lVar14);
          puVar19 = PTR_DAT_1801e5048;
          local_130 = pcVar15;
        }
        else {
          pcVar15 = (code *)0x0;
          local_130 = (code *)0x0;
          puVar19 = PTR_DAT_1801e5048;
        }
      }
      else {
        *(longlong *)pcVar15 = *(longlong *)pcVar15 + 1;
      }
    }
    if (pcVar15 == (code *)0x0) {
      iVar5 = 0x563;
      iVar18 = 0xe48d;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    if (*(code **)(*(longlong *)(pcVar15 + 8) + 0x90) == (code *)0x0) {
      local_128 = (longlong *)PyObject_GetAttr(pcVar15,*(undefined8 *)(puVar19 + 0x3898));
    }
    else {
      local_128 = (longlong *)(**(code **)(*(longlong *)(pcVar15 + 8) + 0x90))();
    }
    if (local_128 == (longlong *)0x0) {
      iVar5 = 0x563;
      iVar18 = 0xe48f;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    *(longlong *)pcVar15 = *(longlong *)pcVar15 + -1;
    if (*(longlong *)pcVar15 == 0) {
      _Py_Dealloc(pcVar15);
    }
    if (*(code **)(local_128[1] + 0x90) == (code *)0x0) {
      pcVar15 = (code *)PyObject_GetAttr(local_128,*(undefined8 *)(PTR_DAT_1801e5048 + 0x22f8));
    }
    else {
      pcVar15 = (code *)(**(code **)(local_128[1] + 0x90))();
    }
    local_130 = pcVar15;
    if (pcVar15 == (code *)0x0) {
      iVar5 = 0x563;
      iVar18 = 0xe492;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    *local_128 = *local_128 + -1;
    if (*local_128 == 0) {
      _Py_Dealloc();
    }
    if (DAT_1801f1340 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
      if (DAT_1801efd38 == (longlong *)0x0) {
        uVar12 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x27d0);
        local_128 = (longlong *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar12);
        if ((local_128 == (longlong *)0x0) && (lVar14 = PyErr_Occurred(), lVar14 == 0)) {
          PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar12);
        }
      }
      else {
        *DAT_1801efd38 = *DAT_1801efd38 + 1;
        local_128 = DAT_1801efd38;
      }
    }
    else {
      lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x27d0);
      local_128 = (longlong *)
                  _PyDict_GetItem_KnownHash
                            (*(longlong *)PTR_DAT_1801e5048,lVar14,*(undefined8 *)(lVar14 + 0x18));
      DAT_1801f1340 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
      DAT_1801efd38 = local_128;
      if (local_128 == (longlong *)0x0) {
        lVar9 = PyErr_Occurred();
        if (lVar9 == 0) {
          local_128 = (longlong *)FUN_1801bb940(lVar14);
        }
        else {
          local_128 = (longlong *)0x0;
        }
      }
      else {
        *local_128 = *local_128 + 1;
      }
    }
    if (local_128 == (longlong *)0x0) {
      iVar5 = 0x563;
      iVar18 = 0xe495;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    plVar8 = (longlong *)0x0;
    lVar14 = 0;
    pcVar16 = pcVar15;
    if ((*(code **)(pcVar15 + 8) == PyMethod_Type_exref) &&
       (plVar8 = *(longlong **)(pcVar15 + 0x18), plVar8 != (longlong *)0x0)) {
      pcVar16 = *(code **)(pcVar15 + 0x10);
      *plVar8 = *plVar8 + 1;
      *(longlong *)pcVar16 = *(longlong *)pcVar16 + 1;
      *(longlong *)pcVar15 = *(longlong *)pcVar15 + -1;
      local_130 = pcVar16;
      if (*(longlong *)pcVar15 == 0) {
        _Py_Dealloc(pcVar15);
      }
      lVar14 = 1;
    }
    local_b0 = plVar8;
    local_a8[0] = local_128;
    plVar7 = (longlong *)
             FUN_1801bbf50((longlong)pcVar16,local_a8 + -lVar14,(ulonglong)((int)lVar14 + 1));
    if ((plVar8 != (longlong *)0x0) && (*plVar8 = *plVar8 + -1, *plVar8 == 0)) {
      _Py_Dealloc(plVar8);
    }
    *local_128 = *local_128 + -1;
    if (*local_128 == 0) {
      _Py_Dealloc();
    }
    local_128 = (longlong *)0x0;
    if (plVar7 == (longlong *)0x0) {
      iVar5 = 0x563;
      iVar18 = 0xe4aa;
      pcVar16 = (code *)0x0;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    *(longlong *)pcVar16 = *(longlong *)pcVar16 + -1;
    if (*(longlong *)pcVar16 == 0) {
      _Py_Dealloc(pcVar16);
    }
    plVar21 = (longlong *)0x0;
    lVar14 = 0;
    if ((*(code **)(pcVar6 + 8) == PyMethod_Type_exref) &&
       (plVar21 = *(longlong **)(pcVar6 + 0x18), plVar21 != (longlong *)0x0)) {
      pcVar16 = *(code **)(pcVar6 + 0x10);
      *plVar21 = *plVar21 + 1;
      *(longlong *)pcVar16 = *(longlong *)pcVar16 + 1;
      *(longlong *)pcVar6 = *(longlong *)pcVar6 + -1;
      if (*(longlong *)pcVar6 == 0) {
        _Py_Dealloc(pcVar6);
      }
      lVar14 = 1;
      pcVar6 = pcVar16;
    }
    local_58[1] = *(longlong **)(PTR_DAT_1801e5048 + 0x1ad8);
    local_58[2] = *(longlong **)(PTR_DAT_1801e5048 + 0x4d40);
    local_58[3] = *(longlong **)(PTR_DAT_1801e5048 + 0x2d98);
    local_60 = plVar21;
    local_58[0] = plVar7;
    plVar8 = (longlong *)
             FUN_1801bbf50((longlong)pcVar6,local_58 + -lVar14,(ulonglong)((int)lVar14 + 4));
    if ((plVar21 != (longlong *)0x0) && (*plVar21 = *plVar21 + -1, *plVar21 == 0)) {
      _Py_Dealloc(plVar21);
    }
    *plVar7 = *plVar7 + -1;
    local_130 = (code *)0x0;
    if (*plVar7 == 0) {
      _Py_Dealloc(plVar7);
    }
    pcVar16 = (code *)0x0;
    if (plVar8 == (longlong *)0x0) {
      iVar5 = 0x563;
      iVar18 = 0xe4c1;
      plVar21 = (longlong *)0x0;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    *(longlong *)pcVar6 = *(longlong *)pcVar6 + -1;
    if (*(longlong *)pcVar6 == 0) {
      _Py_Dealloc(pcVar6);
    }
    puVar19 = PTR_DAT_1801e5048;
    plVar21 = (longlong *)0x0;
    local_c8 = plVar8;
    if (DAT_1801f1740 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
      if (DAT_1801efcd8 == (code *)0x0) {
        uVar12 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x37e0);
        pcVar6 = (code *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar12);
        puVar19 = PTR_DAT_1801e5048;
        if ((pcVar6 == (code *)0x0) &&
           (lVar14 = PyErr_Occurred(), puVar19 = PTR_DAT_1801e5048, lVar14 == 0)) {
          PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar12);
          puVar19 = PTR_DAT_1801e5048;
        }
      }
      else {
        *(longlong *)DAT_1801efcd8 = *(longlong *)DAT_1801efcd8 + 1;
        pcVar6 = DAT_1801efcd8;
      }
    }
    else {
      lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x37e0);
      pcVar6 = (code *)_PyDict_GetItem_KnownHash
                                 (*(longlong *)PTR_DAT_1801e5048,lVar14,
                                  *(undefined8 *)(lVar14 + 0x18));
      puVar19 = PTR_DAT_1801e5048;
      DAT_1801f1740 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
      DAT_1801efcd8 = pcVar6;
      if (pcVar6 == (code *)0x0) {
        lVar9 = PyErr_Occurred();
        if (lVar9 == 0) {
          pcVar6 = (code *)FUN_1801bb940(lVar14);
          puVar19 = PTR_DAT_1801e5048;
        }
        else {
          pcVar6 = (code *)0x0;
          puVar19 = PTR_DAT_1801e5048;
        }
      }
      else {
        *(longlong *)pcVar6 = *(longlong *)pcVar6 + 1;
      }
    }
    if (pcVar6 == (code *)0x0) {
      iVar5 = 0x564;
      iVar18 = 0xe4cf;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    if (*(code **)(*(longlong *)(pcVar6 + 8) + 0x90) == (code *)0x0) {
      pcVar16 = (code *)PyObject_GetAttr(pcVar6,*(undefined8 *)(puVar19 + 0x3898));
    }
    else {
      pcVar16 = (code *)(**(code **)(*(longlong *)(pcVar6 + 8) + 0x90))();
    }
    if (pcVar16 == (code *)0x0) {
      iVar5 = 0x564;
      iVar18 = 0xe4d1;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    *(longlong *)pcVar6 = *(longlong *)pcVar6 + -1;
    if (*(longlong *)pcVar6 == 0) {
      _Py_Dealloc(pcVar6);
    }
    if (*(code **)(*(longlong *)(pcVar16 + 8) + 0x90) == (code *)0x0) {
      pcVar6 = (code *)PyObject_GetAttr(pcVar16,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2660));
    }
    else {
      pcVar6 = (code *)(**(code **)(*(longlong *)(pcVar16 + 8) + 0x90))();
    }
    if (pcVar6 == (code *)0x0) {
      iVar5 = 0x564;
      iVar18 = 0xe4d4;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    *(longlong *)pcVar16 = *(longlong *)pcVar16 + -1;
    if (*(longlong *)pcVar16 == 0) {
      _Py_Dealloc();
    }
    plVar7 = (longlong *)0x0;
    lVar14 = 0;
    if ((*(code **)(pcVar6 + 8) == PyMethod_Type_exref) &&
       (plVar7 = *(longlong **)(pcVar6 + 0x18), plVar7 != (longlong *)0x0)) {
      pcVar16 = *(code **)(pcVar6 + 0x10);
      *plVar7 = *plVar7 + 1;
      *(longlong *)pcVar16 = *(longlong *)pcVar16 + 1;
      *(longlong *)pcVar6 = *(longlong *)pcVar6 + -1;
      if (*(longlong *)pcVar6 == 0) {
        _Py_Dealloc(pcVar6);
      }
      lVar14 = 1;
      pcVar6 = pcVar16;
    }
    local_a8[1] = plVar7;
    local_a8[2] = plVar8;
    plVar21 = (longlong *)
              FUN_1801bbf50((longlong)pcVar6,local_a8 + (2 - lVar14),(ulonglong)((int)lVar14 + 1));
    if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
      _Py_Dealloc(plVar7);
    }
    pcVar16 = (code *)0x0;
    if (plVar21 == (longlong *)0x0) {
      iVar5 = 0x564;
      iVar18 = 0xe4e9;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    *(longlong *)pcVar6 = *(longlong *)pcVar6 + -1;
    if (*(longlong *)pcVar6 == 0) {
      _Py_Dealloc(pcVar6);
    }
    pcVar6 = (code *)0x0;
    iVar5 = FUN_1801c28c0((undefined *)plVar21);
    if (iVar5 < 0) {
      iVar5 = 0x564;
      iVar18 = 0xe4ed;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    *plVar21 = *plVar21 + -1;
    if (*plVar21 == 0) {
      _Py_Dealloc(plVar21);
    }
    plVar21 = (longlong *)0x0;
    if (iVar5 != 0) {
      plVar21 = (longlong *)PyTuple_New(2);
      if (plVar21 == (longlong *)0x0) {
        iVar5 = 0x565;
        iVar18 = 0xe4f9;
        puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      }
      else {
        *plVar8 = *plVar8 + 1;
        puVar19 = PTR_DAT_1801e5048;
        plVar21[3] = (longlong)plVar8;
        plVar8 = *(longlong **)(puVar19 + 0x3c90);
        *plVar8 = *plVar8 + 1;
        plVar21[4] = *(longlong *)(puVar19 + 0x3c90);
        pcVar6 = (code *)PyDict_New();
        if (pcVar6 == (code *)0x0) {
          iVar5 = 0x565;
          iVar18 = 0xe501;
          puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
        }
        else {
          iVar5 = PyDict_SetItem(pcVar6,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2518),
                                 *(undefined8 *)(PTR_DAT_1801e5048 + 0x4a60));
          if (iVar5 < 0) {
            iVar5 = 0x565;
            iVar18 = 0xe503;
            puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
          }
          else {
            pcVar16 = (code *)FUN_1801bbe10(DAT_1801ef4b0,plVar21,pcVar6);
            if (pcVar16 == (code *)0x0) {
              iVar5 = 0x565;
              iVar18 = 0xe504;
              puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
            }
            else {
              *plVar21 = *plVar21 + -1;
              if (*plVar21 == 0) {
                _Py_Dealloc(plVar21);
              }
              plVar21 = (longlong *)0x0;
              *(longlong *)pcVar6 = *(longlong *)pcVar6 + -1;
              if (*(longlong *)pcVar6 == 0) {
                _Py_Dealloc(pcVar6);
              }
              pcVar6 = (code *)0x0;
              pcVar15 = (code *)FUN_1801bc150((longlong)pcVar16,
                                              *(undefined8 *)(PTR_DAT_1801e5048 + 0x2668));
              local_148 = pcVar15;
              if (pcVar15 == (code *)0x0) {
                iVar5 = 0x565;
                iVar18 = 0xe508;
                puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
              }
              else {
                plVar8 = FUN_1801bc150((longlong)pcVar16,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2588)
                                      );
                plVar21 = plVar8;
                if (plVar8 == (longlong *)0x0) {
                  iVar18 = 0xe50a;
                }
                else {
                  plVar7 = (longlong *)0x0;
                  uVar13 = 0;
                  if (((code *)plVar8[1] == PyMethod_Type_exref) &&
                     (plVar7 = (longlong *)plVar8[3], plVar7 != (longlong *)0x0)) {
                    plVar21 = (longlong *)plVar8[2];
                    *plVar7 = *plVar7 + 1;
                    *plVar21 = *plVar21 + 1;
                    *plVar8 = *plVar8 + -1;
                    if (*plVar8 == 0) {
                      _Py_Dealloc();
                    }
                    uVar13 = 1;
                  }
                  local_88 = 0;
                  local_a8[3] = plVar7;
                  plVar8 = (longlong *)
                           FUN_1801bbf50((longlong)plVar21,local_a8 + (4 - uVar13),uVar13);
                  if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
                    _Py_Dealloc(plVar7);
                  }
                  if (plVar8 != (longlong *)0x0) {
                    *plVar21 = *plVar21 + -1;
                    if (*plVar21 == 0) {
                      _Py_Dealloc(plVar21);
                    }
                    *(longlong *)pcVar16 = *(longlong *)pcVar16 + -1;
                    if (*(longlong *)pcVar16 == 0) {
                      _Py_Dealloc(pcVar16);
                    }
                    pcVar6 = (code *)0x0;
                    plVar21 = (longlong *)0x0;
                    local_100 = _PyThreadState_UncheckedGet();
                    puVar3 = *(undefined8 **)(local_100 + 0x90);
                    do {
                      puVar17 = puVar3;
                      pcVar15 = (code *)puVar17[1];
                      if ((pcVar15 != (code *)0x0) && (pcVar15 != _Py_NoneStruct_exref)) break;
                      puVar3 = (undefined8 *)puVar17[3];
                    } while ((undefined8 *)puVar17[3] != (undefined8 *)0x0);
                    local_110 = (longlong *)*puVar17;
                    local_e8 = (longlong *)puVar17[2];
                    if (local_110 != (longlong *)0x0) {
                      *local_110 = *local_110 + 1;
                    }
                    if (pcVar15 != (code *)0x0) {
                      *(longlong *)pcVar15 = *(longlong *)pcVar15 + 1;
                    }
                    if (local_e8 != (longlong *)0x0) {
                      *local_e8 = *local_e8 + 1;
                    }
                    local_138 = pcVar15;
                    local_f8 = plVar8;
                    if (*(code **)(plVar8[1] + 0x90) == (code *)0x0) {
                      pcVar10 = (code *)PyObject_GetAttr(plVar8,*(undefined8 *)
                                                                 (PTR_DAT_1801e5048 + 0x3cf0));
                    }
                    else {
                      pcVar10 = (code *)(**(code **)(plVar8[1] + 0x90))();
                    }
                    pcVar16 = pcVar6;
                    pcVar11 = pcVar10;
                    if (pcVar10 == (code *)0x0) {
                      iVar18 = 0x566;
                      iVar5 = 0xe538;
                      pcVar10 = pcVar6;
                    }
                    else {
                      pcVar15 = pcVar6;
                      pcVar20 = pcVar6;
                      if ((*(code **)(pcVar10 + 8) == PyMethod_Type_exref) &&
                         (pcVar15 = *(code **)(pcVar10 + 0x18), pcVar15 != (code *)0x0)) {
                        pcVar11 = *(code **)(pcVar10 + 0x10);
                        *(longlong *)pcVar15 = *(longlong *)pcVar15 + 1;
                        *(longlong *)pcVar11 = *(longlong *)pcVar11 + 1;
                        *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1;
                        if (*(longlong *)pcVar10 == 0) {
                          _Py_Dealloc();
                        }
                        pcVar20 = (code *)0x1;
                      }
                      local_78[0] = (code *)0x0;
                      local_80 = pcVar15;
                      pcVar10 = (code *)FUN_1801bbf50((longlong)pcVar11,
                                                      local_78 + -(longlong)pcVar20,
                                                      (ulonglong)pcVar20);
                      if ((pcVar15 != (code *)0x0) &&
                         (*(longlong *)pcVar15 = *(longlong *)pcVar15 + -1,
                         *(longlong *)pcVar15 == 0)) {
                        _Py_Dealloc();
                      }
                      local_130 = (code *)0x0;
                      if (pcVar10 == (code *)0x0) {
                        iVar18 = 0x566;
                        iVar5 = 0xe54c;
                        pcVar15 = local_138;
                      }
                      else {
                        *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
                        if (*(longlong *)pcVar11 == 0) {
                          _Py_Dealloc(pcVar11);
                        }
                        if (*(code **)(*(longlong *)(pcVar10 + 8) + 0x90) == (code *)0x0) {
                          pcVar15 = (code *)PyObject_GetAttr(pcVar10,*(undefined8 *)
                                                                      (PTR_DAT_1801e5048 + 0x44a8));
                        }
                        else {
                          pcVar15 = (code *)(**(code **)(*(longlong *)(pcVar10 + 8) + 0x90))();
                        }
                        pcVar11 = pcVar15;
                        if (pcVar15 == (code *)0x0) {
                          iVar18 = 0x566;
                          iVar5 = 0xe550;
                          pcVar15 = local_138;
                        }
                        else {
                          *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1;
                          if (*(longlong *)pcVar10 == 0) {
                            _Py_Dealloc(pcVar10);
                          }
                          pcVar20 = pcVar6;
                          pcVar10 = pcVar6;
                          if ((*(code **)(pcVar15 + 8) == PyMethod_Type_exref) &&
                             (pcVar10 = *(code **)(pcVar15 + 0x18), pcVar10 != (code *)0x0)) {
                            pcVar11 = *(code **)(pcVar15 + 0x10);
                            *(longlong *)pcVar10 = *(longlong *)pcVar10 + 1;
                            *(longlong *)pcVar11 = *(longlong *)pcVar11 + 1;
                            *(longlong *)pcVar15 = *(longlong *)pcVar15 + -1;
                            if (*(longlong *)pcVar15 == 0) {
                              _Py_Dealloc(pcVar15);
                            }
                            pcVar20 = (code *)0x1;
                          }
                          local_78[2] = (code *)0x0;
                          local_78[1] = pcVar10;
                          pcVar20 = (code *)FUN_1801bbf50((longlong)pcVar11,
                                                          local_78 + (2 - (longlong)pcVar20),
                                                          (ulonglong)pcVar20);
                          local_140 = pcVar20;
                          if ((pcVar10 != (code *)0x0) &&
                             (*(longlong *)pcVar10 = *(longlong *)pcVar10 + -1,
                             *(longlong *)pcVar10 == 0)) {
                            _Py_Dealloc();
                          }
                          pcVar10 = (code *)0x0;
                          if (pcVar20 == (code *)0x0) {
                            iVar18 = 0x566;
                            iVar5 = 0xe565;
                            pcVar16 = (code *)0x0;
                            pcVar15 = local_138;
                          }
                          else {
                            *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
                            if (*(longlong *)pcVar11 == 0) {
                              _Py_Dealloc(pcVar11);
                            }
                            if (*(code **)(*(longlong *)(pcVar20 + 8) + 0x90) == (code *)0x0) {
                              pcVar15 = (code *)PyObject_GetAttr(pcVar20,*(undefined8 *)
                                                                          (PTR_DAT_1801e5048 +
                                                                          0x2ff8));
                            }
                            else {
                              pcVar15 = (code *)(**(code **)(*(longlong *)(pcVar20 + 8) + 0x90))();
                            }
                            pcVar11 = pcVar15;
                            if (pcVar15 == (code *)0x0) {
                              iVar18 = 0x567;
                              iVar5 = 0xe573;
                            }
                            else {
                              pcVar10 = pcVar6;
                              if ((*(code **)(pcVar15 + 8) == PyMethod_Type_exref) &&
                                 (pcVar10 = *(code **)(pcVar15 + 0x18), pcVar10 != (code *)0x0)) {
                                pcVar11 = *(code **)(pcVar15 + 0x10);
                                *(longlong *)pcVar10 = *(longlong *)pcVar10 + 1;
                                *(longlong *)pcVar11 = *(longlong *)pcVar11 + 1;
                                *(longlong *)pcVar15 = *(longlong *)pcVar15 + -1;
                                if (*(longlong *)pcVar15 == 0) {
                                  _Py_Dealloc();
                                }
                                pcVar16 = (code *)0x1;
                              }
                              local_b8 = (code *)0x0;
                              local_c0 = pcVar10;
                              pcVar16 = (code *)FUN_1801bbf50((longlong)pcVar11,
                                                              &local_b8 + -(longlong)pcVar16,
                                                              (ulonglong)pcVar16);
                              if ((pcVar10 != (code *)0x0) &&
                                 (*(longlong *)pcVar10 = *(longlong *)pcVar10 + -1,
                                 *(longlong *)pcVar10 == 0)) {
                                _Py_Dealloc();
                              }
                              if (pcVar16 == (code *)0x0) {
                                iVar18 = 0x567;
                                iVar5 = 0xe587;
                              }
                              else {
                                *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
                                if (*(longlong *)pcVar11 == 0) {
                                  _Py_Dealloc(pcVar11);
                                }
                                pcVar11 = (code *)0x0;
                                iVar5 = FUN_1801c28c0(pcVar16);
                                if (iVar5 < 0) {
                                  iVar18 = 0x567;
                                  iVar5 = 0xe58b;
                                  pcVar11 = pcVar6;
                                }
                                else {
                                  *(longlong *)pcVar16 = *(longlong *)pcVar16 + -1;
                                  if (*(longlong *)pcVar16 == 0) {
                                    _Py_Dealloc();
                                  }
                                  pcVar16 = (code *)PyDict_New();
                                  if (iVar5 == 0) {
                                    if (pcVar16 == (code *)0x0) {
                                      iVar5 = 0xe5b4;
                                    }
                                    else {
                                      iVar5 = PyDict_SetItem(pcVar16,*(undefined8 *)
                                                                      (PTR_DAT_1801e5048 + 0x43f8),
                                                             *(undefined8 *)
                                                              (PTR_DAT_1801e5048 + 0x45b8));
                                      if (iVar5 < 0) {
                                        iVar5 = 0xe5b6;
                                      }
                                      else {
                                        iVar5 = PyDict_SetItem(pcVar16,*(undefined8 *)
                                                                        (PTR_DAT_1801e5048 + 0x1998)
                                                               ,_Py_NoneStruct_exref);
                                        if (-1 < iVar5) goto LAB_18005a1b9;
                                        iVar5 = 0xe5b7;
                                      }
                                    }
                                    iVar18 = 0x56a;
                                  }
                                  else if (pcVar16 == (code *)0x0) {
                                    iVar18 = 0x568;
                                    iVar5 = 0xe597;
                                  }
                                  else {
                                    iVar5 = PyDict_SetItem(pcVar16,*(undefined8 *)
                                                                    (PTR_DAT_1801e5048 + 0x43f8),
                                                           *(undefined8 *)
                                                            (PTR_DAT_1801e5048 + 0x45b8));
                                    if (iVar5 < 0) {
                                      iVar18 = 0x568;
                                      iVar5 = 0xe599;
                                    }
                                    else {
                                      if (*(code **)(pcVar20 + 8) == PyLong_Type_exref) {
                                        *(longlong *)pcVar20 = *(longlong *)pcVar20 + 1;
                                        pcVar11 = pcVar20;
                                      }
                                      else {
                                        pcVar11 = (code *)PyNumber_Long();
                                        if (pcVar11 == (code *)0x0) {
                                          iVar18 = 0x568;
                                          iVar5 = 0xe59a;
                                          goto LAB_18005a28d;
                                        }
                                      }
                                      iVar5 = PyDict_SetItem(pcVar16,*(undefined8 *)
                                                                      (PTR_DAT_1801e5048 + 0x1998),
                                                             pcVar11);
                                      if (-1 < iVar5) {
                                        *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
                                        if (*(longlong *)pcVar11 == 0) {
                                          _Py_Dealloc(pcVar11);
                                        }
LAB_18005a1b9:
                                        pcVar6 = (code *)0x0;
                                        FUN_1801bc0e0(local_100,local_110,local_138,local_e8);
                                        pcVar15 = local_148;
                                        plVar8 = (longlong *)
                                                 FUN_1801bbe10((longlong)local_148,
                                                               *(undefined8 *)
                                                                (PTR_DAT_1801e5048 + 0x4fd0),0);
                                        *(longlong *)pcVar15 = *(longlong *)pcVar15 + -1;
                                        if (*(longlong *)pcVar15 == 0) {
                                          _Py_Dealloc(pcVar15);
                                        }
                                        if (plVar8 != (longlong *)0x0) {
                                          *plVar8 = *plVar8 + -1;
                                          if (*plVar8 == 0) {
                                            _Py_Dealloc(plVar8);
                                          }
                                          goto LAB_18005aa5a;
                                        }
                                        iVar5 = 0x565;
                                        local_118 = local_140;
                                        iVar18 = 0xe60e;
                                        pcVar16 = (code *)0x0;
                                        puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
                                        goto LAB_18005a56f;
                                      }
                                      iVar18 = 0x568;
                                      iVar5 = 0xe59c;
                                    }
                                  }
                                }
                              }
                            }
LAB_18005a28d:
                            pcVar10 = (code *)0x0;
                            pcVar15 = local_138;
                            local_118 = pcVar20;
                          }
                        }
                      }
                    }
                    puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
                    if ((pcVar16 != (code *)0x0) &&
                       (*(longlong *)pcVar16 = *(longlong *)pcVar16 + -1, *(longlong *)pcVar16 == 0)
                       ) {
                      _Py_Dealloc();
                    }
                    local_108 = (longlong *)0x0;
                    if ((pcVar11 != (code *)0x0) &&
                       (*(longlong *)pcVar11 = *(longlong *)pcVar11 + -1, *(longlong *)pcVar11 == 0)
                       ) {
                      _Py_Dealloc();
                    }
                    local_140 = (code *)0x0;
                    if ((pcVar10 != (code *)0x0) &&
                       (*(longlong *)pcVar10 = *(longlong *)pcVar10 + -1, *(longlong *)pcVar10 == 0)
                       ) {
                      _Py_Dealloc();
                    }
                    local_120 = (code *)0x0;
                    local_128 = (longlong *)0x0;
                    local_130 = (code *)0x0;
                    FUN_1801c1020("main.Api.get_admin_id",iVar5,iVar18,puVar19);
                    uVar12 = FUN_1801bc330(local_100,&local_108,&local_140,&local_120);
                    plVar21 = local_108;
                    pcVar16 = local_120;
                    pcVar6 = local_140;
                    if ((int)uVar12 < 0) {
                      iVar18 = 0xe5ce;
                    }
                    else {
                      pcVar11 = (code *)PyTuple_Pack(3,local_108,local_140,local_120);
                      pcVar10 = local_148;
                      if (pcVar11 == (code *)0x0) {
                        iVar18 = 0xe5d2;
                        local_130 = (code *)0x0;
                      }
                      else {
                        local_130 = pcVar11;
                        plVar8 = (longlong *)FUN_1801bbe10((longlong)local_148,pcVar11,0);
                        *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1;
                        if (*(longlong *)pcVar10 == 0) {
                          _Py_Dealloc(pcVar10);
                        }
                        *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
                        if (*(longlong *)pcVar11 == 0) {
                          _Py_Dealloc(pcVar11);
                        }
                        local_130 = (code *)0x0;
                        if (plVar8 == (longlong *)0x0) {
                          iVar18 = 0xe5d7;
                        }
                        else {
                          iVar5 = FUN_1801c28c0((undefined *)plVar8);
                          *plVar8 = *plVar8 + -1;
                          if (*plVar8 == 0) {
                            _Py_Dealloc(plVar8);
                          }
                          if (iVar5 < 0) {
                            iVar18 = 0xe5db;
                          }
                          else {
                            if (iVar5 != 0) {
                              if ((plVar21 != (longlong *)0x0) &&
                                 (*plVar21 = *plVar21 + -1, *plVar21 == 0)) {
                                _Py_Dealloc(plVar21);
                              }
                              if ((pcVar6 != (code *)0x0) &&
                                 (*(longlong *)pcVar6 = *(longlong *)pcVar6 + -1,
                                 *(longlong *)pcVar6 == 0)) {
                                _Py_Dealloc(pcVar6);
                              }
                              if ((pcVar16 != (code *)0x0) &&
                                 (*(longlong *)pcVar16 = *(longlong *)pcVar16 + -1,
                                 *(longlong *)pcVar16 == 0)) {
                                _Py_Dealloc(pcVar16);
                              }
                              FUN_1801bc0e0(local_100,local_110,pcVar15,local_e8);
                              if ((local_d8 != (longlong *)0x0) &&
                                 (*local_d8 = *local_d8 + -1, *local_d8 == 0)) {
                                _Py_Dealloc();
                              }
                              if ((local_f0 != (code *)0x0) &&
                                 (*(longlong *)local_f0 = *(longlong *)local_f0 + -1,
                                 *(longlong *)local_f0 == 0)) {
                                _Py_Dealloc(local_f0);
                              }
                              if ((local_e0 != (longlong *)0x0) &&
                                 (*local_e0 = *local_e0 + -1, *local_e0 == 0)) {
                                _Py_Dealloc();
                              }
                              pcVar16 = _Py_NoneStruct_exref;
                              *(longlong *)_Py_NoneStruct_exref =
                                   *(longlong *)_Py_NoneStruct_exref + 1;
                              goto LAB_18005aa70;
                            }
                            lVar14 = PyThreadState_Get();
                            FUN_1801bb760(lVar14,plVar21,pcVar6,pcVar16);
                            plVar21 = (longlong *)0x0;
                            pcVar6 = (code *)0x0;
                            pcVar16 = (code *)0x0;
                            iVar18 = 0xe5e3;
                          }
                        }
                      }
                    }
                    puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
                    iVar5 = 0x565;
                    FUN_1801bc0e0(local_100,local_110,local_138,local_e8);
                    goto LAB_18005a56f;
                  }
                  iVar18 = 0xe51e;
                  pcVar15 = local_148;
                }
                puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
                pcVar6 = (code *)0x0;
                iVar5 = 0x565;
                *(longlong *)pcVar15 = *(longlong *)pcVar15 + -1;
                if (*(longlong *)pcVar15 == 0) {
                  _Py_Dealloc(pcVar15);
                }
                local_130 = (code *)0x0;
              }
            }
          }
        }
      }
      goto LAB_18005a56f;
    }
    pcVar16 = (code *)PyDict_New();
    if (pcVar16 == (code *)0x0) {
      iVar18 = 0xe632;
LAB_18005a563:
      iVar5 = 0x56c;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_18005a56f;
    }
    iVar5 = PyDict_SetItem(pcVar16,*(undefined8 *)(PTR_DAT_1801e5048 + 0x43f8),
                           *(undefined8 *)(PTR_DAT_1801e5048 + 0x45b8));
    if (iVar5 < 0) {
      iVar18 = 0xe634;
      goto LAB_18005a563;
    }
    iVar5 = PyDict_SetItem(pcVar16,*(undefined8 *)(PTR_DAT_1801e5048 + 0x1998),_Py_NoneStruct_exref)
    ;
    pcVar20 = local_118;
    if (iVar5 < 0) {
      iVar18 = 0xe635;
      goto LAB_18005a563;
    }
LAB_18005aa5a:
    local_118 = pcVar20;
    FUN_1801bc0e0(local_d0,local_d8,local_f0,local_e0);
    goto LAB_18005aa70;
  }
  iVar5 = 0x563;
  iVar18 = 0xe485;
  plVar21 = plVar8;
  pcVar16 = (code *)0x0;
  puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
LAB_18005a56f:
  if ((plVar21 != (longlong *)0x0) && (*plVar21 = *plVar21 + -1, *plVar21 == 0)) {
    _Py_Dealloc(plVar21);
  }
  local_108 = (longlong *)0x0;
  if ((pcVar6 != (code *)0x0) &&
     (*(longlong *)pcVar6 = *(longlong *)pcVar6 + -1, *(longlong *)pcVar6 == 0)) {
    _Py_Dealloc(pcVar6);
  }
  pcVar6 = (code *)0x0;
  local_140 = (code *)0x0;
  if ((pcVar16 != (code *)0x0) &&
     (*(longlong *)pcVar16 = *(longlong *)pcVar16 + -1, *(longlong *)pcVar16 == 0)) {
    _Py_Dealloc(pcVar16);
  }
  local_120 = (code *)0x0;
  if ((local_130 != (code *)0x0) &&
     (*(longlong *)local_130 = *(longlong *)local_130 + -1, *(longlong *)local_130 == 0)) {
    _Py_Dealloc();
  }
  if ((local_128 != (longlong *)0x0) && (*local_128 = *local_128 + -1, *local_128 == 0)) {
    _Py_Dealloc();
  }
  lVar14 = local_d0;
  puVar1 = *(undefined **)PyExc_Exception_exref;
  puVar2 = *(undefined **)(local_d0 + 0x58);
  if (puVar2 == puVar1) {
LAB_18005a632:
    FUN_1801c1020("main.Api.get_admin_id",iVar18,iVar5,puVar19);
    uVar12 = FUN_1801bc330(lVar14,&local_120,&local_140,&local_108);
    pcVar6 = local_140;
    if ((int)uVar12 < 0) {
      iVar5 = 0x56d;
      iVar18 = 0xe65a;
      pcVar16 = local_120;
      plVar21 = local_108;
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
    }
    else {
      lVar14 = *(longlong *)local_140;
      *(longlong *)local_140 = lVar14 + 1;
      if (*(code **)(local_140 + 8) == PyUnicode_Type_exref) {
        *(longlong *)local_140 = lVar14 + 2;
        pcVar16 = local_140;
      }
      else {
        pcVar16 = (code *)PyObject_Str(local_140);
      }
      puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
      if (pcVar16 == (code *)0x0) {
        local_140 = (code *)0x0;
        iVar5 = 0x56e;
        local_138 = (code *)0x0;
        iVar18 = 0xe669;
        local_130 = (code *)0x0;
        lVar14 = _PyThreadState_UncheckedGet();
      }
      else {
        pcVar15 = (code *)PyUnicode_Concat(*(undefined8 *)(PTR_DAT_1801e5048 + 0xa98),pcVar16);
        if (pcVar15 == (code *)0x0) {
          iVar5 = 0x56e;
          iVar18 = 0xe66b;
LAB_18005a84d:
          puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
          local_130 = (code *)0x0;
          local_140 = local_130;
          local_138 = local_130;
          lVar14 = _PyThreadState_UncheckedGet();
          *(longlong *)pcVar16 = *(longlong *)pcVar16 + -1;
          if (*(longlong *)pcVar16 == 0) {
            _Py_Dealloc(pcVar16);
          }
          if (pcVar15 == (code *)0x0) goto LAB_18005a880;
        }
        else {
          *(longlong *)pcVar16 = *(longlong *)pcVar16 + -1;
          if (*(longlong *)pcVar16 == 0) {
            _Py_Dealloc(pcVar16);
          }
          local_c0 = (code *)0x0;
          local_b8 = pcVar15;
          plVar21 = (longlong *)FUN_1801bbf50(DAT_1801f1718,&local_b8,0x8000000000000001);
          puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
          if (plVar21 != (longlong *)0x0) {
            *(longlong *)pcVar15 = *(longlong *)pcVar15 + -1;
            if (*(longlong *)pcVar15 == 0) {
              _Py_Dealloc(pcVar15);
            }
            *plVar21 = *plVar21 + -1;
            if (*plVar21 == 0) {
              _Py_Dealloc(plVar21);
            }
            pcVar16 = (code *)PyDict_New();
            puVar19 = PTR_s_packed__build_temp__main_py_1801cc288;
            if (pcVar16 == (code *)0x0) {
              iVar5 = 0x56f;
              iVar18 = 0xe67b;
              local_140 = (code *)0x0;
              local_138 = (code *)0x0;
              local_130 = (code *)0x0;
              lVar14 = _PyThreadState_UncheckedGet();
              goto LAB_18005a880;
            }
            if (*(code **)(pcVar6 + 8) == PyUnicode_Type_exref) {
              *(longlong *)pcVar6 = *(longlong *)pcVar6 + 1;
              pcVar15 = pcVar6;
            }
            else {
              pcVar15 = (code *)PyObject_Str(pcVar6);
            }
            if (pcVar15 == (code *)0x0) {
              iVar18 = 0xe67d;
            }
            else {
              iVar5 = PyDict_SetItem(pcVar16,*(undefined8 *)(PTR_DAT_1801e5048 + 0x25f0),pcVar15);
              if (-1 < iVar5) {
                *(longlong *)pcVar15 = *(longlong *)pcVar15 + -1;
                if (*(longlong *)pcVar15 == 0) {
                  _Py_Dealloc(pcVar15);
                }
                *local_108 = *local_108 + -1;
                if (*local_108 == 0) {
                  _Py_Dealloc();
                }
                *(longlong *)pcVar6 = *(longlong *)pcVar6 + -1;
                if (*(longlong *)pcVar6 == 0) {
                  _Py_Dealloc(pcVar6);
                }
                *(longlong *)local_120 = *(longlong *)local_120 + -1;
                if (*(longlong *)local_120 == 0) {
                  _Py_Dealloc();
                }
                *(longlong *)pcVar6 = *(longlong *)pcVar6 + -1;
                pcVar20 = local_118;
                if (*(longlong *)pcVar6 == 0) {
                  _Py_Dealloc(pcVar6);
                  pcVar20 = local_118;
                }
                goto LAB_18005aa5a;
              }
              iVar18 = 0xe67f;
            }
            iVar5 = 0x56f;
            goto LAB_18005a84d;
          }
          iVar5 = 0x56e;
          iVar18 = 0xe66e;
          local_140 = (code *)0x0;
          local_138 = (code *)0x0;
          local_130 = (code *)0x0;
          lVar14 = _PyThreadState_UncheckedGet();
        }
        *(longlong *)pcVar15 = *(longlong *)pcVar15 + -1;
        if (*(longlong *)pcVar15 == 0) {
          _Py_Dealloc(pcVar15);
        }
      }
LAB_18005a880:
      plVar21 = *(longlong **)(lVar14 + 0x90);
      local_100 = *plVar21;
      local_e8 = (longlong *)plVar21[1];
      local_110 = (longlong *)plVar21[2];
      *plVar21 = 0;
      plVar21[1] = 0;
      plVar21[2] = 0;
      uVar12 = FUN_1801bc330(lVar14,&local_140,&local_138,&local_130);
      if ((int)uVar12 < 0) {
        local_148 = *(code **)(lVar14 + 0x68);
        pcVar16 = *(code **)(lVar14 + 0x58);
        pcVar15 = *(code **)(lVar14 + 0x60);
        *(undefined8 *)(lVar14 + 0x58) = 0;
        *(undefined8 *)(lVar14 + 0x60) = 0;
        *(undefined8 *)(lVar14 + 0x68) = 0;
      }
      else {
        local_148 = local_130;
        pcVar16 = local_140;
        pcVar15 = local_138;
      }
      *(longlong *)pcVar6 = *(longlong *)pcVar6 + -1;
      if (*(longlong *)pcVar6 == 0) {
        _Py_Dealloc(pcVar6);
      }
      FUN_1801bc0e0(lVar14,local_100,local_e8,local_110);
      FUN_1801bb760(lVar14,pcVar16,pcVar15,local_148);
      pcVar16 = local_120;
      plVar21 = local_108;
      lVar14 = local_d0;
    }
  }
  else {
    pcVar16 = (code *)0x0;
    plVar21 = (longlong *)0x0;
    if (puVar2 != (undefined *)0x0) {
      if ((*(uint *)(*(longlong *)(puVar1 + 8) + 0xa8) & 0x4000000) == 0) {
        uVar13 = FUN_1801bdde0(puVar2,puVar1);
        iVar4 = (int)uVar13;
      }
      else {
        uVar12 = FUN_1801bb510(puVar2,(longlong)puVar1);
        iVar4 = (int)uVar12;
      }
      if (iVar4 != 0) goto LAB_18005a632;
    }
  }
  puVar3 = *(undefined8 **)(lVar14 + 0x90);
  plVar8 = (longlong *)*puVar3;
  local_148 = (code *)puVar3[2];
  plVar7 = (longlong *)puVar3[1];
  *puVar3 = local_d8;
  puVar3[1] = local_f0;
  puVar3[2] = local_e0;
  if ((plVar8 != (longlong *)0x0) && (*plVar8 = *plVar8 + -1, *plVar8 == 0)) {
    _Py_Dealloc(plVar8);
  }
  if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
    _Py_Dealloc(plVar7);
  }
  if ((local_148 != (code *)0x0) &&
     (*(longlong *)local_148 = *(longlong *)local_148 + -1, *(longlong *)local_148 == 0)) {
    _Py_Dealloc();
  }
  if ((plVar21 != (longlong *)0x0) && (*plVar21 = *plVar21 + -1, *plVar21 == 0)) {
    _Py_Dealloc(plVar21);
  }
  if ((pcVar6 != (code *)0x0) &&
     (*(longlong *)pcVar6 = *(longlong *)pcVar6 + -1, *(longlong *)pcVar6 == 0)) {
    _Py_Dealloc(pcVar6);
  }
  if ((pcVar16 != (code *)0x0) &&
     (*(longlong *)pcVar16 = *(longlong *)pcVar16 + -1, *(longlong *)pcVar16 == 0)) {
    _Py_Dealloc(pcVar16);
  }
  FUN_1801c1020("main.Api.get_admin_id",iVar18,iVar5,puVar19);
  pcVar16 = (code *)0x0;
LAB_18005aa70:
  if ((local_c8 != (longlong *)0x0) && (*local_c8 = *local_c8 + -1, *local_c8 == 0)) {
    _Py_Dealloc();
  }
  if ((local_f8 != (longlong *)0x0) && (*local_f8 = *local_f8 + -1, *local_f8 == 0)) {
    _Py_Dealloc();
  }
  if ((local_118 != (code *)0x0) &&
     (*(longlong *)local_118 = *(longlong *)local_118 + -1, *(longlong *)local_118 == 0)) {
    _Py_Dealloc(local_118);
  }
  return pcVar16;
}

