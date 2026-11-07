
longlong * FUN_180065090(undefined8 param_1,longlong param_2,undefined8 param_3)

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
  undefined8 local_res18;
  longlong *local_res20;
  longlong *local_a8;
  longlong *local_a0;
  longlong *local_98;
  longlong *local_90;
  longlong *local_88;
  undefined8 local_78;
  longlong *local_70;
  longlong *local_68 [5];
  undefined8 uVar13;
  
  plVar12 = (longlong *)0x0;
  plVar15 = (longlong *)0x0;
  local_res18 = param_3;
  lVar9 = _PyThreadState_UncheckedGet();
  puVar6 = *(undefined8 **)(lVar9 + 0x90);
  do {
    puVar18 = puVar6;
    pcVar1 = (code *)puVar18[1];
    if ((pcVar1 != (code *)0x0) && (pcVar1 != _Py_NoneStruct_exref)) break;
    puVar6 = (undefined8 *)puVar18[3];
  } while ((undefined8 *)puVar18[3] != (undefined8 *)0x0);
  local_88 = (longlong *)*puVar18;
  local_90 = (longlong *)puVar18[2];
  if (local_88 != (longlong *)0x0) {
    *local_88 = *local_88 + 1;
  }
  if (pcVar1 != (code *)0x0) {
    *(longlong *)pcVar1 = *(longlong *)pcVar1 + 1;
  }
  if (local_90 != (longlong *)0x0) {
    *local_90 = *local_90 + 1;
  }
  pcVar2 = *(code **)(*(longlong *)(param_2 + 8) + 0x90);
  if (pcVar2 == (code *)0x0) {
    plVar10 = (longlong *)PyObject_GetAttr(param_2,*(undefined8 *)(PTR_DAT_1801e5048 + 0x4068));
  }
  else {
    plVar10 = (longlong *)(*pcVar2)();
  }
  if (plVar10 == (longlong *)0x0) {
    iVar19 = 0x612;
    iVar8 = 0xfb7e;
  }
  else {
    plVar15 = (longlong *)PyDict_New();
    if (plVar15 == (longlong *)0x0) {
      iVar19 = 0x612;
      iVar8 = 0xfb80;
    }
    else {
      iVar8 = PyDict_SetItem(plVar15,*(undefined8 *)(PTR_DAT_1801e5048 + 0x4798),param_3);
      if (iVar8 < 0) {
        iVar19 = 0x612;
        iVar8 = 0xfb82;
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
        local_70 = plVar12;
        local_68[0] = plVar15;
        plVar11 = (longlong *)
                  FUN_1801bbf50((longlong)plVar10,local_68 + -lVar16,(ulonglong)((int)lVar16 + 1));
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
          iVar19 = 0x612;
          iVar8 = 0xfb96;
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
            iVar19 = 0x613;
            iVar8 = 0xfba3;
          }
          else {
            iVar8 = PyObject_SetItem(plVar12,*(undefined8 *)(PTR_DAT_1801e5048 + 0x4798),local_res18
                                    );
            if (iVar8 < 0) {
              iVar19 = 0x613;
              iVar8 = 0xfba5;
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
                iVar19 = 0x614;
                iVar8 = 0xfbaf;
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
                local_68[2] = (longlong *)0x0;
                local_68[1] = plVar20;
                plVar12 = (longlong *)
                          FUN_1801bbf50((longlong)plVar10,local_68 + (2 - uVar14),uVar14);
                if ((plVar20 != (longlong *)0x0) && (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
                  _Py_Dealloc(plVar20);
                }
                plVar15 = (longlong *)0x0;
                if (plVar12 == (longlong *)0x0) {
                  iVar19 = 0x614;
                  iVar8 = 0xfbc3;
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
                    iVar8 = 0xfbd1;
                  }
                  else {
                    iVar8 = PyDict_SetItem(plVar12,*(undefined8 *)(PTR_DAT_1801e5048 + 0x43f8),
                                           *(undefined8 *)(PTR_DAT_1801e5048 + 0x45b8));
                    if (iVar8 < 0) {
                      iVar8 = 0xfbd3;
                    }
                    else {
                      iVar8 = PyDict_SetItem(plVar12,*(undefined8 *)(PTR_DAT_1801e5048 + 0x3480),
                                             *(undefined8 *)(PTR_DAT_1801e5048 + 0xed8));
                      if (-1 < iVar8) {
                        FUN_1801bc0e0(lVar9,local_88,pcVar1,local_90);
                        return plVar12;
                      }
                      iVar8 = 0xfbd4;
                    }
                  }
                  iVar19 = 0x615;
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
  local_98 = (longlong *)0x0;
  if ((plVar10 != (longlong *)0x0) && (*plVar10 = *plVar10 + -1, *plVar10 == 0)) {
    _Py_Dealloc(plVar10);
  }
  plVar12 = (longlong *)0x0;
  local_res10 = (longlong *)0x0;
  if ((plVar15 != (longlong *)0x0) && (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
    _Py_Dealloc(plVar15);
  }
  local_a0 = (longlong *)0x0;
  puVar3 = *(undefined **)PyExc_Exception_exref;
  puVar4 = *(undefined **)(lVar9 + 0x58);
  if (puVar4 != puVar3) {
    plVar15 = (longlong *)0x0;
    if (puVar4 == (undefined *)0x0) goto LAB_180065725;
    if ((*(uint *)(*(longlong *)(puVar3 + 8) + 0xa8) & 0x4000000) == 0) {
      uVar14 = FUN_1801bdde0(puVar4,puVar3);
      iVar7 = (int)uVar14;
    }
    else {
      uVar13 = FUN_1801bb510(puVar4,(longlong)puVar3);
      iVar7 = (int)uVar13;
    }
    if (iVar7 == 0) goto LAB_180065725;
  }
  FUN_1801c1020("main.Api.save_token",iVar8,iVar19,puVar21);
  uVar13 = FUN_1801bc330(lVar9,&local_98,&local_res10,&local_a0);
  plVar12 = local_res10;
  if ((int)uVar13 < 0) {
    iVar19 = 0x616;
    iVar8 = 0xfbf1;
    plVar15 = local_a0;
    puVar21 = PTR_s_packed__build_temp__main_py_1801cc288;
  }
  else {
    *local_res10 = *local_res10 + 1;
    plVar15 = (longlong *)PyDict_New();
    puVar21 = PTR_s_packed__build_temp__main_py_1801cc288;
    if (plVar15 == (longlong *)0x0) {
      iVar8 = 0xfc01;
      local_res10 = plVar15;
      local_res20 = plVar15;
      local_a8 = plVar15;
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
        iVar8 = 0xfc03;
        local_res20 = (longlong *)0x0;
        local_a8 = (longlong *)0x0;
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
          *local_98 = *local_98 + -1;
          if (*local_98 == 0) {
            _Py_Dealloc();
          }
          *plVar12 = *plVar12 + -1;
          if (*plVar12 == 0) {
            _Py_Dealloc(plVar12);
          }
          *local_a0 = *local_a0 + -1;
          if (*local_a0 == 0) {
            _Py_Dealloc();
          }
          *plVar12 = *plVar12 + -1;
          if (*plVar12 == 0) {
            _Py_Dealloc(plVar12);
          }
          FUN_1801bc0e0(lVar9,local_88,pcVar1,local_90);
          return plVar15;
        }
        local_res10 = (longlong *)0x0;
        iVar8 = 0xfc05;
        local_res20 = (longlong *)0x0;
        local_a8 = (longlong *)0x0;
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
    uVar17 = FUN_1801bc330(lVar16,&local_res10,&local_res20,&local_a8);
    if ((int)uVar17 < 0) {
      local_res10 = *(longlong **)(lVar16 + 0x58);
      local_res20 = *(longlong **)(lVar16 + 0x60);
      local_a8 = *(longlong **)(lVar16 + 0x68);
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
    *(longlong **)(lVar16 + 0x60) = local_res20;
    *(longlong **)(lVar16 + 0x68) = local_a8;
    if ((plVar15 != (longlong *)0x0) && (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
      _Py_Dealloc();
    }
    if ((plVar10 != (longlong *)0x0) && (*plVar10 = *plVar10 + -1, *plVar10 == 0)) {
      _Py_Dealloc(plVar10);
    }
    if ((plVar11 != (longlong *)0x0) && (*plVar11 = *plVar11 + -1, *plVar11 == 0)) {
      _Py_Dealloc(plVar11);
    }
    iVar19 = 0x617;
    plVar15 = local_a0;
  }
LAB_180065725:
  puVar6 = *(undefined8 **)(lVar9 + 0x90);
  plVar10 = (longlong *)*puVar6;
  plVar11 = (longlong *)puVar6[1];
  plVar20 = (longlong *)puVar6[2];
  *puVar6 = local_88;
  puVar6[1] = pcVar1;
  puVar6[2] = local_90;
  if ((plVar10 != (longlong *)0x0) && (*plVar10 = *plVar10 + -1, *plVar10 == 0)) {
    _Py_Dealloc(plVar10);
  }
  if ((plVar11 != (longlong *)0x0) && (*plVar11 = *plVar11 + -1, *plVar11 == 0)) {
    _Py_Dealloc();
  }
  if ((plVar20 != (longlong *)0x0) && (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
    _Py_Dealloc(plVar20);
  }
  if ((local_98 != (longlong *)0x0) && (*local_98 = *local_98 + -1, *local_98 == 0)) {
    _Py_Dealloc();
  }
  if ((plVar12 != (longlong *)0x0) && (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
    _Py_Dealloc(plVar12);
  }
  if ((plVar15 != (longlong *)0x0) && (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
    _Py_Dealloc(plVar15);
  }
  FUN_1801c1020("main.Api.save_token",iVar8,iVar19,puVar21);
  return (longlong *)0x0;
}

