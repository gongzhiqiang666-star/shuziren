
longlong * FUN_180064620(undefined8 param_1,longlong param_2)

{
  code *pcVar1;
  code *pcVar2;
  undefined *puVar3;
  undefined *puVar4;
  longlong lVar5;
  undefined8 *puVar6;
  int iVar7;
  int iVar8;
  longlong *plVar9;
  longlong *plVar10;
  ulonglong uVar12;
  longlong *plVar13;
  longlong *plVar14;
  longlong lVar15;
  undefined8 *puVar16;
  longlong *plVar17;
  longlong *plVar18;
  longlong *local_res8;
  longlong *local_res10;
  longlong *local_res18;
  longlong *local_res20;
  longlong *local_a8;
  longlong *local_a0;
  longlong local_98;
  longlong *local_90;
  longlong *local_88;
  longlong *local_80;
  longlong *local_78;
  longlong *local_70;
  undefined8 local_68;
  longlong *local_60;
  undefined8 local_58;
  undefined8 uVar11;
  
  plVar18 = (longlong *)0x0;
  local_a0 = (longlong *)0x0;
  local_80 = (longlong *)0x0;
  local_98 = _PyThreadState_UncheckedGet();
  puVar6 = *(undefined8 **)(local_98 + 0x90);
  do {
    puVar16 = puVar6;
    pcVar1 = (code *)puVar16[1];
    if ((pcVar1 != (code *)0x0) && (pcVar1 != _Py_NoneStruct_exref)) break;
    puVar6 = (undefined8 *)puVar16[3];
  } while ((undefined8 *)puVar16[3] != (undefined8 *)0x0);
  plVar17 = (longlong *)*puVar16;
  plVar14 = (longlong *)puVar16[2];
  if (plVar17 != (longlong *)0x0) {
    *plVar17 = *plVar17 + 1;
  }
  if (pcVar1 != (code *)0x0) {
    *(longlong *)pcVar1 = *(longlong *)pcVar1 + 1;
  }
  if (plVar14 != (longlong *)0x0) {
    *plVar14 = *plVar14 + 1;
  }
  pcVar2 = *(code **)(*(longlong *)(param_2 + 8) + 0x90);
  local_78 = plVar14;
  local_70 = plVar17;
  if (pcVar2 == (code *)0x0) {
    plVar9 = (longlong *)PyObject_GetAttr(param_2,*(undefined8 *)(PTR_DAT_1801e5048 + 0x1f28));
  }
  else {
    plVar9 = (longlong *)(*pcVar2)();
  }
  if (plVar9 == (longlong *)0x0) {
    iVar8 = 0x609;
    local_res10 = (longlong *)PTR_s_packed__build_temp__main_py_1801cc288;
    local_res8._0_4_ = 0xf9fa;
    plVar13 = plVar18;
  }
  else {
    if (*(code **)(plVar9[1] + 0x90) == (code *)0x0) {
      plVar13 = (longlong *)PyObject_GetAttr(plVar9,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2a38));
    }
    else {
      plVar13 = (longlong *)(**(code **)(plVar9[1] + 0x90))();
    }
    if (plVar13 == (longlong *)0x0) {
      iVar8 = 0x609;
      local_res8._0_4_ = 0xf9fc;
LAB_18006485b:
      *plVar9 = *plVar9 + -1;
      local_res10 = (longlong *)PTR_s_packed__build_temp__main_py_1801cc288;
      if (*plVar9 == 0) {
        _Py_Dealloc(plVar9);
      }
    }
    else {
      *plVar9 = *plVar9 + -1;
      if (*plVar9 == 0) {
        _Py_Dealloc(plVar9);
      }
      plVar10 = (longlong *)
                FUN_1801bbe10((longlong)plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x5118),0);
      if (plVar10 == (longlong *)0x0) {
        iVar8 = 0x609;
        local_res10 = (longlong *)PTR_s_packed__build_temp__main_py_1801cc288;
        local_res8._0_4_ = 63999;
      }
      else {
        *plVar13 = *plVar13 + -1;
        if (*plVar13 == 0) {
          _Py_Dealloc(plVar13);
        }
        plVar13 = (longlong *)0x0;
        plVar9 = (longlong *)PyDict_New();
        if (plVar9 != (longlong *)0x0) {
          iVar8 = PyDict_SetItem(plVar9,*(undefined8 *)(PTR_DAT_1801e5048 + 0x43f8),
                                 *(undefined8 *)(PTR_DAT_1801e5048 + 0x45b8));
          if (iVar8 < 0) {
            local_res8._0_4_ = 0xfa0f;
            plVar13 = plVar18;
          }
          else {
            iVar8 = FUN_1801c28c0((undefined *)plVar10);
            puVar3 = PTR_DAT_1801e5048;
            if (iVar8 < 0) {
              local_res8._0_4_ = 0xfa10;
              plVar13 = plVar18;
            }
            else {
              if (iVar8 == 0) {
                **(longlong **)(PTR_DAT_1801e5048 + 0xfa8) =
                     **(longlong **)(PTR_DAT_1801e5048 + 0xfa8) + 1;
                plVar13 = *(longlong **)(puVar3 + 0xfa8);
              }
              else {
                *plVar10 = *plVar10 + 1;
                plVar13 = plVar10;
              }
              iVar8 = PyDict_SetItem(plVar9,*(undefined8 *)(puVar3 + 0x4798),plVar13);
              if (-1 < iVar8) {
                *plVar13 = *plVar13 + -1;
                if (*plVar13 == 0) {
                  _Py_Dealloc(plVar13);
                }
                FUN_1801bc0e0(local_98,plVar17,pcVar1,plVar14);
                goto LAB_180064da9;
              }
              local_res8._0_4_ = 0xfa1a;
            }
          }
          iVar8 = 0x60a;
          local_a0 = plVar10;
          goto LAB_18006485b;
        }
        iVar8 = 0x60a;
        local_res10 = (longlong *)PTR_s_packed__build_temp__main_py_1801cc288;
        local_res8._0_4_ = 0xfa0d;
        local_a0 = plVar10;
      }
    }
  }
  local_88 = (longlong *)0x0;
  if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
    _Py_Dealloc(plVar13);
  }
  plVar17 = (longlong *)0x0;
  local_res18 = (longlong *)0x0;
  puVar3 = *(undefined **)PyExc_Exception_exref;
  puVar4 = *(undefined **)(local_98 + 0x58);
  if (puVar4 == puVar3) {
LAB_1800648d8:
    FUN_1801c1020("main.Api.get_token",(int)local_res8,iVar8,local_res10);
    lVar15 = local_98;
    uVar11 = FUN_1801bc330(local_98,&local_88,&local_res18,&local_80);
    plVar17 = local_res18;
    if ((int)uVar11 < 0) {
      iVar8 = 0x60b;
      plVar14 = (longlong *)PTR_s_packed__build_temp__main_py_1801cc288;
      local_res8._0_4_ = 0xfa36;
      goto LAB_180064c55;
    }
    lVar5 = *local_res18;
    *local_res18 = lVar5 + 1;
    pcVar2 = (code *)local_res18[1];
    if (pcVar2 == PyUnicode_Type_exref) {
      *local_res18 = lVar5 + 2;
      plVar9 = local_res18;
    }
    else if (pcVar2 == PyLong_Type_exref) {
      plVar9 = (longlong *)(**(code **)(PyLong_Type_exref + 0x58))(local_res18);
    }
    else if (pcVar2 == PyFloat_Type_exref) {
      plVar9 = (longlong *)(**(code **)(PyFloat_Type_exref + 0x58))(local_res18);
    }
    else {
      plVar9 = (longlong *)PyObject_Format(local_res18,*(undefined8 *)(PTR_DAT_1801e5048 + 0x28));
    }
    if (plVar9 == (longlong *)0x0) {
      iVar8 = 0x60c;
      iVar7 = 0xfa45;
LAB_180064a4e:
      plVar14 = (longlong *)PTR_s_packed__build_temp__main_py_1801cc288;
      local_res18 = (longlong *)0x0;
      local_res20 = (longlong *)0x0;
      local_a8 = (longlong *)0x0;
      lVar15 = _PyThreadState_UncheckedGet();
LAB_180064b40:
      puVar6 = *(undefined8 **)(lVar15 + 0x90);
      local_90 = (longlong *)*puVar6;
      local_68 = puVar6[1];
      local_58 = puVar6[2];
      *puVar6 = 0;
      puVar6[1] = 0;
      puVar6[2] = 0;
      uVar11 = FUN_1801bc330(lVar15,&local_res18,&local_res20,&local_a8);
      if ((int)uVar11 < 0) {
        local_res8 = *(longlong **)(lVar15 + 0x58);
        local_res10 = *(longlong **)(lVar15 + 0x60);
        local_res18 = *(longlong **)(lVar15 + 0x68);
        *(undefined8 *)(lVar15 + 0x58) = 0;
        *(undefined8 *)(lVar15 + 0x60) = 0;
        *(undefined8 *)(lVar15 + 0x68) = 0;
      }
      else {
        local_res8 = local_res18;
        local_res10 = local_res20;
        local_res18 = local_a8;
      }
      *plVar17 = *plVar17 + -1;
      if (*plVar17 == 0) {
        _Py_Dealloc(plVar17);
      }
      FUN_1801bc0e0(lVar15,local_90,local_68,local_58);
      local_90 = *(longlong **)(lVar15 + 0x68);
      local_res20 = *(longlong **)(lVar15 + 0x60);
      plVar9 = *(longlong **)(lVar15 + 0x58);
      *(longlong **)(lVar15 + 0x60) = local_res10;
      *(longlong **)(lVar15 + 0x68) = local_res18;
      *(longlong **)(lVar15 + 0x58) = local_res8;
      if ((plVar9 != (longlong *)0x0) && (*plVar9 = *plVar9 + -1, *plVar9 == 0)) {
        _Py_Dealloc(plVar9);
      }
      if ((local_res20 != (longlong *)0x0) && (*local_res20 = *local_res20 + -1, *local_res20 == 0))
      {
        _Py_Dealloc();
      }
      local_res8._0_4_ = iVar7;
      if ((local_90 != (longlong *)0x0) && (*local_90 = *local_90 + -1, *local_90 == 0)) {
        _Py_Dealloc();
      }
      goto LAB_180064c55;
    }
    plVar13 = (longlong *)PyUnicode_Concat(*(undefined8 *)(PTR_DAT_1801e5048 + 0xed0),plVar9);
    if (plVar13 == (longlong *)0x0) {
      iVar8 = 0x60c;
      iVar7 = 0xfa47;
LAB_180064aa1:
      plVar14 = (longlong *)PTR_s_packed__build_temp__main_py_1801cc288;
      local_res18 = (longlong *)0x0;
      local_res20 = (longlong *)0x0;
      local_a8 = (longlong *)0x0;
      lVar15 = _PyThreadState_UncheckedGet();
LAB_180064b2e:
      *plVar9 = *plVar9 + -1;
      if (*plVar9 == 0) {
        _Py_Dealloc(plVar9);
      }
      goto LAB_180064b40;
    }
    *plVar9 = *plVar9 + -1;
    if (*plVar9 == 0) {
      _Py_Dealloc(plVar9);
    }
    local_68 = 0;
    local_60 = plVar13;
    plVar14 = (longlong *)FUN_1801bbf50(DAT_1801f1718,&local_60,0x8000000000000001);
    if (plVar14 == (longlong *)0x0) {
      iVar8 = 0x60c;
      iVar7 = 0xfa4a;
      plVar9 = (longlong *)0x0;
LAB_180064aed:
      plVar14 = (longlong *)PTR_s_packed__build_temp__main_py_1801cc288;
      lVar15 = _PyThreadState_UncheckedGet();
      *plVar13 = *plVar13 + -1;
      local_res18 = (longlong *)0x0;
      local_a8 = (longlong *)0x0;
      local_res20 = (longlong *)0x0;
      if (*plVar13 == 0) {
        _Py_Dealloc(plVar13);
      }
      if (plVar9 == (longlong *)0x0) goto LAB_180064b40;
      goto LAB_180064b2e;
    }
    *plVar13 = *plVar13 + -1;
    if (*plVar13 == 0) {
      _Py_Dealloc(plVar13);
    }
    *plVar14 = *plVar14 + -1;
    if (*plVar14 == 0) {
      _Py_Dealloc(plVar14);
    }
    plVar9 = (longlong *)PyDict_New();
    if (plVar9 == (longlong *)0x0) {
      iVar8 = 0x60d;
      iVar7 = 0xfa57;
      goto LAB_180064a4e;
    }
    if ((code *)plVar17[1] == PyUnicode_Type_exref) {
      *plVar17 = *plVar17 + 1;
      plVar13 = plVar17;
    }
    else {
      plVar13 = (longlong *)PyObject_Str(plVar17);
    }
    if (plVar13 == (longlong *)0x0) {
      iVar8 = 0x60d;
      iVar7 = 0xfa59;
      goto LAB_180064aa1;
    }
    iVar8 = PyDict_SetItem(plVar9,*(undefined8 *)(PTR_DAT_1801e5048 + 0x25f0),plVar13);
    if (iVar8 < 0) {
      iVar8 = 0x60d;
      iVar7 = 0xfa5b;
      goto LAB_180064aed;
    }
    *plVar13 = *plVar13 + -1;
    if (*plVar13 == 0) {
      _Py_Dealloc(plVar13);
    }
    *local_88 = *local_88 + -1;
    if (*local_88 == 0) {
      _Py_Dealloc();
    }
    *plVar17 = *plVar17 + -1;
    if (*plVar17 == 0) {
      _Py_Dealloc(plVar17);
    }
    *local_80 = *local_80 + -1;
    if (*local_80 == 0) {
      _Py_Dealloc();
    }
    *plVar17 = *plVar17 + -1;
    if (*plVar17 == 0) {
      _Py_Dealloc(plVar17);
    }
    FUN_1801bc0e0(lVar15,local_70,pcVar1,local_78);
  }
  else {
    plVar14 = local_res10;
    if (puVar4 != (undefined *)0x0) {
      if ((*(uint *)(*(longlong *)(puVar3 + 8) + 0xa8) & 0x4000000) == 0) {
        uVar12 = FUN_1801bdde0(puVar4,puVar3);
        iVar7 = (int)uVar12;
      }
      else {
        uVar11 = FUN_1801bb510(puVar4,(longlong)puVar3);
        iVar7 = (int)uVar11;
      }
      if (iVar7 != 0) goto LAB_1800648d8;
    }
LAB_180064c55:
    puVar6 = *(undefined8 **)(local_98 + 0x90);
    plVar9 = (longlong *)*puVar6;
    plVar13 = (longlong *)puVar6[1];
    plVar10 = (longlong *)puVar6[2];
    *puVar6 = local_70;
    puVar6[1] = pcVar1;
    puVar6[2] = local_78;
    if ((plVar9 != (longlong *)0x0) && (*plVar9 = *plVar9 + -1, *plVar9 == 0)) {
      _Py_Dealloc(plVar9);
    }
    if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
      _Py_Dealloc();
    }
    if ((plVar10 != (longlong *)0x0) && (*plVar10 = *plVar10 + -1, *plVar10 == 0)) {
      _Py_Dealloc(plVar10);
    }
    if ((local_88 != (longlong *)0x0) && (*local_88 = *local_88 + -1, *local_88 == 0)) {
      _Py_Dealloc();
    }
    if ((plVar17 != (longlong *)0x0) && (*plVar17 = *plVar17 + -1, *plVar17 == 0)) {
      _Py_Dealloc(plVar17);
    }
    if ((local_80 != (longlong *)0x0) && (*local_80 = *local_80 + -1, *local_80 == 0)) {
      _Py_Dealloc();
    }
    FUN_1801c1020("main.Api.get_token",(int)local_res8,iVar8,plVar14);
    plVar9 = plVar18;
  }
  plVar10 = local_a0;
  if (local_a0 == (longlong *)0x0) {
    return plVar9;
  }
LAB_180064da9:
  *plVar10 = *plVar10 + -1;
  if (*plVar10 == 0) {
    _Py_Dealloc();
  }
  return plVar9;
}

