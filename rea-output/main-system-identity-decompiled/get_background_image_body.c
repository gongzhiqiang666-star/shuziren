
/* WARNING: Function: __security_check_cookie replaced with injection: security_check_cookie */

longlong * FUN_180050480(void)

{
  undefined *puVar1;
  undefined *puVar2;
  code *pcVar3;
  undefined8 *puVar4;
  int iVar5;
  int iVar6;
  longlong *plVar7;
  longlong *plVar8;
  longlong *plVar9;
  longlong lVar11;
  ulonglong uVar12;
  longlong *plVar13;
  longlong lVar14;
  undefined8 *puVar15;
  longlong lVar16;
  longlong *plVar17;
  undefined *puVar18;
  longlong *plVar19;
  longlong *plVar20;
  int iVar21;
  undefined1 auStack_158 [32];
  undefined8 local_138;
  longlong *local_130;
  longlong *local_128;
  longlong local_120;
  code *local_118;
  longlong *local_110;
  longlong *local_108;
  code *local_100;
  longlong *local_f8;
  longlong *local_f0;
  code *local_e8;
  longlong *local_e0;
  longlong *local_d8;
  longlong *local_d0;
  longlong local_c8;
  longlong *local_c0;
  longlong *local_b8;
  undefined8 local_b0;
  longlong *local_a8;
  longlong *local_a0 [4];
  longlong *local_80;
  longlong *local_78;
  undefined8 local_70;
  longlong *local_68;
  longlong *local_60;
  longlong *local_58;
  longlong *local_50;
  undefined8 local_48;
  undefined8 local_40;
  undefined8 local_38;
  ulonglong local_30;
  undefined8 uVar10;
  
  local_30 = DAT_1801e4000 ^ (ulonglong)auStack_158;
  plVar7 = (longlong *)0x0;
  local_e0 = (longlong *)0x0;
  local_c0 = (longlong *)0x0;
  plVar19 = (longlong *)0x0;
  local_f8 = (longlong *)0x0;
  plVar17 = (longlong *)0x0;
  local_c8 = _PyThreadState_UncheckedGet();
  puVar4 = *(undefined8 **)(local_c8 + 0x90);
  do {
    puVar15 = puVar4;
    local_e8 = (code *)puVar15[1];
    if ((local_e8 != (code *)0x0) && (local_e8 != _Py_NoneStruct_exref)) break;
    puVar4 = (undefined8 *)puVar15[3];
  } while ((undefined8 *)puVar15[3] != (undefined8 *)0x0);
  local_d0 = (longlong *)*puVar15;
  local_d8 = (longlong *)puVar15[2];
  if (local_d0 != (longlong *)0x0) {
    *local_d0 = *local_d0 + 1;
  }
  if (local_e8 != (code *)0x0) {
    *(longlong *)local_e8 = *(longlong *)local_e8 + 1;
  }
  if (local_d8 != (longlong *)0x0) {
    *local_d8 = *local_d8 + 1;
  }
  puVar18 = PTR_DAT_1801e5048;
  if (DAT_1801ef4c8 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
    if (DAT_1801f05d0 == (longlong *)0x0) {
      uVar10 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x37e0);
      plVar13 = (longlong *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar10);
      puVar18 = PTR_DAT_1801e5048;
      if ((plVar13 == (longlong *)0x0) &&
         (lVar14 = PyErr_Occurred(), puVar18 = PTR_DAT_1801e5048, lVar14 == 0)) {
        PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar10);
        puVar18 = PTR_DAT_1801e5048;
      }
    }
    else {
      *DAT_1801f05d0 = *DAT_1801f05d0 + 1;
      plVar13 = DAT_1801f05d0;
    }
  }
  else {
    lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x37e0);
    plVar13 = (longlong *)
              _PyDict_GetItem_KnownHash
                        (*(longlong *)PTR_DAT_1801e5048,lVar14,*(undefined8 *)(lVar14 + 0x18));
    puVar18 = PTR_DAT_1801e5048;
    DAT_1801ef4c8 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
    DAT_1801f05d0 = plVar13;
    if (plVar13 == (longlong *)0x0) {
      lVar16 = PyErr_Occurred();
      if (lVar16 == 0) {
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
    iVar6 = 0x4df;
    iVar21 = 0xd418;
    plVar17 = plVar7;
    plVar19 = plVar7;
    puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
LAB_180050d53:
    if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
      _Py_Dealloc(plVar13);
    }
    local_110 = (longlong *)0x0;
    if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
      _Py_Dealloc(plVar7);
    }
    plVar7 = (longlong *)0x0;
    local_130 = (longlong *)0x0;
    if ((plVar19 != (longlong *)0x0) && (*plVar19 = *plVar19 + -1, *plVar19 == 0)) {
      _Py_Dealloc(plVar19);
    }
    local_128 = (longlong *)0x0;
    if ((plVar17 != (longlong *)0x0) && (*plVar17 = *plVar17 + -1, *plVar17 == 0)) {
      _Py_Dealloc(plVar17);
    }
    lVar14 = local_c8;
    puVar1 = *(undefined **)PyExc_Exception_exref;
    puVar2 = *(undefined **)(local_c8 + 0x58);
    if (puVar2 == puVar1) {
LAB_18005195f:
      FUN_1801c1020("main.Api.get_background_image",iVar21,iVar6,puVar18);
      uVar10 = FUN_1801bc330(lVar14,&local_110,&local_130,&local_128);
      plVar7 = local_130;
      if ((int)uVar10 < 0) {
        iVar6 = 0x4ed;
        iVar21 = 0xd5c4;
        plVar19 = local_128;
        puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
        goto LAB_180051c45;
      }
      lVar16 = *local_130;
      *local_130 = lVar16 + 1;
      if ((code *)local_130[1] == PyUnicode_Type_exref) {
        *local_130 = lVar16 + 2;
        plVar13 = local_130;
      }
      else {
        plVar13 = (longlong *)PyObject_Str(local_130);
      }
      if (plVar13 == (longlong *)0x0) {
        iVar6 = 0x4ee;
        iVar21 = 0xd5d3;
LAB_180051abf:
        puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
        local_130 = (longlong *)0x0;
        local_120 = 0;
        local_118 = (code *)0x0;
        lVar14 = _PyThreadState_UncheckedGet();
LAB_180051b87:
        puVar4 = *(undefined8 **)(lVar14 + 0x90);
        local_138 = *puVar4;
        local_108 = (longlong *)puVar4[1];
        local_f0 = (longlong *)puVar4[2];
        *puVar4 = 0;
        puVar4[1] = 0;
        puVar4[2] = 0;
        uVar10 = FUN_1801bc330(lVar14,&local_130,&local_120,&local_118);
        if ((int)uVar10 < 0) {
          local_100 = *(code **)(lVar14 + 0x68);
          plVar19 = *(longlong **)(lVar14 + 0x58);
          lVar16 = *(longlong *)(lVar14 + 0x60);
          *(undefined8 *)(lVar14 + 0x58) = 0;
          *(undefined8 *)(lVar14 + 0x60) = 0;
          *(undefined8 *)(lVar14 + 0x68) = 0;
        }
        else {
          local_100 = local_118;
          plVar19 = local_130;
          lVar16 = local_120;
        }
        *plVar7 = *plVar7 + -1;
        if (*plVar7 == 0) {
          _Py_Dealloc(plVar7);
        }
        FUN_1801bc0e0(lVar14,local_138,local_108,local_f0);
        FUN_1801bb760(lVar14,plVar19,lVar16,local_100);
        plVar19 = local_128;
        lVar14 = local_c8;
        goto LAB_180051c45;
      }
      plVar19 = (longlong *)PyUnicode_Concat(*(undefined8 *)(PTR_DAT_1801e5048 + 0x1010),plVar13);
      if (plVar19 == (longlong *)0x0) {
        iVar6 = 0x4ee;
        iVar21 = 0xd5d5;
LAB_180051b40:
        puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
        local_130 = (longlong *)0x0;
        local_120 = 0;
        local_118 = (code *)0x0;
        lVar14 = _PyThreadState_UncheckedGet();
        *plVar13 = *plVar13 + -1;
        if (*plVar13 == 0) {
          _Py_Dealloc(plVar13);
        }
        if (plVar19 != (longlong *)0x0) {
LAB_180051b77:
          *plVar19 = *plVar19 + -1;
          if (*plVar19 == 0) {
            _Py_Dealloc(plVar19);
          }
        }
        goto LAB_180051b87;
      }
      *plVar13 = *plVar13 + -1;
      if (*plVar13 == 0) {
        _Py_Dealloc(plVar13);
      }
      local_a8 = (longlong *)0x0;
      local_a0[0] = plVar19;
      plVar17 = (longlong *)FUN_1801bbf50(DAT_1801f1718,local_a0,0x8000000000000001);
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      if (plVar17 == (longlong *)0x0) {
        iVar6 = 0x4ee;
        iVar21 = 0xd5d8;
        local_130 = (longlong *)0x0;
        local_120 = 0;
        local_118 = (code *)0x0;
        lVar14 = _PyThreadState_UncheckedGet();
        goto LAB_180051b77;
      }
      *plVar19 = *plVar19 + -1;
      if (*plVar19 == 0) {
        _Py_Dealloc(plVar19);
      }
      *plVar17 = *plVar17 + -1;
      if (*plVar17 == 0) {
        _Py_Dealloc(plVar17);
      }
      plVar13 = (longlong *)PyDict_New();
      if (plVar13 == (longlong *)0x0) {
        iVar6 = 0x4ef;
        iVar21 = 0xd5e5;
        goto LAB_180051abf;
      }
      if ((code *)plVar7[1] == PyUnicode_Type_exref) {
        *plVar7 = *plVar7 + 1;
        plVar19 = plVar7;
      }
      else {
        plVar19 = (longlong *)PyObject_Str(plVar7);
      }
      if (plVar19 == (longlong *)0x0) {
        iVar21 = 0xd5e7;
LAB_180051b3b:
        iVar6 = 0x4ef;
        goto LAB_180051b40;
      }
      iVar6 = PyDict_SetItem(plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x25f0),plVar19);
      if (iVar6 < 0) {
        iVar21 = 0xd5e9;
        goto LAB_180051b3b;
      }
      *plVar19 = *plVar19 + -1;
      if (*plVar19 == 0) {
        _Py_Dealloc(plVar19);
      }
      *local_110 = *local_110 + -1;
      if (*local_110 == 0) {
        _Py_Dealloc();
      }
      *plVar7 = *plVar7 + -1;
      if (*plVar7 == 0) {
        _Py_Dealloc(plVar7);
      }
      *local_128 = *local_128 + -1;
      if (*local_128 == 0) {
        _Py_Dealloc();
      }
      *plVar7 = *plVar7 + -1;
      if (*plVar7 == 0) {
        _Py_Dealloc(plVar7);
      }
      FUN_1801bc0e0(lVar14,local_d0,local_e8,local_d8);
    }
    else {
      plVar19 = (longlong *)0x0;
      if (puVar2 != (undefined *)0x0) {
        if ((*(uint *)(*(longlong *)(puVar1 + 8) + 0xa8) & 0x4000000) == 0) {
          uVar12 = FUN_1801bdde0(puVar2,puVar1);
          iVar5 = (int)uVar12;
        }
        else {
          uVar10 = FUN_1801bb510(puVar2,(longlong)puVar1);
          iVar5 = (int)uVar10;
        }
        if (iVar5 != 0) goto LAB_18005195f;
      }
LAB_180051c45:
      puVar4 = *(undefined8 **)(lVar14 + 0x90);
      plVar17 = (longlong *)*puVar4;
      plVar13 = (longlong *)puVar4[1];
      plVar8 = (longlong *)puVar4[2];
      *puVar4 = local_d0;
      puVar4[1] = local_e8;
      puVar4[2] = local_d8;
      if ((plVar17 != (longlong *)0x0) && (*plVar17 = *plVar17 + -1, *plVar17 == 0)) {
        _Py_Dealloc();
      }
      if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
        _Py_Dealloc(plVar13);
      }
      if ((plVar8 != (longlong *)0x0) && (*plVar8 = *plVar8 + -1, *plVar8 == 0)) {
        _Py_Dealloc(plVar8);
      }
      if ((local_110 != (longlong *)0x0) && (*local_110 = *local_110 + -1, *local_110 == 0)) {
        _Py_Dealloc();
      }
      if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
        _Py_Dealloc(plVar7);
      }
      if ((plVar19 != (longlong *)0x0) && (*plVar19 = *plVar19 + -1, *plVar19 == 0)) {
        _Py_Dealloc(plVar19);
      }
      FUN_1801c1020("main.Api.get_background_image",iVar21,iVar6,puVar18);
      plVar13 = (longlong *)0x0;
    }
    plVar9 = local_e0;
    if (local_e0 == (longlong *)0x0) goto LAB_180051daf;
  }
  else {
    if (*(code **)(plVar13[1] + 0x90) == (code *)0x0) {
      plVar7 = (longlong *)PyObject_GetAttr(plVar13,*(undefined8 *)(puVar18 + 0x3898));
    }
    else {
      plVar7 = (longlong *)(**(code **)(plVar13[1] + 0x90))();
    }
    if (plVar7 == (longlong *)0x0) {
      iVar6 = 0x4df;
      iVar21 = 0xd41a;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    *plVar13 = *plVar13 + -1;
    if (*plVar13 == 0) {
      _Py_Dealloc(plVar13);
    }
    if (*(code **)(plVar7[1] + 0x90) == (code *)0x0) {
      plVar13 = (longlong *)PyObject_GetAttr(plVar7,*(undefined8 *)(PTR_DAT_1801e5048 + 0x30a0));
    }
    else {
      plVar13 = (longlong *)(**(code **)(plVar7[1] + 0x90))();
    }
    if (plVar13 == (longlong *)0x0) {
      iVar6 = 0x4df;
      iVar21 = 0xd41d;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    *plVar7 = *plVar7 + -1;
    if (*plVar7 == 0) {
      _Py_Dealloc(plVar7);
    }
    puVar18 = PTR_DAT_1801e5048;
    plVar7 = (longlong *)0x0;
    if (DAT_1801f1468 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
      if (DAT_1801f0aa8 == (longlong *)0x0) {
        uVar10 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x37e0);
        plVar19 = (longlong *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar10);
        puVar18 = PTR_DAT_1801e5048;
        if ((plVar19 == (longlong *)0x0) &&
           (lVar14 = PyErr_Occurred(), puVar18 = PTR_DAT_1801e5048, lVar14 == 0)) {
          PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar10);
          puVar18 = PTR_DAT_1801e5048;
        }
      }
      else {
        *DAT_1801f0aa8 = *DAT_1801f0aa8 + 1;
        plVar19 = DAT_1801f0aa8;
      }
    }
    else {
      lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x37e0);
      plVar19 = (longlong *)
                _PyDict_GetItem_KnownHash
                          (*(longlong *)PTR_DAT_1801e5048,lVar14,*(undefined8 *)(lVar14 + 0x18));
      puVar18 = PTR_DAT_1801e5048;
      DAT_1801f1468 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
      DAT_1801f0aa8 = plVar19;
      if (plVar19 == (longlong *)0x0) {
        lVar16 = PyErr_Occurred();
        if (lVar16 == 0) {
          plVar19 = (longlong *)FUN_1801bb940(lVar14);
          puVar18 = PTR_DAT_1801e5048;
        }
        else {
          plVar19 = (longlong *)0x0;
          puVar18 = PTR_DAT_1801e5048;
        }
      }
      else {
        *plVar19 = *plVar19 + 1;
      }
    }
    if (plVar19 == (longlong *)0x0) {
      iVar6 = 0x4df;
      iVar21 = 0xd420;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    if (*(code **)(plVar19[1] + 0x90) == (code *)0x0) {
      plVar17 = (longlong *)PyObject_GetAttr(plVar19,*(undefined8 *)(puVar18 + 0x3898));
    }
    else {
      plVar17 = (longlong *)(**(code **)(plVar19[1] + 0x90))();
    }
    if (plVar17 == (longlong *)0x0) {
      iVar6 = 0x4df;
      iVar21 = 0xd422;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    *plVar19 = *plVar19 + -1;
    if (*plVar19 == 0) {
      _Py_Dealloc(plVar19);
    }
    if (*(code **)(plVar17[1] + 0x90) == (code *)0x0) {
      plVar19 = (longlong *)PyObject_GetAttr(plVar17,*(undefined8 *)(PTR_DAT_1801e5048 + 0x22f8));
    }
    else {
      plVar19 = (longlong *)(**(code **)(plVar17[1] + 0x90))();
    }
    if (plVar19 == (longlong *)0x0) {
      iVar6 = 0x4df;
      iVar21 = 0xd425;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    *plVar17 = *plVar17 + -1;
    if (*plVar17 == 0) {
      _Py_Dealloc(plVar17);
    }
    if (DAT_1801ef198 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
      if (DAT_1801f0560 == (longlong *)0x0) {
        uVar10 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x27d0);
        plVar17 = (longlong *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar10);
        if ((plVar17 == (longlong *)0x0) && (lVar14 = PyErr_Occurred(), lVar14 == 0)) {
          PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar10);
        }
      }
      else {
        *DAT_1801f0560 = *DAT_1801f0560 + 1;
        plVar17 = DAT_1801f0560;
      }
    }
    else {
      lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x27d0);
      plVar17 = (longlong *)
                _PyDict_GetItem_KnownHash
                          (*(longlong *)PTR_DAT_1801e5048,lVar14,*(undefined8 *)(lVar14 + 0x18));
      DAT_1801ef198 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
      DAT_1801f0560 = plVar17;
      if (plVar17 == (longlong *)0x0) {
        lVar16 = PyErr_Occurred();
        if (lVar16 == 0) {
          plVar17 = (longlong *)FUN_1801bb940(lVar14);
        }
        else {
          plVar17 = (longlong *)0x0;
        }
      }
      else {
        *plVar17 = *plVar17 + 1;
      }
    }
    if (plVar17 == (longlong *)0x0) {
      iVar6 = 0x4df;
      iVar21 = 0xd428;
      plVar17 = (longlong *)0x0;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    plVar7 = (longlong *)0x0;
    lVar14 = 0;
    if (((code *)plVar19[1] == PyMethod_Type_exref) &&
       (plVar7 = (longlong *)plVar19[3], plVar7 != (longlong *)0x0)) {
      plVar8 = (longlong *)plVar19[2];
      *plVar7 = *plVar7 + 1;
      *plVar8 = *plVar8 + 1;
      *plVar19 = *plVar19 + -1;
      if (*plVar19 == 0) {
        _Py_Dealloc(plVar19);
      }
      lVar14 = 1;
      plVar19 = plVar8;
    }
    local_a0[1] = plVar7;
    local_a0[2] = plVar17;
    plVar8 = (longlong *)
             FUN_1801bbf50((longlong)plVar19,local_a0 + (2 - lVar14),(ulonglong)((int)lVar14 + 1));
    if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
      _Py_Dealloc(plVar7);
    }
    *plVar17 = *plVar17 + -1;
    if (*plVar17 == 0) {
      _Py_Dealloc(plVar17);
    }
    plVar17 = (longlong *)0x0;
    local_128 = (longlong *)0x0;
    if (plVar8 == (longlong *)0x0) {
      iVar6 = 0x4df;
      iVar21 = 0xd43d;
      plVar7 = (longlong *)0x0;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    *plVar19 = *plVar19 + -1;
    if (*plVar19 == 0) {
      _Py_Dealloc(plVar19);
    }
    plVar7 = (longlong *)0x0;
    lVar14 = 0;
    if (((code *)plVar13[1] == PyMethod_Type_exref) &&
       (plVar7 = (longlong *)plVar13[3], plVar7 != (longlong *)0x0)) {
      plVar19 = (longlong *)plVar13[2];
      *plVar7 = *plVar7 + 1;
      *plVar19 = *plVar19 + 1;
      *plVar13 = *plVar13 + -1;
      if (*plVar13 == 0) {
        _Py_Dealloc(plVar13);
      }
      lVar14 = 1;
      plVar13 = plVar19;
    }
    local_48 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x1ad8);
    local_40 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x4d40);
    local_38 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x1c90);
    local_58 = plVar7;
    local_50 = plVar8;
    plVar9 = (longlong *)
             FUN_1801bbf50((longlong)plVar13,local_a0 + (10 - lVar14),(ulonglong)((int)lVar14 + 4));
    if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
      _Py_Dealloc(plVar7);
    }
    plVar20 = (longlong *)0x0;
    plVar19 = (longlong *)0x0;
    *plVar8 = *plVar8 + -1;
    if (*plVar8 == 0) {
      _Py_Dealloc(plVar8);
    }
    plVar7 = (longlong *)0x0;
    if (plVar9 == (longlong *)0x0) {
      iVar6 = 0x4df;
      iVar21 = 0xd454;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    *plVar13 = *plVar13 + -1;
    if (*plVar13 == 0) {
      _Py_Dealloc(plVar13);
    }
    puVar18 = PTR_DAT_1801e5048;
    local_e0 = plVar9;
    if (DAT_1801ef910 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
      if (DAT_1801f16a8 == (longlong *)0x0) {
        uVar10 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x37e0);
        plVar13 = (longlong *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar10);
        puVar18 = PTR_DAT_1801e5048;
        if ((plVar13 == (longlong *)0x0) &&
           (lVar14 = PyErr_Occurred(), puVar18 = PTR_DAT_1801e5048, lVar14 == 0)) {
          PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar10);
          puVar18 = PTR_DAT_1801e5048;
        }
      }
      else {
        *DAT_1801f16a8 = *DAT_1801f16a8 + 1;
        plVar13 = DAT_1801f16a8;
      }
    }
    else {
      lVar14 = *(longlong *)(PTR_DAT_1801e5048 + 0x37e0);
      plVar13 = (longlong *)
                _PyDict_GetItem_KnownHash
                          (*(longlong *)PTR_DAT_1801e5048,lVar14,*(undefined8 *)(lVar14 + 0x18));
      puVar18 = PTR_DAT_1801e5048;
      DAT_1801ef910 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
      DAT_1801f16a8 = plVar13;
      if (plVar13 == (longlong *)0x0) {
        lVar16 = PyErr_Occurred();
        if (lVar16 == 0) {
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
      iVar6 = 0x4e1;
      iVar21 = 0xd462;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    if (*(code **)(plVar13[1] + 0x90) == (code *)0x0) {
      plVar7 = (longlong *)PyObject_GetAttr(plVar13,*(undefined8 *)(puVar18 + 0x3898));
    }
    else {
      plVar7 = (longlong *)(**(code **)(plVar13[1] + 0x90))();
    }
    if (plVar7 == (longlong *)0x0) {
      iVar6 = 0x4e1;
      iVar21 = 0xd464;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    *plVar13 = *plVar13 + -1;
    if (*plVar13 == 0) {
      _Py_Dealloc(plVar13);
    }
    if (*(code **)(plVar7[1] + 0x90) == (code *)0x0) {
      plVar13 = (longlong *)PyObject_GetAttr(plVar7,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2660));
    }
    else {
      plVar13 = (longlong *)(**(code **)(plVar7[1] + 0x90))();
    }
    if (plVar13 == (longlong *)0x0) {
      iVar6 = 0x4e1;
      iVar21 = 0xd467;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    *plVar7 = *plVar7 + -1;
    if (*plVar7 == 0) {
      _Py_Dealloc();
    }
    lVar14 = 0;
    plVar7 = (longlong *)0x0;
    if (((code *)plVar13[1] == PyMethod_Type_exref) &&
       (plVar7 = (longlong *)plVar13[3], plVar7 != (longlong *)0x0)) {
      plVar17 = (longlong *)plVar13[2];
      *plVar7 = *plVar7 + 1;
      *plVar17 = *plVar17 + 1;
      *plVar13 = *plVar13 + -1;
      if (*plVar13 == 0) {
        _Py_Dealloc(plVar13);
      }
      lVar14 = 1;
      plVar13 = plVar17;
    }
    local_a0[3] = plVar7;
    local_80 = plVar9;
    plVar17 = (longlong *)
              FUN_1801bbf50((longlong)plVar13,local_a0 + (4 - lVar14),(ulonglong)((int)lVar14 + 1));
    if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
      _Py_Dealloc(plVar7);
    }
    plVar7 = (longlong *)0x0;
    if (plVar17 == (longlong *)0x0) {
      iVar6 = 0x4e1;
      iVar21 = 0xd47c;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
LAB_180050d50:
      plVar17 = (longlong *)0x0;
      goto LAB_180050d53;
    }
    *plVar13 = *plVar13 + -1;
    if (*plVar13 == 0) {
      _Py_Dealloc(plVar13);
    }
    plVar13 = (longlong *)0x0;
    iVar6 = FUN_1801c28c0((undefined *)plVar17);
    if (iVar6 < 0) {
      iVar6 = 0x4e1;
      iVar21 = 0xd480;
      plVar13 = (longlong *)0x0;
LAB_180050f11:
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      *plVar17 = *plVar17 + -1;
      if (*plVar17 == 0) {
        _Py_Dealloc(plVar17);
      }
      goto LAB_180050d50;
    }
    *plVar17 = *plVar17 + -1;
    if (*plVar17 == 0) {
      _Py_Dealloc(plVar17);
    }
    if (iVar6 != 0) {
      plVar17 = (longlong *)PyTuple_New(2);
      if (plVar17 == (longlong *)0x0) {
        iVar6 = 0x4e5;
        iVar21 = 0xd4a5;
        plVar17 = (longlong *)0x0;
        puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
        goto LAB_180050d53;
      }
      *plVar9 = *plVar9 + 1;
      puVar18 = PTR_DAT_1801e5048;
      plVar17[3] = (longlong)plVar9;
      plVar13 = *(longlong **)(puVar18 + 0x3ce0);
      *plVar13 = *plVar13 + 1;
      lVar14 = DAT_1801ef4b0;
      plVar17[4] = *(longlong *)(puVar18 + 0x3ce0);
      plVar13 = (longlong *)FUN_1801bbe10(lVar14,plVar17,0);
      if (plVar13 == (longlong *)0x0) {
        iVar6 = 0x4e5;
        iVar21 = 0xd4ad;
        goto LAB_180050f11;
      }
      *plVar17 = *plVar17 + -1;
      if (*plVar17 == 0) {
        _Py_Dealloc(plVar17);
      }
      plVar8 = FUN_1801bc150((longlong)plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2668));
      local_108 = plVar8;
      if (plVar8 == (longlong *)0x0) {
        iVar6 = 0x4e5;
        iVar21 = 0xd4b0;
        puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
        goto LAB_180050d50;
      }
      plVar19 = FUN_1801bc150((longlong)plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2588));
      plVar7 = plVar19;
      if (plVar19 == (longlong *)0x0) {
        iVar21 = 0xd4b2;
      }
      else {
        plVar17 = (longlong *)0x0;
        plVar8 = plVar17;
        if (((code *)plVar19[1] == PyMethod_Type_exref) &&
           (plVar20 = (longlong *)plVar19[3], plVar8 = (longlong *)0x0, plVar20 != (longlong *)0x0))
        {
          plVar7 = (longlong *)plVar19[2];
          *plVar20 = *plVar20 + 1;
          *plVar7 = *plVar7 + 1;
          *plVar19 = *plVar19 + -1;
          if (*plVar19 == 0) {
            _Py_Dealloc();
          }
          plVar8 = (longlong *)0x1;
        }
        local_70 = 0;
        local_78 = plVar20;
        plVar19 = (longlong *)
                  FUN_1801bbf50((longlong)plVar7,local_a0 + (6 - (longlong)plVar8),(ulonglong)plVar8
                               );
        if ((plVar20 != (longlong *)0x0) && (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
          _Py_Dealloc(plVar20);
        }
        if (plVar19 != (longlong *)0x0) {
          *plVar7 = *plVar7 + -1;
          if (*plVar7 == 0) {
            _Py_Dealloc(plVar7);
          }
          *plVar13 = *plVar13 + -1;
          if (*plVar13 == 0) {
            _Py_Dealloc(plVar13);
          }
          lVar14 = _PyThreadState_UncheckedGet();
          puVar4 = *(undefined8 **)(lVar14 + 0x90);
          do {
            puVar15 = puVar4;
            local_118 = (code *)puVar15[1];
            if ((local_118 != (code *)0x0) && (local_118 != _Py_NoneStruct_exref)) break;
            puVar4 = (undefined8 *)puVar15[3];
          } while ((undefined8 *)puVar15[3] != (undefined8 *)0x0);
          local_f0 = (longlong *)*puVar15;
          local_100 = (code *)puVar15[2];
          if (local_f0 != (longlong *)0x0) {
            *local_f0 = *local_f0 + 1;
          }
          if (local_118 != (code *)0x0) {
            *(longlong *)local_118 = *(longlong *)local_118 + 1;
          }
          if (local_100 != (code *)0x0) {
            *(longlong *)local_100 = *(longlong *)local_100 + 1;
          }
          puVar18 = PTR_DAT_1801e5048;
          local_130 = (longlong *)0x0;
          local_120 = lVar14;
          local_c0 = plVar19;
          if (DAT_1801efe00 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
            if (DAT_1801f0e18 == (longlong *)0x0) {
              uVar10 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x1c10);
              plVar7 = (longlong *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar10);
              puVar18 = PTR_DAT_1801e5048;
              if ((plVar7 == (longlong *)0x0) &&
                 (lVar16 = PyErr_Occurred(), puVar18 = PTR_DAT_1801e5048, lVar16 == 0)) {
                PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",
                             uVar10);
                puVar18 = PTR_DAT_1801e5048;
              }
            }
            else {
              *DAT_1801f0e18 = *DAT_1801f0e18 + 1;
              plVar7 = DAT_1801f0e18;
            }
          }
          else {
            lVar16 = *(longlong *)(PTR_DAT_1801e5048 + 0x1c10);
            plVar7 = (longlong *)
                     _PyDict_GetItem_KnownHash
                               (*(longlong *)PTR_DAT_1801e5048,lVar16,*(undefined8 *)(lVar16 + 0x18)
                               );
            puVar18 = PTR_DAT_1801e5048;
            DAT_1801efe00 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
            DAT_1801f0e18 = plVar7;
            if (plVar7 == (longlong *)0x0) {
              lVar11 = PyErr_Occurred();
              if (lVar11 == 0) {
                plVar7 = (longlong *)FUN_1801bb940(lVar16);
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
          plVar13 = plVar17;
          if (plVar7 == (longlong *)0x0) {
            iVar6 = 0xd4e0;
            plVar19 = local_130;
            plVar8 = plVar17;
            puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
LAB_1800511e9:
            if ((plVar17 != (longlong *)0x0) && (*plVar17 = *plVar17 + -1, *plVar17 == 0)) {
              _Py_Dealloc(plVar17);
            }
            local_110 = (longlong *)0x0;
            if ((plVar19 != (longlong *)0x0) && (*plVar19 = *plVar19 + -1, *plVar19 == 0)) {
              _Py_Dealloc(plVar19);
            }
            local_130 = (longlong *)0x0;
            if ((plVar8 != (longlong *)0x0) && (*plVar8 = *plVar8 + -1, *plVar8 == 0)) {
              _Py_Dealloc(plVar8);
            }
            local_128 = (longlong *)0x0;
            if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
              _Py_Dealloc(plVar13);
            }
            FUN_1801c1020("main.Api.get_background_image",iVar6,0x4e6,puVar18);
            uVar10 = FUN_1801bc330(lVar14,&local_130,&local_128,&local_110);
            plVar13 = local_110;
            plVar19 = local_128;
            plVar7 = local_130;
            if ((int)uVar10 < 0) {
              iVar21 = 0xd545;
            }
            else {
              plVar8 = (longlong *)PyTuple_Pack(3,local_130,local_128,local_110);
              plVar17 = local_108;
              if (plVar8 == (longlong *)0x0) {
                iVar21 = 0xd549;
              }
              else {
                plVar9 = (longlong *)FUN_1801bbe10((longlong)local_108,plVar8,0);
                *plVar17 = *plVar17 + -1;
                if (*plVar17 == 0) {
                  _Py_Dealloc(plVar17);
                }
                *plVar8 = *plVar8 + -1;
                local_108 = (longlong *)0x0;
                if (*plVar8 == 0) {
                  _Py_Dealloc(plVar8);
                }
                if (plVar9 == (longlong *)0x0) {
                  iVar21 = 0xd54e;
                }
                else {
                  iVar6 = FUN_1801c28c0((undefined *)plVar9);
                  *plVar9 = *plVar9 + -1;
                  if (*plVar9 == 0) {
                    _Py_Dealloc(plVar9);
                  }
                  if (iVar6 < 0) {
                    iVar21 = 0xd552;
                  }
                  else {
                    if (iVar6 != 0) {
                      if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
                        _Py_Dealloc(plVar7);
                      }
                      if ((plVar19 != (longlong *)0x0) && (*plVar19 = *plVar19 + -1, *plVar19 == 0))
                      {
                        _Py_Dealloc(plVar19);
                      }
                      if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0))
                      {
                        _Py_Dealloc(plVar13);
                      }
                      plVar17 = (longlong *)0x0;
                      FUN_1801bc0e0(local_120,local_f0,local_118,local_100);
                      goto LAB_180051749;
                    }
                    lVar14 = PyThreadState_Get();
                    FUN_1801bb760(lVar14,plVar7,plVar19,plVar13);
                    plVar7 = (longlong *)0x0;
                    plVar19 = (longlong *)0x0;
                    plVar13 = (longlong *)0x0;
                    iVar21 = 0xd55a;
                  }
                }
              }
            }
            puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
            iVar6 = 0x4e5;
            FUN_1801bc0e0(local_120,local_f0,local_118,local_100);
            plVar17 = (longlong *)0x0;
          }
          else {
            if (*(code **)(plVar7[1] + 0x90) == (code *)0x0) {
              plVar8 = (longlong *)PyObject_GetAttr(plVar7,*(undefined8 *)(puVar18 + 0x1be0));
            }
            else {
              plVar8 = (longlong *)(**(code **)(plVar7[1] + 0x90))();
            }
            puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
            if (plVar8 == (longlong *)0x0) {
              iVar6 = 0xd4e2;
              *plVar7 = *plVar7 + -1;
              plVar19 = local_130;
              if (*plVar7 == 0) {
                _Py_Dealloc(plVar7);
                plVar19 = local_130;
              }
              goto LAB_1800511e9;
            }
            *plVar7 = *plVar7 + -1;
            if (*plVar7 == 0) {
              _Py_Dealloc(plVar7);
            }
            if (*(code **)(plVar19[1] + 0x90) == (code *)0x0) {
              plVar13 = (longlong *)
                        PyObject_GetAttr(plVar19,*(undefined8 *)(PTR_DAT_1801e5048 + 0x3cf0));
            }
            else {
              plVar13 = (longlong *)(**(code **)(plVar19[1] + 0x90))();
            }
            if (plVar13 == (longlong *)0x0) {
              iVar6 = 0xd4e5;
              plVar19 = local_130;
              puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
              goto LAB_1800511e9;
            }
            if (((code *)plVar13[1] == PyMethod_Type_exref) &&
               (plVar17 = (longlong *)plVar13[3], plVar17 != (longlong *)0x0)) {
              plVar7 = (longlong *)plVar13[2];
              *plVar17 = *plVar17 + 1;
              *plVar7 = *plVar7 + 1;
              *plVar13 = *plVar13 + -1;
              if (*plVar13 == 0) {
                _Py_Dealloc(plVar13);
              }
              local_b0 = 0;
              local_b8 = plVar17;
              plVar19 = (longlong *)FUN_1801bbf50((longlong)plVar7,&local_b8,1);
              *plVar17 = *plVar17 + -1;
              lVar14 = local_120;
              if (*plVar17 == 0) {
                _Py_Dealloc();
                lVar14 = local_120;
              }
            }
            else {
              local_b0 = 0;
              local_b8 = plVar17;
              plVar19 = (longlong *)FUN_1801bbf50((longlong)plVar13,&local_b0,0);
              plVar7 = plVar13;
            }
            if (plVar19 == (longlong *)0x0) {
              iVar6 = 0xd4f9;
              plVar13 = plVar7;
              plVar17 = (longlong *)0x0;
              plVar19 = local_130;
              puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
              goto LAB_1800511e9;
            }
            *plVar7 = *plVar7 + -1;
            if (*plVar7 == 0) {
              _Py_Dealloc();
            }
            plVar7 = (longlong *)0x0;
            lVar16 = 0;
            plVar9 = plVar8;
            if (((code *)plVar8[1] == PyMethod_Type_exref) &&
               (plVar7 = (longlong *)plVar8[3], plVar7 != (longlong *)0x0)) {
              plVar9 = (longlong *)plVar8[2];
              *plVar7 = *plVar7 + 1;
              *plVar9 = *plVar9 + 1;
              *plVar8 = *plVar8 + -1;
              if (*plVar8 == 0) {
                _Py_Dealloc(plVar8);
              }
              lVar16 = 1;
            }
            local_68 = plVar7;
            local_60 = plVar19;
            plVar17 = (longlong *)
                      FUN_1801bbf50((longlong)plVar9,local_a0 + (8 - lVar16),
                                    (ulonglong)((int)lVar16 + 1));
            if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
              _Py_Dealloc(plVar7);
            }
            plVar13 = (longlong *)0x0;
            *plVar19 = *plVar19 + -1;
            if (*plVar19 == 0) {
              _Py_Dealloc(plVar19);
            }
            if (plVar17 == (longlong *)0x0) {
              iVar6 = 0xd510;
              plVar19 = local_130;
              plVar8 = plVar9;
              puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
              goto LAB_1800511e9;
            }
            *plVar9 = *plVar9 + -1;
            if (*plVar9 == 0) {
              _Py_Dealloc(plVar9);
            }
            if (*(code **)(plVar17[1] + 0x90) == (code *)0x0) {
              plVar8 = (longlong *)PyObject_GetAttr(plVar17);
            }
            else {
              plVar8 = (longlong *)(**(code **)(plVar17[1] + 0x90))();
            }
            if (plVar8 == (longlong *)0x0) {
              iVar6 = 0xd514;
              plVar19 = local_130;
              puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
              goto LAB_1800511e9;
            }
            *plVar17 = *plVar17 + -1;
            if (*plVar17 == 0) {
              _Py_Dealloc(plVar17);
            }
            plVar7 = (longlong *)0x0;
            lVar16 = 0;
            plVar9 = plVar8;
            if (((code *)plVar8[1] == PyMethod_Type_exref) &&
               (plVar7 = (longlong *)plVar8[3], plVar7 != (longlong *)0x0)) {
              plVar9 = (longlong *)plVar8[2];
              *plVar7 = *plVar7 + 1;
              *plVar9 = *plVar9 + 1;
              *plVar8 = *plVar8 + -1;
              if (*plVar8 == 0) {
                _Py_Dealloc(plVar8);
              }
              lVar16 = 1;
            }
            local_a0[0] = *(longlong **)(PTR_DAT_1801e5048 + 0x4a60);
            local_a8 = plVar7;
            plVar17 = (longlong *)
                      FUN_1801bbf50((longlong)plVar9,local_a0 + -lVar16,(ulonglong)((int)lVar16 + 1)
                                   );
            if ((plVar7 != (longlong *)0x0) && (*plVar7 = *plVar7 + -1, *plVar7 == 0)) {
              _Py_Dealloc(plVar7);
            }
            if (plVar17 == (longlong *)0x0) {
              iVar6 = 0xd529;
              plVar17 = (longlong *)0x0;
              plVar19 = (longlong *)0x0;
              plVar8 = plVar9;
              puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
              goto LAB_1800511e9;
            }
            *plVar9 = *plVar9 + -1;
            if (*plVar9 == 0) {
              _Py_Dealloc(plVar9);
            }
            if ((local_f0 != (longlong *)0x0) && (*local_f0 = *local_f0 + -1, *local_f0 == 0)) {
              _Py_Dealloc();
            }
            if ((local_118 != (code *)0x0) &&
               (*(longlong *)local_118 = *(longlong *)local_118 + -1, *(longlong *)local_118 == 0))
            {
              _Py_Dealloc();
            }
            local_f8 = plVar17;
            if ((local_100 != (code *)0x0) &&
               (*(longlong *)local_100 = *(longlong *)local_100 + -1, *(longlong *)local_100 == 0))
            {
              _Py_Dealloc();
              local_f8 = plVar17;
            }
LAB_180051749:
            plVar8 = local_108;
            plVar19 = (longlong *)0x0;
            plVar7 = (longlong *)0x0;
            plVar13 = (longlong *)0x0;
            if (local_108 != (longlong *)0x0) {
              plVar9 = (longlong *)
                       FUN_1801bbe10((longlong)local_108,*(undefined8 *)(PTR_DAT_1801e5048 + 0x4fd0)
                                     ,0);
              *plVar8 = *plVar8 + -1;
              if (*plVar8 == 0) {
                _Py_Dealloc(plVar8);
              }
              if (plVar9 == (longlong *)0x0) {
                iVar6 = 0x4e5;
                iVar21 = 0xd574;
                plVar17 = (longlong *)0x0;
                puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                goto LAB_180050d53;
              }
              *plVar9 = *plVar9 + -1;
              if (*plVar9 == 0) {
                _Py_Dealloc(plVar9);
              }
            }
            plVar13 = (longlong *)PyDict_New();
            if (plVar13 == (longlong *)0x0) {
              iVar6 = 0x4ea;
              iVar21 = 0xd593;
              plVar17 = (longlong *)0x0;
              puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
            }
            else {
              iVar6 = PyDict_SetItem(plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x43f8),
                                     *(undefined8 *)(PTR_DAT_1801e5048 + 0x45b8));
              if (iVar6 < 0) {
                iVar6 = 0x4ea;
                iVar21 = 0xd595;
                plVar17 = (longlong *)0x0;
                puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
              }
              else if (plVar17 == (longlong *)0x0) {
                PyErr_Format(*(undefined8 *)PyExc_UnboundLocalError_exref,
                             "local variable \'%s\' referenced before assignment","encoded_string");
                iVar6 = 0x4eb;
                iVar21 = 0xd59e;
                plVar17 = (longlong *)0x0;
                puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
              }
              else {
                pcVar3 = (code *)plVar17[1];
                if (pcVar3 == PyUnicode_Type_exref) {
                  *plVar17 = *plVar17 + 1;
                  plVar19 = plVar17;
                }
                else {
                  if (pcVar3 == PyLong_Type_exref) {
                    plVar19 = (longlong *)(**(code **)(PyLong_Type_exref + 0x58))(plVar17);
                  }
                  else if (pcVar3 == PyFloat_Type_exref) {
                    plVar19 = (longlong *)(**(code **)(PyFloat_Type_exref + 0x58))(plVar17);
                  }
                  else {
                    plVar19 = (longlong *)
                              PyObject_Format(plVar17,*(undefined8 *)(PTR_DAT_1801e5048 + 0x28));
                  }
                  if (plVar19 == (longlong *)0x0) {
                    iVar6 = 0x4eb;
                    iVar21 = 0xd59f;
                    plVar17 = (longlong *)0x0;
                    puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                    goto LAB_180050d53;
                  }
                }
                plVar7 = (longlong *)
                         PyUnicode_Concat(*(undefined8 *)(PTR_DAT_1801e5048 + 0x2170),plVar19);
                if (plVar7 == (longlong *)0x0) {
                  iVar6 = 0x4eb;
                  iVar21 = 0xd5a1;
                  plVar17 = (longlong *)0x0;
                  puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                }
                else {
                  *plVar19 = *plVar19 + -1;
                  if (*plVar19 == 0) {
                    _Py_Dealloc(plVar19);
                  }
                  plVar19 = (longlong *)0x0;
                  iVar6 = PyDict_SetItem(plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2dd0),plVar7)
                  ;
                  if (-1 < iVar6) {
                    *plVar7 = *plVar7 + -1;
                    plVar9 = local_e0;
                    if (*plVar7 == 0) {
                      _Py_Dealloc(plVar7);
                      plVar9 = local_e0;
                    }
                    goto LAB_180051d8a;
                  }
                  iVar6 = 0x4ea;
                  iVar21 = 0xd5a4;
                  plVar17 = (longlong *)0x0;
                  puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                }
              }
            }
          }
          goto LAB_180050d53;
        }
        iVar21 = 0xd4c6;
        plVar8 = local_108;
      }
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      plVar19 = (longlong *)0x0;
      iVar6 = 0x4e5;
      *plVar8 = *plVar8 + -1;
      plVar17 = local_128;
      if (*plVar8 == 0) {
        _Py_Dealloc(plVar8);
        plVar17 = local_128;
      }
      goto LAB_180050d53;
    }
    plVar17 = (longlong *)PyDict_New();
    if (plVar17 == (longlong *)0x0) {
      iVar6 = 0x4e2;
      iVar21 = 0xd48d;
      plVar17 = (longlong *)0x0;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      goto LAB_180050d53;
    }
    iVar6 = PyDict_SetItem(plVar17,*(undefined8 *)(PTR_DAT_1801e5048 + 0x25f0),
                           *(undefined8 *)(PTR_DAT_1801e5048 + 0x1008));
    plVar13 = plVar17;
    if (iVar6 < 0) {
      iVar6 = 0x4e2;
      iVar21 = 0xd48f;
      plVar13 = (longlong *)0x0;
      goto LAB_180050f11;
    }
LAB_180051d8a:
    FUN_1801bc0e0(local_c8,local_d0,local_e8,local_d8);
  }
  *plVar9 = *plVar9 + -1;
  if (*plVar9 == 0) {
    _Py_Dealloc(plVar9);
  }
LAB_180051daf:
  if ((local_c0 != (longlong *)0x0) && (*local_c0 = *local_c0 + -1, *local_c0 == 0)) {
    _Py_Dealloc();
  }
  if ((local_f8 != (longlong *)0x0) && (*local_f8 = *local_f8 + -1, *local_f8 == 0)) {
    _Py_Dealloc(local_f8);
  }
  return plVar13;
}

