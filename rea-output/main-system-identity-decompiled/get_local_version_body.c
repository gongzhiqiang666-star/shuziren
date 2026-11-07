
/* WARNING: Function: __security_check_cookie replaced with injection: security_check_cookie */

longlong * FUN_18005c5a0(undefined8 param_1,longlong param_2)

{
  code *pcVar1;
  undefined *puVar2;
  undefined *puVar3;
  undefined8 *puVar4;
  int iVar5;
  int iVar6;
  longlong lVar7;
  longlong *plVar8;
  longlong *plVar9;
  longlong lVar10;
  ulonglong uVar12;
  longlong *plVar13;
  longlong *plVar14;
  longlong *plVar15;
  undefined8 *puVar16;
  uint uVar17;
  undefined *puVar18;
  longlong *plVar19;
  longlong *plVar20;
  int iVar21;
  undefined1 auStack_128 [32];
  longlong *local_108;
  longlong *local_100;
  longlong *local_f8;
  code *local_f0;
  longlong *local_e8;
  longlong *local_e0;
  longlong *local_d8;
  longlong *local_d0;
  code *local_c8;
  longlong *local_c0;
  longlong local_b8;
  code *local_b0;
  longlong *local_a8;
  longlong *local_a0 [6];
  longlong *local_70 [4];
  longlong *local_50;
  undefined8 local_48;
  undefined8 local_40;
  ulonglong local_38;
  undefined8 uVar11;
  
  local_38 = DAT_1801e4000 ^ (ulonglong)auStack_128;
  plVar19 = (longlong *)0x0;
  local_a0[3] = (longlong *)0x0;
  plVar20 = (longlong *)0x0;
  local_a0[4] = (longlong *)0x0;
  local_d0 = (longlong *)0x0;
  local_100 = (longlong *)0x0;
  local_b8 = _PyThreadState_UncheckedGet();
  puVar4 = *(undefined8 **)(local_b8 + 0x90);
  do {
    puVar16 = puVar4;
    local_b0 = (code *)puVar16[1];
    if ((local_b0 != (code *)0x0) && (local_b0 != _Py_NoneStruct_exref)) break;
    puVar4 = (undefined8 *)puVar16[3];
  } while ((undefined8 *)puVar16[3] != (undefined8 *)0x0);
  local_a0[2] = (longlong *)*puVar16;
  local_a0[1] = (longlong *)puVar16[2];
  if (local_a0[2] != (longlong *)0x0) {
    *local_a0[2] = *local_a0[2] + 1;
  }
  if (local_b0 != (code *)0x0) {
    *(longlong *)local_b0 = *(longlong *)local_b0 + 1;
  }
  if (local_a0[1] != (longlong *)0x0) {
    *local_a0[1] = *local_a0[1] + 1;
  }
  puVar18 = PTR_DAT_1801e5048;
  if (DAT_1801f05c0 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
    if (DAT_1801f0f00 == (longlong *)0x0) {
      uVar11 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x37e0);
      plVar13 = (longlong *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar11);
      puVar18 = PTR_DAT_1801e5048;
      if ((plVar13 == (longlong *)0x0) &&
         (lVar10 = PyErr_Occurred(), puVar18 = PTR_DAT_1801e5048, lVar10 == 0)) {
        PyErr_Format(*(undefined8 *)PyExc_NameError_exref,"name \'%U\' is not defined",uVar11);
        puVar18 = PTR_DAT_1801e5048;
      }
    }
    else {
      *DAT_1801f0f00 = *DAT_1801f0f00 + 1;
      plVar13 = DAT_1801f0f00;
    }
  }
  else {
    lVar10 = *(longlong *)(PTR_DAT_1801e5048 + 0x37e0);
    plVar13 = (longlong *)
              _PyDict_GetItem_KnownHash
                        (*(longlong *)PTR_DAT_1801e5048,lVar10,*(undefined8 *)(lVar10 + 0x18));
    puVar18 = PTR_DAT_1801e5048;
    DAT_1801f05c0 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
    DAT_1801f0f00 = plVar13;
    if (plVar13 == (longlong *)0x0) {
      lVar7 = PyErr_Occurred();
      if (lVar7 == 0) {
        plVar13 = (longlong *)FUN_1801bb940(lVar10);
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
    iVar6 = 0x585;
    iVar21 = 0xea6a;
    plVar20 = plVar19;
    plVar15 = plVar19;
    puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
  }
  else {
    if (*(code **)(plVar13[1] + 0x90) == (code *)0x0) {
      plVar15 = (longlong *)PyObject_GetAttr(plVar13,*(undefined8 *)(puVar18 + 0x3898));
    }
    else {
      plVar15 = (longlong *)(**(code **)(plVar13[1] + 0x90))();
    }
    if (plVar15 == (longlong *)0x0) {
      iVar6 = 0x585;
      iVar21 = 0xea6c;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
    }
    else {
      *plVar13 = *plVar13 + -1;
      if (*plVar13 == 0) {
        _Py_Dealloc(plVar13);
      }
      if (*(code **)(plVar15[1] + 0x90) == (code *)0x0) {
        plVar14 = (longlong *)PyObject_GetAttr(plVar15,*(undefined8 *)(PTR_DAT_1801e5048 + 0x30a0));
      }
      else {
        plVar14 = (longlong *)(**(code **)(plVar15[1] + 0x90))();
      }
      plVar13 = plVar14;
      if (plVar14 == (longlong *)0x0) {
        iVar6 = 0x585;
        iVar21 = 0xea6f;
        puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
      }
      else {
        *plVar15 = *plVar15 + -1;
        if (*plVar15 == 0) {
          _Py_Dealloc(plVar15);
        }
        pcVar1 = *(code **)(*(longlong *)(param_2 + 8) + 0x90);
        if (pcVar1 == (code *)0x0) {
          plVar15 = (longlong *)
                    PyObject_GetAttr(param_2,*(undefined8 *)(PTR_DAT_1801e5048 + 0x1c28));
        }
        else {
          plVar15 = (longlong *)(*pcVar1)();
        }
        if (plVar15 == (longlong *)0x0) {
          iVar6 = 0x585;
          iVar21 = 0xea72;
          plVar15 = (longlong *)0x0;
          puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
        }
        else {
          local_70[3] = plVar19;
          plVar20 = plVar19;
          uVar17 = 0;
          if (((code *)plVar14[1] == PyMethod_Type_exref) &&
             (plVar20 = (longlong *)plVar14[3], local_70[3] = plVar20, uVar17 = 0,
             local_100 = plVar20, plVar20 != (longlong *)0x0)) {
            plVar13 = (longlong *)plVar14[2];
            *plVar20 = *plVar20 + 1;
            *plVar13 = *plVar13 + 1;
            *plVar14 = *plVar14 + -1;
            if (*plVar14 == 0) {
              _Py_Dealloc(plVar14);
            }
            uVar17 = 1;
            local_70[3] = local_100;
          }
          local_48 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x1f30);
          local_40 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x1f50);
          local_50 = plVar15;
          plVar14 = (longlong *)
                    FUN_1801bbf50((longlong)plVar13,local_70 + (4 - (ulonglong)uVar17),
                                  (ulonglong)(uVar17 + 3));
          if ((plVar20 != (longlong *)0x0) && (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
            _Py_Dealloc(plVar20);
          }
          *plVar15 = *plVar15 + -1;
          local_100 = (longlong *)0x0;
          if (*plVar15 == 0) {
            _Py_Dealloc(plVar15);
          }
          plVar15 = (longlong *)0x0;
          if (plVar14 == (longlong *)0x0) {
            iVar6 = 0x585;
            iVar21 = 0xea87;
            plVar20 = (longlong *)0x0;
            puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
          }
          else {
            *plVar13 = *plVar13 + -1;
            if (*plVar13 == 0) {
              _Py_Dealloc(plVar13);
            }
            local_a0[3] = plVar14;
            plVar20 = (longlong *)PyTuple_New(2);
            if (plVar20 == (longlong *)0x0) {
              iVar6 = 0x586;
              iVar21 = 0xea96;
              plVar13 = (longlong *)0x0;
              puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
            }
            else {
              *plVar14 = *plVar14 + 1;
              puVar18 = PTR_DAT_1801e5048;
              plVar20[3] = (longlong)plVar14;
              plVar13 = *(longlong **)(puVar18 + 0x3c90);
              *plVar13 = *plVar13 + 1;
              plVar20[4] = *(longlong *)(puVar18 + 0x3c90);
              plVar13 = (longlong *)PyDict_New();
              if (plVar13 == (longlong *)0x0) {
                iVar6 = 0x586;
                iVar21 = 0xea9e;
                puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
              }
              else {
                iVar6 = PyDict_SetItem(plVar13,*(undefined8 *)(PTR_DAT_1801e5048 + 0x2518),
                                       *(undefined8 *)(PTR_DAT_1801e5048 + 0x4a60));
                if (iVar6 < 0) {
                  iVar6 = 0x586;
                  iVar21 = 0xeaa0;
                  puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                }
                else {
                  plVar15 = (longlong *)FUN_1801bbe10(DAT_1801ef4b0,plVar20,plVar13);
                  if (plVar15 == (longlong *)0x0) {
                    iVar6 = 0x586;
                    iVar21 = 0xeaa1;
                    puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                  }
                  else {
                    *plVar20 = *plVar20 + -1;
                    if (*plVar20 == 0) {
                      _Py_Dealloc(plVar20);
                    }
                    *plVar13 = *plVar13 + -1;
                    plVar20 = (longlong *)0x0;
                    if (*plVar13 == 0) {
                      _Py_Dealloc(plVar13);
                    }
                    local_d8 = FUN_1801bc150((longlong)plVar15,
                                             *(undefined8 *)(PTR_DAT_1801e5048 + 0x2668));
                    if (local_d8 == (longlong *)0x0) {
                      iVar6 = 0x586;
                      iVar21 = 0xeaa5;
                      plVar13 = (longlong *)0x0;
                      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                    }
                    else {
                      plVar20 = FUN_1801bc150((longlong)plVar15,
                                              *(undefined8 *)(PTR_DAT_1801e5048 + 0x2588));
                      if (plVar20 == (longlong *)0x0) {
                        iVar21 = 0xeaa7;
                      }
                      else {
                        plVar13 = plVar19;
                        plVar14 = plVar19;
                        local_a0[5] = plVar19;
                        local_e8 = plVar20;
                        if (((code *)plVar20[1] == PyMethod_Type_exref) &&
                           (plVar13 = (longlong *)plVar20[3], local_a0[5] = plVar13,
                           local_100 = plVar13, plVar13 != (longlong *)0x0)) {
                          plVar8 = (longlong *)plVar20[2];
                          *plVar13 = *plVar13 + 1;
                          *plVar8 = *plVar8 + 1;
                          *plVar20 = *plVar20 + -1;
                          if (*plVar20 == 0) {
                            _Py_Dealloc();
                          }
                          plVar14 = (longlong *)0x1;
                          local_a0[5] = local_100;
                          local_e8 = plVar8;
                        }
                        plVar20 = local_e8;
                        local_70[0] = (longlong *)0x0;
                        plVar14 = (longlong *)
                                  FUN_1801bbf50((longlong)local_e8,local_70 + -(longlong)plVar14,
                                                (ulonglong)plVar14);
                        if ((plVar13 != (longlong *)0x0) &&
                           (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
                          _Py_Dealloc(plVar13);
                        }
                        local_100 = (longlong *)0x0;
                        if (plVar14 != (longlong *)0x0) {
                          *local_e8 = *local_e8 + -1;
                          if (*local_e8 == 0) {
                            _Py_Dealloc();
                          }
                          *plVar15 = *plVar15 + -1;
                          if (*plVar15 == 0) {
                            _Py_Dealloc(plVar15);
                          }
                          local_e8 = (longlong *)_PyThreadState_UncheckedGet();
                          puVar4 = (undefined8 *)local_e8[0x12];
                          do {
                            puVar16 = puVar4;
                            local_f0 = (code *)puVar16[1];
                            if ((local_f0 != (code *)0x0) && (local_f0 != _Py_NoneStruct_exref))
                            break;
                            puVar4 = (undefined8 *)puVar16[3];
                          } while ((undefined8 *)puVar16[3] != (undefined8 *)0x0);
                          local_c8 = (code *)*puVar16;
                          local_c0 = (longlong *)puVar16[2];
                          if (local_c8 != (code *)0x0) {
                            *(longlong *)local_c8 = *(longlong *)local_c8 + 1;
                          }
                          if (local_f0 != (code *)0x0) {
                            *(longlong *)local_f0 = *(longlong *)local_f0 + 1;
                          }
                          if (local_c0 != (longlong *)0x0) {
                            *local_c0 = *local_c0 + 1;
                          }
                          puVar18 = PTR_DAT_1801e5048;
                          local_a0[4] = plVar14;
                          if (DAT_1801f0848 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18))
                          {
                            if (DAT_1801f0c58 == (longlong *)0x0) {
                              uVar11 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x4e50);
                              plVar20 = (longlong *)
                                        FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),uVar11);
                              puVar18 = PTR_DAT_1801e5048;
                              if ((plVar20 == (longlong *)0x0) &&
                                 (lVar10 = PyErr_Occurred(), puVar18 = PTR_DAT_1801e5048,
                                 lVar10 == 0)) {
                                PyErr_Format(*(undefined8 *)PyExc_NameError_exref,
                                             "name \'%U\' is not defined",uVar11);
                                puVar18 = PTR_DAT_1801e5048;
                              }
                            }
                            else {
                              *DAT_1801f0c58 = *DAT_1801f0c58 + 1;
                              plVar20 = DAT_1801f0c58;
                            }
                          }
                          else {
                            lVar10 = *(longlong *)(PTR_DAT_1801e5048 + 0x4e50);
                            plVar20 = (longlong *)
                                      _PyDict_GetItem_KnownHash
                                                (*(longlong *)PTR_DAT_1801e5048,lVar10,
                                                 *(undefined8 *)(lVar10 + 0x18));
                            puVar18 = PTR_DAT_1801e5048;
                            DAT_1801f0848 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
                            DAT_1801f0c58 = plVar20;
                            if (plVar20 == (longlong *)0x0) {
                              lVar7 = PyErr_Occurred();
                              if (lVar7 == 0) {
                                plVar20 = (longlong *)FUN_1801bb940(lVar10);
                                puVar18 = PTR_DAT_1801e5048;
                              }
                              else {
                                plVar20 = (longlong *)0x0;
                                puVar18 = PTR_DAT_1801e5048;
                              }
                            }
                            else {
                              *plVar20 = *plVar20 + 1;
                            }
                          }
                          plVar8 = plVar19;
                          if (plVar20 == (longlong *)0x0) {
                            iVar6 = 0xead5;
                            plVar13 = plVar19;
                            goto LAB_18005ce19;
                          }
                          if (*(code **)(plVar20[1] + 0x90) == (code *)0x0) {
                            plVar13 = (longlong *)
                                      PyObject_GetAttr(plVar20,*(undefined8 *)(puVar18 + 0x4010));
                          }
                          else {
                            plVar13 = (longlong *)(**(code **)(plVar20[1] + 0x90))();
                          }
                          if (plVar13 == (longlong *)0x0) {
                            *plVar20 = *plVar20 + -1;
                            puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                            iVar6 = 0xead7;
                            local_e0 = (longlong *)0x0;
                            if (*plVar20 == 0) {
                              _Py_Dealloc(plVar20);
                            }
LAB_18005ce25:
                            if ((plVar8 != (longlong *)0x0) &&
                               (*plVar8 = *plVar8 + -1, *plVar8 == 0)) {
                              _Py_Dealloc(plVar8);
                            }
                            local_f8 = (longlong *)0x0;
                            if ((plVar13 != (longlong *)0x0) &&
                               (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
                              _Py_Dealloc(plVar13);
                            }
                            local_100 = (longlong *)0x0;
                            FUN_1801c1020("main.Api.get_local_version",iVar6,0x587,puVar18);
                            uVar11 = FUN_1801bc330((longlong)local_e8,&local_e0,&local_f8,&local_100
                                                  );
                            plVar20 = local_e0;
                            plVar15 = local_f8;
                            plVar13 = local_100;
                            if ((int)uVar11 < 0) {
                              iVar21 = 0xeb15;
                            }
                            else {
                              plVar8 = (longlong *)PyTuple_Pack(3,local_e0,local_f8,local_100);
                              plVar14 = local_d8;
                              if (plVar8 == (longlong *)0x0) {
                                iVar21 = 0xeb19;
                              }
                              else {
                                plVar9 = (longlong *)FUN_1801bbe10((longlong)local_d8,plVar8,0);
                                *plVar14 = *plVar14 + -1;
                                if (*plVar14 == 0) {
                                  _Py_Dealloc(plVar14);
                                }
                                *plVar8 = *plVar8 + -1;
                                local_d8 = (longlong *)0x0;
                                if (*plVar8 == 0) {
                                  _Py_Dealloc(plVar8);
                                }
                                if (plVar9 == (longlong *)0x0) {
                                  iVar21 = 0xeb1e;
                                }
                                else {
                                  iVar6 = FUN_1801c28c0((undefined *)plVar9);
                                  *plVar9 = *plVar9 + -1;
                                  if (*plVar9 == 0) {
                                    _Py_Dealloc(plVar9);
                                  }
                                  if (iVar6 < 0) {
                                    iVar21 = 0xeb22;
                                  }
                                  else {
                                    if (iVar6 != 0) {
                                      if ((plVar20 != (longlong *)0x0) &&
                                         (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
                                        _Py_Dealloc(plVar20);
                                      }
                                      if ((plVar15 != (longlong *)0x0) &&
                                         (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
                                        _Py_Dealloc(plVar15);
                                      }
                                      local_f8 = (longlong *)0x0;
                                      if ((plVar13 != (longlong *)0x0) &&
                                         (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
                                        _Py_Dealloc(plVar13);
                                      }
                                      local_100 = (longlong *)0x0;
                                      FUN_1801bc0e0((longlong)local_e8,local_c8,local_f0,local_c0);
                                      plVar8 = plVar19;
                                      goto LAB_18005d07c;
                                    }
                                    lVar10 = PyThreadState_Get();
                                    FUN_1801bb760(lVar10,plVar20,plVar15,plVar13);
                                    plVar20 = (longlong *)0x0;
                                    local_100 = (longlong *)0x0;
                                    plVar15 = (longlong *)0x0;
                                    iVar21 = 0xeb2a;
                                  }
                                }
                              }
                            }
                            puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                            iVar6 = 0x586;
                            FUN_1801bc0e0((longlong)local_e8,local_c8,local_f0,local_c0);
                            plVar13 = (longlong *)0x0;
                          }
                          else {
                            *plVar20 = *plVar20 + -1;
                            if (*plVar20 == 0) {
                              _Py_Dealloc(plVar20);
                            }
                            plVar20 = plVar19;
                            plVar15 = plVar13;
                            if (((code *)plVar13[1] == PyMethod_Type_exref) &&
                               (plVar20 = (longlong *)plVar13[3], plVar8 = (longlong *)0x0,
                               plVar20 != (longlong *)0x0)) {
                              plVar15 = (longlong *)plVar13[2];
                              *plVar20 = *plVar20 + 1;
                              *plVar15 = *plVar15 + 1;
                              *plVar13 = *plVar13 + -1;
                              if (*plVar13 == 0) {
                                _Py_Dealloc(plVar13);
                              }
                              plVar8 = (longlong *)0x1;
                            }
                            local_a8 = plVar20;
                            local_a0[0] = plVar14;
                            plVar8 = (longlong *)
                                     FUN_1801bbf50((longlong)plVar15,local_a0 + -(longlong)plVar8,
                                                   (ulonglong)((int)plVar8 + 1));
                            if ((plVar20 != (longlong *)0x0) &&
                               (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
                              _Py_Dealloc(plVar20);
                            }
                            if (plVar8 == (longlong *)0x0) {
                              iVar6 = 0xeaec;
                              plVar13 = plVar15;
LAB_18005ce19:
                              local_e0 = (longlong *)0x0;
                              puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                              goto LAB_18005ce25;
                            }
                            *plVar15 = *plVar15 + -1;
                            if (*plVar15 == 0) {
                              _Py_Dealloc(plVar15);
                            }
                            local_100 = (longlong *)0x0;
                            plVar13 = (longlong *)0x0;
                            iVar6 = FUN_1801c28c0((undefined *)plVar8);
                            if (iVar6 < 0) {
                              iVar6 = 0xeaf0;
                              plVar13 = plVar19;
                              goto LAB_18005ce19;
                            }
                            if (iVar6 == 0) {
                              *plVar8 = *plVar8 + -1;
                              if (*plVar8 == 0) {
                                _Py_Dealloc(plVar8);
                              }
                              plVar8 = (longlong *)PyDict_New();
                              if (plVar8 == (longlong *)0x0) {
                                iVar6 = 0xeaf9;
                                plVar8 = (longlong *)0x0;
                                goto LAB_18005ce19;
                              }
                              lVar10 = *plVar8;
                            }
                            else {
                              lVar10 = *plVar8;
                            }
                            *plVar8 = lVar10;
                            if (lVar10 == 0) {
                              _Py_Dealloc(plVar8);
                            }
                            local_f8 = (longlong *)0x0;
                            if ((local_c8 != (code *)0x0) &&
                               (*(longlong *)local_c8 = *(longlong *)local_c8 + -1,
                               *(longlong *)local_c8 == 0)) {
                              _Py_Dealloc();
                            }
                            if ((local_f0 != (code *)0x0) &&
                               (*(longlong *)local_f0 = *(longlong *)local_f0 + -1,
                               *(longlong *)local_f0 == 0)) {
                              _Py_Dealloc();
                            }
                            local_d0 = plVar8;
                            if ((local_c0 != (longlong *)0x0) &&
                               (*local_c0 = *local_c0 + -1, *local_c0 == 0)) {
                              _Py_Dealloc();
                              local_d0 = plVar8;
                            }
LAB_18005d07c:
                            plVar14 = local_d8;
                            plVar20 = (longlong *)0x0;
                            plVar15 = plVar20;
                            plVar13 = plVar20;
                            if (local_d8 != (longlong *)0x0) {
                              plVar9 = (longlong *)
                                       FUN_1801bbe10((longlong)local_d8,
                                                     *(undefined8 *)(PTR_DAT_1801e5048 + 0x4fd0),0);
                              *plVar14 = *plVar14 + -1;
                              if (*plVar14 == 0) {
                                _Py_Dealloc(plVar14);
                              }
                              if (plVar9 == (longlong *)0x0) {
                                iVar6 = 0x586;
                                iVar21 = 0xeb44;
                                puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                                goto LAB_18005d1fc;
                              }
                              *plVar9 = *plVar9 + -1;
                              if (*plVar9 == 0) {
                                _Py_Dealloc(plVar9);
                              }
                            }
                            plVar14 = (longlong *)PyDict_New();
                            local_100 = plVar14;
                            if (plVar14 == (longlong *)0x0) {
                              iVar6 = 0x589;
                              iVar21 = 0xeb63;
                              puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                            }
                            else {
                              iVar6 = PyDict_SetItem(plVar14,*(undefined8 *)
                                                              (PTR_DAT_1801e5048 + 0x43f8),
                                                     *(undefined8 *)(PTR_DAT_1801e5048 + 0x45b8));
                              if (iVar6 < 0) {
                                iVar6 = 0x589;
                                iVar21 = 0xeb65;
                                puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                              }
                              else if (plVar8 == (longlong *)0x0) {
                                PyErr_Format(*(undefined8 *)PyExc_UnboundLocalError_exref,
                                             "local variable \'%s\' referenced before assignment",
                                             "config");
                                iVar6 = 0x58a;
                                iVar21 = 0xeb6e;
                                puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                              }
                              else {
                                if (*(code **)(plVar8[1] + 0x90) == (code *)0x0) {
                                  plVar13 = (longlong *)
                                            PyObject_GetAttr(plVar8,*(undefined8 *)
                                                                     (PTR_DAT_1801e5048 + 0x2a38));
                                }
                                else {
                                  plVar13 = (longlong *)(**(code **)(plVar8[1] + 0x90))();
                                }
                                if (plVar13 == (longlong *)0x0) {
                                  iVar6 = 0x58a;
                                  iVar21 = 0xeb6f;
                                  puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                                }
                                else {
                                  plVar15 = (longlong *)
                                            FUN_1801bbe10((longlong)plVar13,
                                                          *(undefined8 *)
                                                           (PTR_DAT_1801e5048 + 0x50f0),0);
                                  if (plVar15 == (longlong *)0x0) {
                                    iVar21 = 0xeb71;
                                    plVar20 = plVar19;
                                    puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                                  }
                                  else {
                                    *plVar13 = *plVar13 + -1;
                                    if (*plVar13 == 0) {
                                      _Py_Dealloc(plVar13);
                                    }
                                    if ((code *)plVar15[1] == PyUnicode_Type_exref) {
                                      *plVar15 = *plVar15 + 1;
                                      plVar13 = plVar15;
LAB_18005d2ca:
                                      *plVar15 = *plVar15 + -1;
                                      if (*plVar15 == 0) {
                                        _Py_Dealloc(plVar15);
                                      }
                                      if (*(code **)(plVar13[1] + 0x90) == (code *)0x0) {
                                        plVar20 = (longlong *)
                                                  PyObject_GetAttr(plVar13,*(undefined8 *)
                                                                            (PTR_DAT_1801e5048 +
                                                                            0x44a8));
                                      }
                                      else {
                                        plVar20 = (longlong *)(**(code **)(plVar13[1] + 0x90))();
                                      }
                                      if (plVar20 == (longlong *)0x0) {
                                        iVar21 = 0xeb77;
                                        plVar20 = plVar19;
                                        puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                                      }
                                      else {
                                        *plVar13 = *plVar13 + -1;
                                        if (*plVar13 == 0) {
                                          _Py_Dealloc(plVar13);
                                        }
                                        plVar13 = plVar19;
                                        plVar9 = plVar19;
                                        plVar15 = plVar20;
                                        if (((code *)plVar20[1] == PyMethod_Type_exref) &&
                                           (plVar13 = (longlong *)plVar20[3],
                                           plVar13 != (longlong *)0x0)) {
                                          plVar15 = (longlong *)plVar20[2];
                                          *plVar13 = *plVar13 + 1;
                                          *plVar15 = *plVar15 + 1;
                                          *plVar20 = *plVar20 + -1;
                                          if (*plVar20 == 0) {
                                            _Py_Dealloc(plVar20);
                                          }
                                          plVar9 = (longlong *)0x1;
                                        }
                                        local_70[2] = (longlong *)0x0;
                                        local_70[1] = plVar13;
                                        plVar20 = (longlong *)
                                                  FUN_1801bbf50((longlong)plVar15,
                                                                local_70 + (2 - (longlong)plVar9),
                                                                (ulonglong)plVar9);
                                        if ((plVar13 != (longlong *)0x0) &&
                                           (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
                                          _Py_Dealloc(plVar13);
                                        }
                                        plVar13 = (longlong *)0x0;
                                        if (plVar20 == (longlong *)0x0) {
                                          iVar21 = 0xeb8c;
                                          plVar13 = plVar19;
                                          puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                                          if (plVar15 != (longlong *)0x0) goto LAB_18005d3f4;
                                        }
                                        else {
                                          *plVar15 = *plVar15 + -1;
                                          if (*plVar15 == 0) {
                                            _Py_Dealloc(plVar15);
                                          }
                                          iVar6 = FUN_1801c28c0((undefined *)plVar20);
                                          if (-1 < iVar6) {
                                            if (iVar6 == 0) {
                                              *plVar20 = *plVar20 + -1;
                                              if (*plVar20 == 0) {
                                                _Py_Dealloc(plVar20);
                                              }
                                              puVar18 = PTR_DAT_1801e5048;
                                              **(longlong **)(PTR_DAT_1801e5048 + 0x4a80) =
                                                   **(longlong **)(PTR_DAT_1801e5048 + 0x4a80) + 1;
                                              plVar15 = *(longlong **)(puVar18 + 0x4a80);
                                            }
                                            else {
                                              lVar10 = *plVar20;
                                              *plVar20 = lVar10;
                                              puVar18 = PTR_DAT_1801e5048;
                                              plVar15 = plVar20;
                                              if (lVar10 == 0) {
                                                _Py_Dealloc(plVar20);
                                                puVar18 = PTR_DAT_1801e5048;
                                              }
                                            }
                                            plVar20 = (longlong *)0x0;
                                            iVar6 = PyDict_SetItem(plVar14,*(undefined8 *)
                                                                            (puVar18 + 0x4b40),
                                                                   plVar15);
                                            if (-1 < iVar6) {
                                              *plVar15 = *plVar15 + -1;
                                              if (*plVar15 == 0) {
                                                _Py_Dealloc(plVar15);
                                              }
                                              FUN_1801bc0e0(local_b8,local_a0[2],local_b0,
                                                            local_a0[1]);
                                              goto LAB_18005d919;
                                            }
                                            iVar6 = 0x589;
                                            iVar21 = 0xeb9c;
                                            puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                                            goto LAB_18005d1fc;
                                          }
                                          iVar21 = 0xeb90;
                                          plVar13 = plVar19;
                                          puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                                        }
                                      }
                                    }
                                    else {
                                      plVar13 = (longlong *)PyObject_Str(plVar15);
                                      if (plVar13 != (longlong *)0x0) goto LAB_18005d2ca;
                                      iVar21 = 0xeb74;
                                      plVar20 = plVar19;
LAB_18005d3f4:
                                      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                                      *plVar15 = *plVar15 + -1;
                                      if (*plVar15 == 0) {
                                        _Py_Dealloc(plVar15);
                                      }
                                    }
                                  }
                                  iVar6 = 0x58a;
                                  plVar15 = local_f8;
                                }
                              }
                            }
                          }
                          goto LAB_18005d1fc;
                        }
                        iVar21 = 0xeabb;
                      }
                      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
                      iVar6 = 0x586;
                      *local_d8 = *local_d8 + -1;
                      plVar13 = (longlong *)0x0;
                      if (*local_d8 == 0) {
                        _Py_Dealloc();
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
LAB_18005d1fc:
  if ((plVar20 != (longlong *)0x0) && (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
    _Py_Dealloc(plVar20);
  }
  local_e0 = (longlong *)0x0;
  if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
    _Py_Dealloc(plVar13);
  }
  if ((plVar15 != (longlong *)0x0) && (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
    _Py_Dealloc(plVar15);
  }
  local_f8 = (longlong *)0x0;
  if ((local_100 != (longlong *)0x0) && (*local_100 = *local_100 + -1, *local_100 == 0)) {
    _Py_Dealloc();
  }
  lVar10 = local_b8;
  local_100 = (longlong *)0x0;
  puVar2 = *(undefined **)PyExc_Exception_exref;
  puVar3 = *(undefined **)(local_b8 + 0x58);
  if (puVar3 == puVar2) {
LAB_18005d4d4:
    FUN_1801c1020("main.Api.get_local_version",iVar21,iVar6,puVar18);
    uVar11 = FUN_1801bc330(lVar10,&local_100,&local_f8,&local_e0);
    plVar20 = local_f8;
    if ((int)uVar11 < 0) {
      iVar6 = 0x58c;
      iVar21 = 0xebbb;
      plVar13 = local_100;
      puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
    }
    else {
      lVar7 = *local_f8;
      *local_f8 = lVar7 + 1;
      if ((code *)local_f8[1] == PyUnicode_Type_exref) {
        *local_f8 = lVar7 + 2;
        plVar14 = local_f8;
      }
      else {
        plVar14 = (longlong *)PyObject_Str(local_f8);
      }
      if (plVar14 == (longlong *)0x0) {
        iVar6 = 0x58d;
        iVar21 = 0xebca;
LAB_18005d635:
        puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
        local_f8 = (longlong *)0x0;
        local_f0 = (code *)0x0;
        local_d8 = (longlong *)0x0;
        plVar15 = (longlong *)_PyThreadState_UncheckedGet();
      }
      else {
        plVar13 = (longlong *)PyUnicode_Concat(*(undefined8 *)(PTR_DAT_1801e5048 + 0x1068),plVar14);
        if (plVar13 == (longlong *)0x0) {
          iVar6 = 0x58d;
          iVar21 = 0xebcc;
LAB_18005d6b3:
          puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
          local_f8 = (longlong *)0x0;
          local_f0 = (code *)0x0;
          local_d8 = (longlong *)0x0;
          local_e8 = (longlong *)_PyThreadState_UncheckedGet();
          *plVar14 = *plVar14 + -1;
          if (*plVar14 == 0) {
            _Py_Dealloc(plVar14);
          }
          plVar15 = local_e8;
          if (plVar13 == (longlong *)0x0) goto LAB_18005d6fd;
        }
        else {
          *plVar14 = *plVar14 + -1;
          if (*plVar14 == 0) {
            _Py_Dealloc(plVar14);
          }
          local_a8 = (longlong *)0x0;
          local_a0[0] = plVar13;
          plVar15 = (longlong *)FUN_1801bbf50(DAT_1801f1718,local_a0,0x8000000000000001);
          puVar18 = PTR_s_packed__build_temp__main_py_1801cc288;
          if (plVar15 != (longlong *)0x0) {
            *plVar13 = *plVar13 + -1;
            if (*plVar13 == 0) {
              _Py_Dealloc(plVar13);
            }
            *plVar15 = *plVar15 + -1;
            if (*plVar15 == 0) {
              _Py_Dealloc(plVar15);
            }
            plVar14 = (longlong *)PyDict_New();
            if (plVar14 == (longlong *)0x0) {
              iVar6 = 0x58e;
              iVar21 = 0xebdc;
              goto LAB_18005d635;
            }
            if ((code *)plVar20[1] == PyUnicode_Type_exref) {
              *plVar20 = *plVar20 + 1;
              plVar13 = plVar20;
            }
            else {
              plVar13 = (longlong *)PyObject_Str(plVar20);
            }
            if (plVar13 == (longlong *)0x0) {
              iVar21 = 0xebde;
            }
            else {
              iVar6 = PyDict_SetItem(plVar14,*(undefined8 *)(PTR_DAT_1801e5048 + 0x25f0),plVar13);
              if (-1 < iVar6) {
                *plVar13 = *plVar13 + -1;
                if (*plVar13 == 0) {
                  _Py_Dealloc(plVar13);
                }
                *local_e0 = *local_e0 + -1;
                if (*local_e0 == 0) {
                  _Py_Dealloc();
                }
                *plVar20 = *plVar20 + -1;
                if (*plVar20 == 0) {
                  _Py_Dealloc(plVar20);
                }
                *local_100 = *local_100 + -1;
                if (*local_100 == 0) {
                  _Py_Dealloc();
                }
                *plVar20 = *plVar20 + -1;
                if (*plVar20 == 0) {
                  _Py_Dealloc(plVar20);
                }
                FUN_1801bc0e0(lVar10,local_a0[2],local_b0,local_a0[1]);
                plVar8 = local_d0;
                goto LAB_18005d919;
              }
              iVar21 = 0xebe0;
            }
            iVar6 = 0x58e;
            goto LAB_18005d6b3;
          }
          iVar6 = 0x58d;
          iVar21 = 0xebcf;
          local_f8 = (longlong *)0x0;
          local_f0 = (code *)0x0;
          local_d8 = (longlong *)0x0;
          plVar15 = (longlong *)_PyThreadState_UncheckedGet();
        }
        *plVar13 = *plVar13 + -1;
        if (*plVar13 == 0) {
          _Py_Dealloc(plVar13);
        }
      }
LAB_18005d6fd:
      puVar4 = (undefined8 *)plVar15[0x12];
      local_108 = (longlong *)*puVar4;
      local_a8 = (longlong *)puVar4[1];
      local_e8 = (longlong *)puVar4[2];
      *puVar4 = 0;
      puVar4[1] = 0;
      puVar4[2] = 0;
      uVar11 = FUN_1801bc330((longlong)plVar15,&local_f8,&local_f0,&local_d8);
      if ((int)uVar11 < 0) {
        local_c8 = (code *)plVar15[0xc];
        plVar13 = (longlong *)plVar15[0xb];
        local_c0 = (longlong *)plVar15[0xd];
        plVar15[0xb] = 0;
        plVar15[0xc] = 0;
        plVar15[0xd] = 0;
      }
      else {
        local_c0 = local_d8;
        local_c8 = local_f0;
        plVar13 = local_f8;
      }
      *plVar20 = *plVar20 + -1;
      if (*plVar20 == 0) {
        _Py_Dealloc(plVar20);
      }
      FUN_1801bc0e0((longlong)plVar15,local_108,local_a8,local_e8);
      FUN_1801bb760((longlong)plVar15,plVar13,local_c8,local_c0);
      plVar13 = local_100;
      lVar10 = local_b8;
    }
  }
  else {
    plVar20 = plVar19;
    plVar13 = plVar19;
    if (puVar3 != (undefined *)0x0) {
      if ((*(uint *)(*(longlong *)(puVar2 + 8) + 0xa8) & 0x4000000) == 0) {
        uVar12 = FUN_1801bdde0(puVar3,puVar2);
        iVar5 = (int)uVar12;
      }
      else {
        uVar11 = FUN_1801bb510(puVar3,(longlong)puVar2);
        iVar5 = (int)uVar11;
      }
      if (iVar5 != 0) goto LAB_18005d4d4;
    }
  }
  puVar4 = *(undefined8 **)(lVar10 + 0x90);
  plVar15 = (longlong *)*puVar4;
  local_108 = (longlong *)puVar4[2];
  plVar14 = (longlong *)puVar4[1];
  *puVar4 = local_a0[2];
  puVar4[1] = local_b0;
  puVar4[2] = local_a0[1];
  if ((plVar15 != (longlong *)0x0) && (*plVar15 = *plVar15 + -1, *plVar15 == 0)) {
    _Py_Dealloc(plVar15);
  }
  if ((plVar14 != (longlong *)0x0) && (*plVar14 = *plVar14 + -1, *plVar14 == 0)) {
    _Py_Dealloc(plVar14);
  }
  if ((local_108 != (longlong *)0x0) && (*local_108 = *local_108 + -1, *local_108 == 0)) {
    _Py_Dealloc();
  }
  if ((local_e0 != (longlong *)0x0) && (*local_e0 = *local_e0 + -1, *local_e0 == 0)) {
    _Py_Dealloc();
  }
  if ((plVar20 != (longlong *)0x0) && (*plVar20 = *plVar20 + -1, *plVar20 == 0)) {
    _Py_Dealloc(plVar20);
  }
  if ((plVar13 != (longlong *)0x0) && (*plVar13 = *plVar13 + -1, *plVar13 == 0)) {
    _Py_Dealloc(plVar13);
  }
  FUN_1801c1020("main.Api.get_local_version",iVar21,iVar6,puVar18);
  plVar14 = plVar19;
  plVar8 = local_d0;
LAB_18005d919:
  if ((local_a0[3] != (longlong *)0x0) && (*local_a0[3] = *local_a0[3] + -1, *local_a0[3] == 0)) {
    _Py_Dealloc();
  }
  if ((local_a0[4] != (longlong *)0x0) && (*local_a0[4] = *local_a0[4] + -1, *local_a0[4] == 0)) {
    _Py_Dealloc();
  }
  if ((plVar8 != (longlong *)0x0) && (*plVar8 = *plVar8 + -1, *plVar8 == 0)) {
    _Py_Dealloc(plVar8);
  }
  return plVar14;
}

