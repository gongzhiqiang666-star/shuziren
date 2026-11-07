
longlong * FUN_1800659f0(undefined8 param_1,longlong param_2)

{
  code *pcVar1;
  code *pcVar2;
  undefined *puVar3;
  undefined *puVar4;
  undefined8 uVar5;
  undefined8 *puVar6;
  int iVar7;
  int iVar8;
  longlong lVar9;
  longlong *plVar10;
  longlong *plVar11;
  longlong *plVar12;
  ulonglong uVar14;
  longlong *plVar15;
  longlong lVar16;
  undefined8 uVar17;
  undefined8 *puVar18;
  int iVar19;
  longlong *plVar20;
  undefined *puVar21;
  longlong *local_res10;
  longlong *local_res18;
  longlong *local_res20;
  longlong *local_98;
  longlong *local_90;
  longlong *local_88;
  longlong *local_80;
  undefined8 local_78;
  longlong *local_68;
  longlong *local_60 [4];
  undefined8 uVar13;
  
  plVar12 = (longlong *)0x0;
  plVar15 = (longlong *)0x0;
  lVar9 = _PyThreadState_UncheckedGet();
  puVar6 = *(undefined8 **)(lVar9 + 0x90);
  do {
    puVar18 = puVar6;
    pcVar1 = (code *)puVar18[1];
    if ((pcVar1 != (code *)0x0) && (pcVar1 != _Py_NoneStruct_exref)) break;
    puVar6 = (undefined8 *)puVar18[3];
  } while ((undefined8 *)puVar18[3] != (undefined8 *)0x0);
  local_80 = (longlong *)*puVar18;
  local_88 = (longlong *)puVar18[2];
  if (local_80 != (longlong *)0x0) {
    *local_80 = *local_80 + 1;
  }
  if (pcVar1 != (code *)0x0) {
    *(longlong *)pcVar1 = *(longlong *)pcVar1 + 1;
  }
  if (local_88 != (longlong *)0x0) {
    *local_88 = *local_88 + 1;
  }
  pcVar2 = *(code **)(*(longlong *)(param_2 + 8) + 0x90);
  if (pcVar2 == (code *)0x0) {
    plVar10 = (longlong *)PyObject_GetAttr(param_2,*(undefined8 *)(PTR_DAT_1801e5048 + 0x4068));
  }
  else {
    plVar10 = (longlong *)(*pcVar2)();
  }
  if (plVar10 == (longlong *)0x0) {
    iVar19 = 0x61c;
    iVar8 = 0xfd13;
  }
  else {
    plVar15 = (longlong *)PyDict_New();
    if (plVar15 == (longlong *)0x0) {
      iVar19 = 0x61c;
      iVar8 = 0xfd15;
    }
    else {
      iVar8 = PyDict_SetItem(plVar15,*(undefined8 *)(PTR_DAT_1801e5048 + 0x4798),
                             *(undefined8 *)(PTR_DAT_1801e5048 + 0xfa8));
      if (iVar8 < 0) {
        iVar19 = 0x61c;
        iVar8 = 0xfd17;
      }
      else {
        plVar12 = (longlong *)0x0;
        lVar16 = 0;
        if (((code *)plVar10[1] == PyMethod_Type_exref) &&
           (plVar12 = (longlong *)plVar10[3], plVar12 != (longlong *)0x0)) {
          plVar11 = (longlong *)plVar10[2];
          *plVar12 = *plVar12 + 1;
          *plVar11 = *plVar11 + 1;
          *plVar10 = *plVar10 + -1;
          if (*plVar10 == 0) {
            _Py_Dealloc(plVar10);
          }
          lVar16 = 1;
          plVar10 = plVar11;
        }
        local_68 = plVar12;
        local_60[0] = plVar15;
        plVar11 = (longlong *)
                  FUN_1801bbf50((longlong)plVar10,local_60 + -lVar16,(ulonglong)((int)lVar16 + 1));
        if ((plVar12 != (longlong *)0x0) && (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
          _Py_Dealloc(plVar12);
        }
        *plVar15 = *plVar15 + -1;
        if (*plVar15 == 0) {
          _Py_Dealloc(plVar15);
        }
        plVar20 = (longlong *)0x0;
        plVar15 = (longlong *)0x0;
        if (plVar11 == (longlong *)0x0) {
          iVar19 = 0x61c;
          iVar8 = 0xfd2b;
          plVar12 = (longlong *)0x0;
        }
        else {
          *plVar10 = *plVar10 + -1;
          if (*plVar10 == 0) {
            _Py_Dealloc(plVar10);
          }
          plVar10 = (longlong *)0x0;
          *plVar11 = *plVar11 + -1;
          if (*plVar11 == 0) {
            _Py_Dealloc(plVar11);
          }
          pcVar2 = *(code **)(*(longlong *)(param_2 + 8) + 0x90);
          if (pcVar2 == (code *)0x0) {
            plVar12 = (longlong *)
                      PyObject_GetAttr(param_2,*(undefined8 *)(PTR_DAT_1801e5048 + 0x1f28));
          }
          else {
            plVar12 = (longlong *)(*pcVar2)();
          }
          if (plVar12 == (longlong *)0x0) {
            iVar19 = 0x61d;
            iVar8 = 0xfd38;
          }
          else {
            iVar8 = PyObject_SetItem(plVar12,*(undefined8 *)(PTR_DAT_1801e5048 + 0x4798),
                                     *(undefined8 *)(PTR_DAT_1801e5048 + 0xfa8));
            if (iVar8 < 0) {
              iVar19 = 0x61d;
              iVar8 = 0xfd3a;
            }
            else {
              *plVar12 = *plVar12 + -1;
              if (*plVar12 == 0) {
                _Py_Dealloc(plVar12);
              }
              plVar12 = (longlong *)0x0;
              pcVar2 = *(code **)(*(longlong *)(param_2 + 8) + 0x90);
              if (pcVar2 == (code *)0x0) {
                plVar10 = (longlong *)
                          PyObject_GetAttr(param_2,*(undefined8 *)(PTR_DAT_1801e5048 + 0x4988));
              }
              else {
                plVar10 = (longlong *)(*pcVar2)();
              }
              if (plVar10 == (longlong *)0x0) {
                iVar19 = 0x61e;
                iVar8 = 0xfd44;
              }
              else {
                uVar14 = 0;
                if (((code *)plVar10[1] == PyMethod_Type_exref) &&
                   (plVar20 = (longlong *)plVar10[3], plVar20 != (longlong *)0x0)) {
                  plVar12 = (longlong *)plVar10[2];
                  *plVar20 = *plVar20 + 1;
                  *plVar12 = *plVar12 + 1;
                  *plVar10 = *plVar10 + -1;
                  if (*plVar10 == 0) {
                    _Py_Dealloc();
                  }
                  uVar14 = 1;
                  plVar10 = plVar12;
                }
                local_60[2] = (longlong *)0x0;
                local_60[1] = plVar20;
                plVar12 = (longlong *)
                          FUN_1801bbf50((longlong)plVar10,local_60 + (2 - uVar14),uVar14);
                if ((plVar20 != (longlong *)0x0) && (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
                  _Py_Dealloc(plVar20);
                }
                plVar15 = (longlong *)0x0;
                if (plVar12 == (longlong *)0x0) {
                  iVar19 = 0x61e;
                  iVar8 = 0xfd58;
                  plVar12 = (longlong *)0x0;
                }
                else {
                  *plVar10 = *plVar10 + -1;
                  if (*plVar10 == 0) {
                    _Py_Dealloc(plVar10);
                  }
                  plVar10 = (longlong *)0x0;
                  *plVar12 = *plVar12 + -1;
                  if (*plVar12 == 0) {
                    _Py_Dealloc(plVar12);
                  }
                  plVar12 = (longlong *)PyDict_New();
                  if (plVar12 == (longlong *)0x0) {
                    iVar8 = 0xfd66;
                  }
                  else {
                    iVar8 = PyDict_SetItem(plVar12,*(undefined8 *)(PTR_DAT_1801e5048 + 0x43f8),
                                           *(undefined8 *)(PTR_DAT_1801e5048 + 0x45b8));
                    if (iVar8 < 0) {
                      iVar8 = 0xfd68;
                    }
                    else {
                      iVar8 = PyDict_SetItem(plVar12,*(undefined8 *)(PTR_DAT_1801e5048 + 0x3480),
                                             *(undefined8 *)(PTR_DAT_1801e5048 + 0xee0));
                      if (-1 < iVar8) {
                        FUN_1801bc0e0(lVar9,local_80,pcVar1,local_88);
                        return plVar12;
                      }
                      iVar8 = 0xfd69;
                    }
                  }
                  iVar19 = 0x61f;
                }
              }
            }
          }
        }
      }
    }
  }
  puVar21 = PTR_s_packed__build_temp__main_py_1801cc288;
  if ((plVar12 != (longlong *)0x0) && (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
    _Py_Dealloc(plVar12);
  }
  local_90 = (longlong *)0x0;
  if ((plVar10 != (longlong *)0x0) && (*plVar10 = *plVar10 + -1, *plVar10 == 0)) {
    _Py_Dealloc(plVar10);
  }
  plVar12 = (longlong *)0x0;
  local_res10 = (longlong *)0x0;
  if ((plVar15 != (longlong *)0x0) && (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
    _Py_Dealloc(plVar15);
  }
  local_98 = (longlong *)0x0;
  puVar3 = *(undefined **)PyExc_Exception_exref;
  puVar4 = *(undefined **)(lVar9 + 0x58);
  if (puVar4 != puVar3) {
    plVar15 = (longlong *)0x0;
    if (puVar4 == (undefined *)0x0) goto LAB_18006608c;
    if ((*(uint *)(*(longlong *)(puVar3 + 8) + 0xa8) & 0x4000000) == 0) {
      uVar14 = FUN_1801bdde0(puVar4,puVar3);
      iVar7 = (int)uVar14;
    }
    else {
      uVar13 = FUN_1801bb510(puVar4,(longlong)puVar3);
      iVar7 = (int)uVar13;
    }
    if (iVar7 == 0) goto LAB_18006608c;
  }
  FUN_1801c1020("main.Api.clear_token",iVar8,iVar19,puVar21);
  uVar13 = FUN_1801bc330(lVar9,&local_90,&local_res10,&local_98);
  plVar12 = local_res10;
  if ((int)uVar13 < 0) {
    iVar19 = 0x620;
    iVar8 = 0xfd86;
    plVar15 = local_98;
    puVar21 = PTR_s_packed__build_temp__main_py_1801cc288;
  }
  else {
    *local_res10 = *local_res10 + 1;
    plVar15 = (longlong *)PyDict_New();
    puVar21 = PTR_s_packed__build_temp__main_py_1801cc288;
    if (plVar15 == (longlong *)0x0) {
      iVar8 = 0xfd96;
      local_res10 = plVar15;
      local_res18 = plVar15;
      local_res20 = plVar15;
      lVar16 = _PyThreadState_UncheckedGet();
    }
    else {
      if ((code *)plVar12[1] == PyUnicode_Type_exref) {
        *plVar12 = *plVar12 + 1;
        plVar10 = plVar12;
      }
      else {
        plVar10 = (longlong *)PyObject_Str(plVar12);
      }
      puVar21 = PTR_s_packed__build_temp__main_py_1801cc288;
      if (plVar10 == (longlong *)0x0) {
        local_res10 = (longlong *)0x0;
        iVar8 = 0xfd98;
        local_res18 = (longlong *)0x0;
        local_res20 = (longlong *)0x0;
        lVar16 = _PyThreadState_UncheckedGet();
      }
      else {
        iVar8 = PyDict_SetItem(plVar15,*(undefined8 *)(PTR_DAT_1801e5048 + 0x25f0),plVar10);
        puVar21 = PTR_s_packed__build_temp__main_py_1801cc288;
        if (-1 < iVar8) {
          *plVar10 = *plVar10 + -1;
          if (*plVar10 == 0) {
            _Py_Dealloc(plVar10);
          }
          *local_90 = *local_90 + -1;
          if (*local_90 == 0) {
            _Py_Dealloc();
          }
          *plVar12 = *plVar12 + -1;
          if (*plVar12 == 0) {
            _Py_Dealloc(plVar12);
          }
          *local_98 = *local_98 + -1;
          if (*local_98 == 0) {
            _Py_Dealloc();
          }
          *plVar12 = *plVar12 + -1;
          if (*plVar12 == 0) {
            _Py_Dealloc(plVar12);
          }
          FUN_1801bc0e0(lVar9,local_80,pcVar1,local_88);
          return plVar15;
        }
        local_res10 = (longlong *)0x0;
        iVar8 = 0xfd9a;
        local_res18 = (longlong *)0x0;
        local_res20 = (longlong *)0x0;
        lVar16 = _PyThreadState_UncheckedGet();
        *plVar10 = *plVar10 + -1;
        if (*plVar10 == 0) {
          _Py_Dealloc(plVar10);
        }
      }
      *plVar15 = *plVar15 + -1;
      if (*plVar15 == 0) {
        _Py_Dealloc(plVar15);
      }
    }
    puVar6 = *(undefined8 **)(lVar16 + 0x90);
    local_78 = puVar6[2];
    uVar13 = *puVar6;
    uVar5 = puVar6[1];
    *puVar6 = 0;
    puVar6[1] = 0;
    puVar6[2] = 0;
    uVar17 = FUN_1801bc330(lVar16,&local_res10,&local_res18,&local_res20);
    if ((int)uVar17 < 0) {
      local_res10 = *(longlong **)(lVar16 + 0x58);
      local_res18 = *(longlong **)(lVar16 + 0x60);
      local_res20 = *(longlong **)(lVar16 + 0x68);
      *(undefined8 *)(lVar16 + 0x58) = 0;
      *(undefined8 *)(lVar16 + 0x60) = 0;
      *(undefined8 *)(lVar16 + 0x68) = 0;
    }
    *plVar12 = *plVar12 + -1;
    if (*plVar12 == 0) {
      _Py_Dealloc(plVar12);
    }
    FUN_1801bc0e0(lVar16,uVar13,uVar5,local_78);
    plVar15 = *(longlong **)(lVar16 + 0x58);
    plVar10 = *(longlong **)(lVar16 + 0x60);
    plVar11 = *(longlong **)(lVar16 + 0x68);
    *(longlong **)(lVar16 + 0x58) = local_res10;
    *(longlong **)(lVar16 + 0x60) = local_res18;
    *(longlong **)(lVar16 + 0x68) = local_res20;
    if ((plVar15 != (longlong *)0x0) && (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
      _Py_Dealloc();
    }
    if ((plVar10 != (longlong *)0x0) && (*plVar10 = *plVar10 + -1, *plVar10 == 0)) {
      _Py_Dealloc(plVar10);
    }
    if ((plVar11 != (longlong *)0x0) && (*plVar11 = *plVar11 + -1, *plVar11 == 0)) {
      _Py_Dealloc(plVar11);
    }
    iVar19 = 0x621;
    plVar15 = local_98;
  }
LAB_18006608c:
  puVar6 = *(undefined8 **)(lVar9 + 0x90);
  plVar10 = (longlong *)*puVar6;
  plVar11 = (longlong *)puVar6[1];
  plVar20 = (longlong *)puVar6[2];
  *puVar6 = local_80;
  puVar6[1] = pcVar1;
  puVar6[2] = local_88;
  if ((plVar10 != (longlong *)0x0) && (*plVar10 = *plVar10 + -1, *plVar10 == 0)) {
    _Py_Dealloc(plVar10);
  }
  if ((plVar11 != (longlong *)0x0) && (*plVar11 = *plVar11 + -1, *plVar11 == 0)) {
    _Py_Dealloc();
  }
  if ((plVar20 != (longlong *)0x0) && (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
    _Py_Dealloc(plVar20);
  }
  if ((local_90 != (longlong *)0x0) && (*local_90 = *local_90 + -1, *local_90 == 0)) {
    _Py_Dealloc();
  }
  if ((plVar12 != (longlong *)0x0) && (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
    _Py_Dealloc(plVar12);
  }
  if ((plVar15 != (longlong *)0x0) && (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
    _Py_Dealloc(plVar15);
  }
  FUN_1801c1020("main.Api.clear_token",iVar8,iVar19,puVar21);
  return (longlong *)0x0;
}

