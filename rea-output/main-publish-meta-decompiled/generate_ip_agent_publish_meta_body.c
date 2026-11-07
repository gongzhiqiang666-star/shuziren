
/* WARNING: Function: __security_check_cookie replaced with injection: security_check_cookie */

undefined *
FUN_180142a40(undefined8 param_1,longlong *param_2,undefined *param_3,undefined *param_4)

{
  undefined *puVar1;
  undefined *puVar2;
  undefined8 uVar3;
  undefined8 *puVar4;
  uint uVar5;
  int iVar6;
  int iVar7;
  code *pcVar8;
  code *pcVar9;
  code *pcVar10;
  code *pcVar11;
  longlong *plVar12;
  code *pcVar13;
  ulonglong uVar15;
  longlong lVar16;
  code *pcVar17;
  undefined8 uVar18;
  undefined8 *puVar19;
  longlong lVar20;
  int iVar21;
  longlong *plVar22;
  undefined *puVar23;
  code *pcVar24;
  code *pcVar25;
  longlong *plVar26;
  undefined1 auStack_1a8 [32];
  code *local_188;
  code *local_180;
  code *local_178;
  code *local_170;
  code *local_168;
  code *local_160;
  code *local_158;
  code *local_150;
  code *local_148;
  longlong *local_140;
  longlong local_138;
  code *local_130;
  code *local_128;
  longlong *local_120;
  code *local_118;
  longlong *local_110;
  longlong *local_108;
  code *local_100;
  longlong *local_f8;
  longlong *local_f0 [4];
  undefined8 local_d0;
  longlong *local_c8;
  undefined8 local_c0;
  longlong *local_b8;
  undefined8 local_b0;
  longlong *local_a8;
  undefined8 local_a0;
  longlong *local_98;
  code *local_90;
  longlong *local_88;
  code *local_80;
  longlong *local_78;
  code *local_70;
  longlong *local_68;
  longlong *local_60;
  code *local_58 [2];
  ulonglong local_48;
  undefined8 uVar14;
  
  local_48 = DAT_1801e4000 ^ (ulonglong)auStack_1a8;
  pcVar17 = (code *)0x0;
  pcVar25 = (code *)0x0;
  pcVar11 = (code *)0x0;
  pcVar24 = (code *)0x0;
  plVar12 = (longlong *)0x0;
  plVar26 = (longlong *)0x0;
  local_178 = (code *)0x0;
  local_130 = (code *)0x0;
  local_150 = (code *)0x0;
  local_128 = (code *)0x0;
  local_158 = (code *)0x0;
  local_160 = (code *)param_4;
  local_148 = (code *)param_3;
  local_140 = param_2;
  local_138 = _PyThreadState_UncheckedGet();
  puVar4 = *(undefined8 **)(local_138 + 0x90);
  do {
    puVar19 = puVar4;
    local_118 = (code *)puVar19[1];
    if ((local_118 != (code *)0x0) && (local_118 != _Py_NoneStruct_exref)) break;
    puVar4 = (undefined8 *)puVar19[3];
  } while ((undefined8 *)puVar19[3] != (undefined8 *)0x0);
  local_110 = (longlong *)*puVar19;
  local_120 = (longlong *)puVar19[2];
  if (local_110 != (longlong *)0x0) {
    *local_110 = *local_110 + 1;
  }
  if (local_118 != (code *)0x0) {
    *(longlong *)local_118 = *(longlong *)local_118 + 1;
  }
  if (local_120 != (longlong *)0x0) {
    *local_120 = *local_120 + 1;
  }
  if (*(code **)(param_2[1] + 0x90) == (code *)0x0) {
    pcVar8 = (code *)PyObject_GetAttr(param_2);
  }
  else {
    pcVar8 = (code *)(**(code **)(param_2[1] + 0x90))();
  }
  pcVar10 = pcVar17;
  pcVar13 = (code *)0x0;
  local_170 = pcVar8;
  if (pcVar8 == (code *)0x0) {
    iVar21 = 0x13b7;
    iVar7 = 0x29642;
    pcVar24 = pcVar11;
    plVar26 = plVar12;
  }
  else {
    plVar22 = (longlong *)0x0;
    lVar20 = 0;
    if ((*(code **)(pcVar8 + 8) == PyMethod_Type_exref) &&
       (plVar22 = *(longlong **)(pcVar8 + 0x18), plVar22 != (longlong *)0x0)) {
      local_170 = *(code **)(pcVar8 + 0x10);
      *plVar22 = *plVar22 + 1;
      *(longlong *)local_170 = *(longlong *)local_170 + 1;
      *(longlong *)pcVar8 = *(longlong *)pcVar8 + -1;
      if (*(longlong *)pcVar8 == 0) {
        _Py_Dealloc();
      }
      lVar20 = 1;
    }
    pcVar8 = local_170;
    local_100 = local_148;
    local_108 = plVar22;
    pcVar9 = (code *)FUN_1801bbf50((longlong)local_170,&local_100 + -lVar20,
                                   (ulonglong)((int)lVar20 + 1));
    local_168 = pcVar9;
    local_158 = pcVar9;
    if ((plVar22 != (longlong *)0x0) && (*plVar22 = *plVar22 + -1, *plVar22 == 0)) {
      _Py_Dealloc(plVar22);
    }
    if (pcVar9 == (code *)0x0) {
      iVar21 = 0x13b7;
      iVar7 = 0x29656;
      pcVar24 = pcVar11;
      plVar26 = plVar12;
    }
    else {
      *(longlong *)pcVar8 = *(longlong *)pcVar8 + -1;
      if (*(longlong *)pcVar8 == 0) {
        _Py_Dealloc(pcVar8);
      }
      local_158 = (code *)0x0;
      local_170 = (code *)0x0;
      uVar5 = (uint)(pcVar9 == _Py_TrueStruct_exref);
      if ((pcVar9 != _Py_FalseStruct_exref && pcVar9 != _Py_NoneStruct_exref) &&
          pcVar9 != _Py_TrueStruct_exref) {
        uVar5 = PyObject_IsTrue(pcVar9);
      }
      pcVar10 = local_160;
      pcVar13 = pcVar9;
      if ((int)uVar5 < 0) {
        iVar21 = 0x13b8;
        iVar7 = 0x29664;
        pcVar24 = pcVar11;
        pcVar10 = pcVar17;
        plVar26 = plVar12;
      }
      else if (uVar5 == 0) {
        local_158 = (code *)PyDict_New();
        if (local_158 == (code *)0x0) {
          iVar21 = 0x13b9;
          iVar7 = 0x29670;
          pcVar10 = pcVar25;
        }
        else {
          iVar7 = PyDict_SetItem(local_158,*(undefined8 *)(PTR_DAT_1801e5048 + 0x25f0),
                                 *(undefined8 *)(PTR_DAT_1801e5048 + 0xb08));
          pcVar17 = local_158;
          if (-1 < iVar7) {
LAB_180144363:
            local_158 = pcVar17;
            FUN_1801bc0e0(local_138,local_110,local_118,local_120);
            pcVar24 = local_158;
            goto LAB_18014437e;
          }
          iVar21 = 0x13b9;
          iVar7 = 0x29672;
          pcVar10 = pcVar25;
        }
      }
      else {
        iVar7 = FUN_1801c28c0(local_160);
        if (iVar7 < 0) {
          iVar21 = 0x13bc;
          iVar7 = 0x29687;
          pcVar10 = pcVar25;
        }
        else {
          if (iVar7 == 0) {
            pcVar10 = (code *)PyDict_New();
            if (pcVar10 == (code *)0x0) {
              iVar21 = 0x13bc;
              iVar7 = 0x2968e;
              pcVar24 = (code *)0x0;
              pcVar10 = pcVar25;
              goto LAB_180143e91;
            }
            lVar20 = *(longlong *)pcVar10;
            *(longlong *)pcVar10 = lVar20;
            if (lVar20 == 0) {
              _Py_Dealloc(pcVar10);
            }
          }
          else {
            *(longlong *)pcVar10 = *(longlong *)pcVar10 + 1;
          }
          if (pcVar10 == _Py_NoneStruct_exref) {
            PyErr_Format(*(undefined8 *)PyExc_AttributeError_exref,
                         "\'NoneType\' object has no attribute \'%.30s\'",&DAT_1801c5a94);
            iVar21 = 0x13bc;
            iVar7 = 0x29696;
            pcVar24 = (code *)0x0;
          }
          else {
            pcVar11 = (code *)FUN_1801bcd40(pcVar10,*(undefined8 *)(PTR_DAT_1801e5048 + 0x4098),
                                            (longlong *)_Py_NoneStruct_exref);
            pcVar24 = pcVar11;
            if (pcVar11 == (code *)0x0) {
              iVar21 = 0x13bc;
              iVar7 = 0x29698;
            }
            else {
              *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1;
              if (*(longlong *)pcVar10 == 0) {
                _Py_Dealloc(pcVar10);
              }
              pcVar10 = (code *)0x0;
              iVar7 = FUN_1801c28c0(pcVar11);
              if (iVar7 < 0) {
                iVar21 = 0x13bc;
                iVar7 = 0x2969b;
              }
              else {
                lVar20 = *(longlong *)pcVar11;
                if (iVar7 == 0) {
                  *(longlong *)pcVar11 = lVar20 + -1;
                  if (lVar20 + -1 == 0) {
                    _Py_Dealloc(pcVar11);
                  }
                  pcVar24 = (code *)0x0;
                  if (*(code **)(*(longlong *)(pcVar9 + 8) + 0x90) == (code *)0x0) {
                    pcVar10 = (code *)PyObject_GetAttr(pcVar9);
                  }
                  else {
                    pcVar10 = (code *)(**(code **)(*(longlong *)(pcVar9 + 8) + 0x90))();
                  }
                  if (pcVar10 == (code *)0x0) {
                    iVar21 = 0x13bd;
                    iVar7 = 0x296ac;
                  }
                  else {
                    plVar12 = (longlong *)0x0;
                    lVar20 = 0;
                    if ((*(code **)(pcVar10 + 8) == PyMethod_Type_exref) &&
                       (plVar12 = *(longlong **)(pcVar10 + 0x18), plVar12 != (longlong *)0x0)) {
                      pcVar24 = *(code **)(pcVar10 + 0x10);
                      *plVar12 = *plVar12 + 1;
                      *(longlong *)pcVar24 = *(longlong *)pcVar24 + 1;
                      *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1;
                      if (*(longlong *)pcVar10 == 0) {
                        _Py_Dealloc();
                      }
                      lVar20 = 1;
                      pcVar10 = pcVar24;
                    }
                    local_f0[0] = *(longlong **)(PTR_DAT_1801e5048 + 0x3f20);
                    local_f8 = plVar12;
                    pcVar24 = (code *)FUN_1801bbf50((longlong)pcVar10,local_f0 + -lVar20,
                                                    (ulonglong)((int)lVar20 + 1));
                    if ((plVar12 != (longlong *)0x0) && (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
                      _Py_Dealloc(plVar12);
                    }
                    if (pcVar24 == (code *)0x0) {
                      iVar21 = 0x13bd;
                      iVar7 = 0x296c0;
                    }
                    else {
                      *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1;
                      if (*(longlong *)pcVar10 == 0) {
                        _Py_Dealloc(pcVar10);
                      }
                      pcVar10 = (code *)0x0;
                      iVar7 = FUN_1801c28c0(pcVar24);
                      if (iVar7 < 0) {
                        iVar21 = 0x13bd;
                        iVar7 = 0x296c4;
                      }
                      else {
                        pcVar11 = pcVar24;
                        if (iVar7 != 0) {
LAB_180143045:
                          lVar20 = *(longlong *)pcVar11;
                          *(longlong *)pcVar11 = lVar20;
                          local_170 = pcVar11;
                          if (lVar20 == 0) {
                            _Py_Dealloc(pcVar11);
                          }
                          goto LAB_18014307c;
                        }
                        *(longlong *)pcVar24 = *(longlong *)pcVar24 + -1;
                        if (*(longlong *)pcVar24 == 0) {
                          _Py_Dealloc(pcVar24);
                        }
                        pcVar24 = (code *)0x0;
                        if (*(code **)(*(longlong *)(pcVar9 + 8) + 0x90) == (code *)0x0) {
                          pcVar10 = (code *)PyObject_GetAttr(pcVar9);
                        }
                        else {
                          pcVar10 = (code *)(**(code **)(*(longlong *)(pcVar9 + 8) + 0x90))();
                        }
                        if (pcVar10 == (code *)0x0) {
                          iVar21 = 0x13be;
                          iVar7 = 0x296d5;
                        }
                        else {
                          plVar12 = (longlong *)0x0;
                          lVar20 = 0;
                          if ((*(code **)(pcVar10 + 8) == PyMethod_Type_exref) &&
                             (plVar12 = *(longlong **)(pcVar10 + 0x18), plVar12 != (longlong *)0x0))
                          {
                            pcVar24 = *(code **)(pcVar10 + 0x10);
                            *plVar12 = *plVar12 + 1;
                            *(longlong *)pcVar24 = *(longlong *)pcVar24 + 1;
                            *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1;
                            if (*(longlong *)pcVar10 == 0) {
                              _Py_Dealloc();
                            }
                            lVar20 = 1;
                            pcVar10 = pcVar24;
                          }
                          local_f0[2] = *(longlong **)(PTR_DAT_1801e5048 + 0x37d8);
                          local_f0[1] = plVar12;
                          pcVar24 = (code *)FUN_1801bbf50((longlong)pcVar10,local_f0 + (2 - lVar20),
                                                          (ulonglong)((int)lVar20 + 1));
                          if ((plVar12 != (longlong *)0x0) &&
                             (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
                            _Py_Dealloc(plVar12);
                          }
                          if (pcVar24 == (code *)0x0) {
                            iVar21 = 0x13be;
                            iVar7 = 0x296e9;
                          }
                          else {
                            *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1;
                            if (*(longlong *)pcVar10 == 0) {
                              _Py_Dealloc(pcVar10);
                            }
                            pcVar10 = (code *)0x0;
                            iVar7 = FUN_1801c28c0(pcVar24);
                            if (-1 < iVar7) {
                              pcVar11 = pcVar24;
                              if (iVar7 == 0) {
                                *(longlong *)pcVar24 = *(longlong *)pcVar24 + -1;
                                if (*(longlong *)pcVar24 == 0) {
                                  _Py_Dealloc(pcVar24);
                                }
                                puVar23 = PTR_DAT_1801e5048;
                                **(longlong **)(PTR_DAT_1801e5048 + 0xfa8) =
                                     **(longlong **)(PTR_DAT_1801e5048 + 0xfa8) + 1;
                                pcVar11 = *(code **)(puVar23 + 0xfa8);
                                local_170 = pcVar11;
                                goto LAB_18014307c;
                              }
                              goto LAB_180143045;
                            }
                            iVar21 = 0x13be;
                            iVar7 = 0x296ed;
                          }
                        }
                      }
                    }
                  }
                }
                else {
                  *(longlong *)pcVar11 = lVar20;
                  local_170 = pcVar11;
                  if (lVar20 == 0) {
                    _Py_Dealloc(pcVar11);
                  }
LAB_18014307c:
                  pcVar10 = (code *)0x0;
                  if (*(code **)(*(longlong *)(pcVar11 + 8) + 0x90) == (code *)0x0) {
                    pcVar24 = (code *)PyObject_GetAttr(pcVar11,*(undefined8 *)
                                                                (PTR_DAT_1801e5048 + 0x44a8));
                  }
                  else {
                    pcVar24 = (code *)(**(code **)(*(longlong *)(pcVar11 + 8) + 0x90))();
                  }
                  if (pcVar24 == (code *)0x0) {
                    iVar21 = 0x13c0;
                    iVar7 = 0x29709;
                    plVar26 = (longlong *)0x0;
                  }
                  else {
                    *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
                    if (*(longlong *)pcVar11 == 0) {
                      _Py_Dealloc(pcVar11);
                    }
                    plVar26 = (longlong *)0x0;
                    uVar15 = 0;
                    if ((*(code **)(pcVar24 + 8) == PyMethod_Type_exref) &&
                       (plVar26 = *(longlong **)(pcVar24 + 0x18), plVar26 != (longlong *)0x0)) {
                      pcVar11 = *(code **)(pcVar24 + 0x10);
                      *plVar26 = *plVar26 + 1;
                      *(longlong *)pcVar11 = *(longlong *)pcVar11 + 1;
                      *(longlong *)pcVar24 = *(longlong *)pcVar24 + -1;
                      if (*(longlong *)pcVar24 == 0) {
                        _Py_Dealloc(pcVar24);
                      }
                      uVar15 = 1;
                      pcVar24 = pcVar11;
                    }
                    local_d0 = 0;
                    local_f0[3] = plVar26;
                    pcVar11 = (code *)FUN_1801bbf50((longlong)pcVar24,local_f0 + (4 - uVar15),uVar15
                                                   );
                    local_180 = pcVar11;
                    local_158 = pcVar11;
                    if ((plVar26 != (longlong *)0x0) && (*plVar26 = *plVar26 + -1, *plVar26 == 0)) {
                      _Py_Dealloc(plVar26);
                    }
                    local_170 = (code *)0x0;
                    if (pcVar11 == (code *)0x0) {
                      iVar21 = 0x13c0;
                      iVar7 = 0x2971e;
                      plVar26 = (longlong *)0x0;
                    }
                    else {
                      *(longlong *)pcVar24 = *(longlong *)pcVar24 + -1;
                      if (*(longlong *)pcVar24 == 0) {
                        _Py_Dealloc(pcVar24);
                      }
                      local_158 = (code *)0x0;
                      pcVar24 = (code *)0x0;
                      iVar7 = FUN_1801c28c0(pcVar11);
                      if (iVar7 < 0) {
                        iVar21 = 0x13c1;
                        local_178 = local_180;
                        iVar7 = 0x2972c;
                        plVar26 = (longlong *)0x0;
                      }
                      else if (iVar7 == 0) {
                        pcVar17 = (code *)PyDict_New();
                        local_158 = pcVar17;
                        if (pcVar17 == (code *)0x0) {
                          iVar21 = 0x13c2;
                          local_178 = local_180;
                          iVar7 = 0x29738;
                          plVar26 = (longlong *)0x0;
                        }
                        else {
                          iVar7 = PyDict_SetItem(pcVar17,*(undefined8 *)(PTR_DAT_1801e5048 + 0x25f0)
                                                 ,*(undefined8 *)(PTR_DAT_1801e5048 + 0x16c8));
                          local_178 = pcVar11;
                          if (-1 < iVar7) goto LAB_180144363;
                          iVar21 = 0x13c2;
                          local_178 = local_180;
                          iVar7 = 0x2973a;
                          plVar26 = (longlong *)0x0;
                        }
                      }
                      else {
                        if (DAT_1801ef928 == *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18)) {
                          if (DAT_1801ef100 == (code *)0x0) {
                            uVar14 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x2a20);
                            pcVar24 = (code *)FUN_1801bb820(*(longlong *)(PTR_DAT_1801e5048 + 8),
                                                            uVar14);
                            if ((pcVar24 == (code *)0x0) && (lVar20 = PyErr_Occurred(), lVar20 == 0)
                               ) {
                              PyErr_Format(*(undefined8 *)PyExc_NameError_exref,
                                           "name \'%U\' is not defined",uVar14);
                            }
                          }
                          else {
                            *(longlong *)DAT_1801ef100 = *(longlong *)DAT_1801ef100 + 1;
                            pcVar24 = DAT_1801ef100;
                          }
                        }
                        else {
                          lVar20 = *(longlong *)(PTR_DAT_1801e5048 + 0x2a20);
                          pcVar24 = (code *)_PyDict_GetItem_KnownHash
                                                      (*(longlong *)PTR_DAT_1801e5048,lVar20,
                                                       *(undefined8 *)(lVar20 + 0x18));
                          DAT_1801ef928 = *(longlong *)(*(longlong *)PTR_DAT_1801e5048 + 0x18);
                          DAT_1801ef100 = pcVar24;
                          if (pcVar24 == (code *)0x0) {
                            lVar16 = PyErr_Occurred();
                            if (lVar16 == 0) {
                              pcVar24 = (code *)FUN_1801bb940(lVar20);
                            }
                            else {
                              pcVar24 = (code *)0x0;
                            }
                          }
                          else {
                            *(longlong *)pcVar24 = *(longlong *)pcVar24 + 1;
                          }
                        }
                        pcVar17 = local_160;
                        if (pcVar24 == (code *)0x0) {
                          iVar21 = 0x13c4;
                          local_178 = local_180;
                          iVar7 = 0x2974f;
                          plVar26 = (longlong *)0x0;
                        }
                        else {
                          iVar7 = FUN_1801c28c0(local_160);
                          if (iVar7 < 0) {
                            iVar21 = 0x13c6;
                            local_178 = local_180;
                            iVar7 = 0x29759;
                            plVar26 = (longlong *)0x0;
                          }
                          else {
                            if (iVar7 == 0) {
                              pcVar17 = (code *)PyDict_New();
                              if (pcVar17 == (code *)0x0) {
                                iVar21 = 0x13c6;
                                local_178 = local_180;
                                iVar7 = 0x29760;
                                plVar26 = (longlong *)0x0;
                                goto LAB_180143e91;
                              }
                              lVar20 = *(longlong *)pcVar17;
                              *(longlong *)pcVar17 = lVar20;
                              pcVar10 = pcVar17;
                              if (lVar20 == 0) {
                                _Py_Dealloc(pcVar17);
                              }
                            }
                            else {
                              *(longlong *)pcVar17 = *(longlong *)pcVar17 + 1;
                              pcVar10 = pcVar17;
                            }
                            if (pcVar10 == _Py_NoneStruct_exref) {
                              PyErr_Format(*(undefined8 *)PyExc_AttributeError_exref,
                                           "\'NoneType\' object has no attribute \'%.30s\'",
                                           &DAT_1801c5a94);
                              iVar21 = 0x13c6;
                              local_178 = local_180;
                              iVar7 = 0x29768;
                              plVar26 = (longlong *)0x0;
                            }
                            else {
                              plVar26 = FUN_1801bcd40(pcVar10,*(undefined8 *)
                                                               (PTR_DAT_1801e5048 + 0x4c00),
                                                      (longlong *)_Py_NoneStruct_exref);
                              if (plVar26 == (longlong *)0x0) {
                                iVar21 = 0x13c6;
                                local_178 = local_180;
                                iVar7 = 0x2976a;
                              }
                              else {
                                *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1;
                                if (*(longlong *)pcVar10 == 0) {
                                  _Py_Dealloc(pcVar10);
                                }
                                pcVar10 = (code *)0x0;
                                iVar7 = FUN_1801c28c0((undefined *)plVar26);
                                if (iVar7 < 0) {
                                  iVar21 = 0x13c6;
                                  local_178 = local_180;
                                  iVar7 = 0x2976d;
                                }
                                else {
                                  lVar20 = *plVar26;
                                  if (iVar7 == 0) {
                                    *plVar26 = lVar20 + -1;
                                    if (lVar20 + -1 == 0) {
                                      _Py_Dealloc(plVar26);
                                    }
                                    if (*(code **)(*(longlong *)(pcVar9 + 8) + 0x90) == (code *)0x0)
                                    {
                                      plVar26 = (longlong *)
                                                PyObject_GetAttr(pcVar9,*(undefined8 *)
                                                                         (PTR_DAT_1801e5048 + 0x2a38
                                                                         ));
                                    }
                                    else {
                                      plVar26 = (longlong *)
                                                (**(code **)(*(longlong *)(pcVar9 + 8) + 0x90))();
                                    }
                                    if (plVar26 == (longlong *)0x0) {
                                      iVar21 = 0x13c6;
                                      local_178 = local_180;
                                      iVar7 = 0x29776;
                                    }
                                    else {
                                      plVar12 = (longlong *)
                                                FUN_1801bbe10((longlong)plVar26,
                                                              *(undefined8 *)
                                                               (PTR_DAT_1801e5048 + 0x5440),0);
                                      if (plVar12 != (longlong *)0x0) {
                                        *plVar26 = *plVar26 + -1;
                                        if (*plVar26 == 0) {
                                          _Py_Dealloc();
                                        }
                                        lVar20 = *plVar12;
                                        *plVar12 = lVar20;
                                        goto joined_r0x000180143533;
                                      }
                                      iVar21 = 0x13c6;
                                      local_178 = local_180;
                                      iVar7 = 0x29778;
                                      pcVar10 = (code *)0x0;
                                    }
                                  }
                                  else {
                                    *plVar26 = lVar20;
                                    plVar12 = plVar26;
joined_r0x000180143533:
                                    if (lVar20 == 0) {
                                      _Py_Dealloc();
                                    }
                                    plVar26 = (longlong *)0x0;
                                    lVar20 = 0;
                                    if ((*(code **)(pcVar24 + 8) == PyMethod_Type_exref) &&
                                       (plVar26 = *(longlong **)(pcVar24 + 0x18),
                                       plVar26 != (longlong *)0x0)) {
                                      pcVar17 = *(code **)(pcVar24 + 0x10);
                                      *plVar26 = *plVar26 + 1;
                                      *(longlong *)pcVar17 = *(longlong *)pcVar17 + 1;
                                      *(longlong *)pcVar24 = *(longlong *)pcVar24 + -1;
                                      if (*(longlong *)pcVar24 == 0) {
                                        _Py_Dealloc();
                                      }
                                      lVar20 = 1;
                                      pcVar24 = pcVar17;
                                    }
                                    local_78 = plVar26;
                                    local_70 = pcVar11;
                                    local_68 = plVar12;
                                    pcVar11 = (code *)FUN_1801bbf50((longlong)pcVar24,
                                                                    &local_70 + -lVar20,
                                                                    (ulonglong)((int)lVar20 + 2));
                                    local_158 = pcVar11;
                                    if ((plVar26 != (longlong *)0x0) &&
                                       (*plVar26 = *plVar26 + -1, *plVar26 == 0)) {
                                      _Py_Dealloc(plVar26);
                                    }
                                    pcVar10 = (code *)0x0;
                                    *plVar12 = *plVar12 + -1;
                                    if (*plVar12 == 0) {
                                      _Py_Dealloc(plVar12);
                                    }
                                    local_170 = (code *)0x0;
                                    if (pcVar11 == (code *)0x0) {
                                      iVar21 = 0x13c4;
                                      local_178 = local_180;
                                      iVar7 = 0x29792;
                                      plVar26 = (longlong *)0x0;
                                    }
                                    else {
                                      *(longlong *)pcVar24 = *(longlong *)pcVar24 + -1;
                                      if (*(longlong *)pcVar24 == 0) {
                                        _Py_Dealloc(pcVar24);
                                      }
                                      pcVar24 = (code *)0x0;
                                      local_158 = (code *)0x0;
                                      local_130 = pcVar11;
                                      if (*(code **)(*(longlong *)(pcVar11 + 8) + 0x90) ==
                                          (code *)0x0) {
                                        pcVar10 = (code *)PyObject_GetAttr();
                                      }
                                      else {
                                        pcVar10 = (code *)(**(code **)(*(longlong *)(pcVar11 + 8) +
                                                                      0x90))();
                                      }
                                      if (pcVar10 == (code *)0x0) {
                                        iVar21 = 0x13c8;
                                        local_178 = local_180;
                                        iVar7 = 0x297a0;
                                        plVar26 = (longlong *)0x0;
                                      }
                                      else {
                                        plVar26 = (longlong *)0x0;
                                        lVar20 = 0;
                                        if ((*(code **)(pcVar10 + 8) == PyMethod_Type_exref) &&
                                           (plVar26 = *(longlong **)(pcVar10 + 0x18),
                                           plVar26 != (longlong *)0x0)) {
                                          pcVar11 = *(code **)(pcVar10 + 0x10);
                                          *plVar26 = *plVar26 + 1;
                                          *(longlong *)pcVar11 = *(longlong *)pcVar11 + 1;
                                          *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1;
                                          if (*(longlong *)pcVar10 == 0) {
                                            _Py_Dealloc();
                                          }
                                          lVar20 = 1;
                                          pcVar10 = pcVar11;
                                        }
                                        local_c0 = *(undefined8 *)(PTR_DAT_1801e5048 + 0x4760);
                                        local_c8 = plVar26;
                                        local_170 = (code *)FUN_1801bbf50((longlong)pcVar10,
                                                                          local_f0 + (6 - lVar20),
                                                                          (ulonglong)
                                                                          ((int)lVar20 + 1));
                                        if ((plVar26 != (longlong *)0x0) &&
                                           (*plVar26 = *plVar26 + -1, *plVar26 == 0)) {
                                          _Py_Dealloc(plVar26);
                                        }
                                        plVar12 = (longlong *)0x0;
                                        plVar26 = (longlong *)0x0;
                                        if (local_170 == (code *)0x0) {
                                          iVar21 = 0x13c8;
                                          local_178 = local_180;
                                          iVar7 = 0x297b4;
                                        }
                                        else {
                                          *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1;
                                          if (*(longlong *)pcVar10 == 0) {
                                            _Py_Dealloc(pcVar10);
                                          }
                                          pcVar10 = (code *)0x0;
                                          iVar7 = FUN_1801c28c0(local_170);
                                          if (iVar7 < 0) {
                                            iVar21 = 0x13c8;
                                            local_178 = local_180;
                                            iVar7 = 0x297b8;
                                          }
                                          else {
                                            if (iVar7 == 0) {
                                              *(longlong *)local_170 = *(longlong *)local_170 + -1;
                                              if (*(longlong *)local_170 == 0) {
                                                _Py_Dealloc(local_170);
                                              }
                                              puVar23 = PTR_DAT_1801e5048;
                                              **(longlong **)(PTR_DAT_1801e5048 + 0xfa8) =
                                                   **(longlong **)(PTR_DAT_1801e5048 + 0xfa8) + 1;
                                              pcVar24 = *(code **)(puVar23 + 0xfa8);
                                            }
                                            else {
                                              lVar20 = *(longlong *)local_170;
                                              *(longlong *)local_170 = lVar20;
                                              pcVar24 = local_170;
                                              if (lVar20 == 0) {
                                                _Py_Dealloc();
                                              }
                                            }
                                            if (*(code **)(pcVar24 + 8) == PyUnicode_Type_exref) {
                                              *(longlong *)pcVar24 = *(longlong *)pcVar24 + 1;
                                              pcVar11 = pcVar24;
                                            }
                                            else {
                                              pcVar11 = (code *)PyObject_Str(pcVar24);
                                            }
                                            local_170 = pcVar11;
                                            if (pcVar11 == (code *)0x0) {
                                              iVar21 = 0x13c8;
                                              local_178 = local_180;
                                              iVar7 = 0x297c4;
                                            }
                                            else {
                                              *(longlong *)pcVar24 = *(longlong *)pcVar24 + -1;
                                              if (*(longlong *)pcVar24 == 0) {
                                                _Py_Dealloc(pcVar24);
                                              }
                                              if (*(code **)(*(longlong *)(pcVar11 + 8) + 0x90) ==
                                                  (code *)0x0) {
                                                pcVar24 = (code *)PyObject_GetAttr(pcVar11,*(
                                                  undefined8 *)(PTR_DAT_1801e5048 + 0x44a8));
                                              }
                                              else {
                                                pcVar24 = (code *)(**(code **)(*(longlong *)
                                                                                (pcVar11 + 8) + 0x90
                                                                              ))();
                                              }
                                              if (pcVar24 == (code *)0x0) {
                                                iVar21 = 0x13c8;
                                                local_178 = local_180;
                                                iVar7 = 0x297c7;
                                              }
                                              else {
                                                *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
                                                if (*(longlong *)pcVar11 == 0) {
                                                  _Py_Dealloc(pcVar11);
                                                }
                                                plVar22 = (longlong *)0x0;
                                                uVar15 = 0;
                                                if ((*(code **)(pcVar24 + 8) == PyMethod_Type_exref)
                                                   && (plVar22 = *(longlong **)(pcVar24 + 0x18),
                                                      plVar22 != (longlong *)0x0)) {
                                                  pcVar11 = *(code **)(pcVar24 + 0x10);
                                                  *plVar22 = *plVar22 + 1;
                                                  *(longlong *)pcVar11 = *(longlong *)pcVar11 + 1;
                                                  *(longlong *)pcVar24 = *(longlong *)pcVar24 + -1;
                                                  if (*(longlong *)pcVar24 == 0) {
                                                    _Py_Dealloc(pcVar24);
                                                  }
                                                  uVar15 = 1;
                                                  pcVar24 = pcVar11;
                                                }
                                                local_b0 = 0;
                                                local_b8 = plVar22;
                                                pcVar11 = (code *)FUN_1801bbf50((longlong)pcVar24,
                                                                                local_f0 +
                                                                                (8 - uVar15),uVar15)
                                                ;
                                                local_188 = pcVar11;
                                                local_158 = pcVar11;
                                                if ((plVar22 != (longlong *)0x0) &&
                                                   (*plVar22 = *plVar22 + -1, *plVar22 == 0)) {
                                                  _Py_Dealloc(plVar22);
                                                }
                                                local_170 = (code *)0x0;
                                                if (pcVar11 == (code *)0x0) {
                                                  iVar21 = 0x13c8;
                                                  local_178 = local_180;
                                                  iVar7 = 0x297dc;
                                                }
                                                else {
                                                  *(longlong *)pcVar24 = *(longlong *)pcVar24 + -1;
                                                  if (*(longlong *)pcVar24 == 0) {
                                                    _Py_Dealloc(pcVar24);
                                                  }
                                                  local_158 = (code *)0x0;
                                                  if (*(code **)(local_140[1] + 0x90) == (code *)0x0
                                                     ) {
                                                    pcVar24 = (code *)PyObject_GetAttr(local_140,
                                                                                       *(undefined8
                                                                                         *)(
                                                  PTR_DAT_1801e5048 + 0x3678));
                                                  }
                                                  else {
                                                    pcVar24 = (code *)(**(code **)(local_140[1] +
                                                                                  0x90))();
                                                  }
                                                  if (pcVar24 == (code *)0x0) {
                                                    iVar21 = 0x13c9;
                                                    iVar7 = 0x297ea;
                                                    pcVar10 = (code *)0x0;
                                                    plVar26 = plVar12;
                                                  }
                                                  else {
                                                    if (*(code **)(*(longlong *)(local_130 + 8) +
                                                                  0x90) == (code *)0x0) {
                                                      pcVar11 = (code *)PyObject_GetAttr();
                                                    }
                                                    else {
                                                      pcVar11 = (code *)(**(code **)(*(longlong *)
                                                                                      (local_130 + 8
                                                                                      ) + 0x90))();
                                                    }
                                                    pcVar10 = pcVar11;
                                                    if (pcVar11 == (code *)0x0) {
                                                      iVar21 = 0x13c9;
                                                      iVar7 = 0x297ec;
                                                      plVar26 = plVar12;
                                                    }
                                                    else {
                                                      plVar22 = (longlong *)0x0;
                                                      lVar20 = 0;
                                                      if ((*(code **)(pcVar11 + 8) ==
                                                           PyMethod_Type_exref) &&
                                                         (plVar22 = *(longlong **)(pcVar11 + 0x18),
                                                         plVar22 != (longlong *)0x0)) {
                                                        pcVar10 = *(code **)(pcVar11 + 0x10);
                                                        *plVar22 = *plVar22 + 1;
                                                        *(longlong *)pcVar10 =
                                                             *(longlong *)pcVar10 + 1;
                                                        *(longlong *)pcVar11 =
                                                             *(longlong *)pcVar11 + -1;
                                                        if (*(longlong *)pcVar11 == 0) {
                                                          _Py_Dealloc();
                                                        }
                                                        lVar20 = 1;
                                                      }
                                                      local_a0 = *(undefined8 *)
                                                                  (PTR_DAT_1801e5048 + 0x4638);
                                                      local_a8 = plVar22;
                                                      local_170 = (code *)FUN_1801bbf50((longlong)
                                                                                        pcVar10,
                                                  local_f0 + (10 - lVar20),
                                                  (ulonglong)((int)lVar20 + 1));
                                                  if ((plVar22 != (longlong *)0x0) &&
                                                     (*plVar22 = *plVar22 + -1, *plVar22 == 0)) {
                                                    _Py_Dealloc();
                                                  }
                                                  if (local_170 == (code *)0x0) {
                                                    iVar21 = 0x13c9;
                                                    iVar7 = 0x29800;
                                                    plVar26 = plVar12;
                                                  }
                                                  else {
                                                    *(longlong *)pcVar10 = *(longlong *)pcVar10 + -1
                                                    ;
                                                    if (*(longlong *)pcVar10 == 0) {
                                                      _Py_Dealloc();
                                                    }
                                                    plVar12 = (longlong *)0x0;
                                                    uVar5 = 0;
                                                    if ((*(code **)(pcVar24 + 8) ==
                                                         PyMethod_Type_exref) &&
                                                       (plVar12 = *(longlong **)(pcVar24 + 0x18),
                                                       uVar5 = 0, plVar12 != (longlong *)0x0)) {
                                                      pcVar11 = *(code **)(pcVar24 + 0x10);
                                                      *plVar12 = *plVar12 + 1;
                                                      *(longlong *)pcVar11 =
                                                           *(longlong *)pcVar11 + 1;
                                                      *(longlong *)pcVar24 =
                                                           *(longlong *)pcVar24 + -1;
                                                      if (*(longlong *)pcVar24 == 0) {
                                                        _Py_Dealloc(pcVar24);
                                                      }
                                                      uVar5 = 1;
                                                      pcVar24 = pcVar11;
                                                    }
                                                    pcVar11 = local_170;
                                                    local_90 = local_170;
                                                    local_98 = plVar12;
                                                    pcVar17 = (code *)FUN_1801bbf50((longlong)
                                                                                    pcVar24,&
                                                  local_90 + -(ulonglong)uVar5,
                                                  (ulonglong)(uVar5 + 1));
                                                  local_158 = pcVar17;
                                                  if ((plVar12 != (longlong *)0x0) &&
                                                     (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
                                                    _Py_Dealloc(plVar12);
                                                  }
                                                  pcVar10 = (code *)0x0;
                                                  *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
                                                  if (*(longlong *)pcVar11 == 0) {
                                                    _Py_Dealloc(pcVar11);
                                                  }
                                                  local_170 = (code *)0x0;
                                                  if (pcVar17 == (code *)0x0) {
                                                    iVar21 = 0x13c9;
                                                    iVar7 = 0x29817;
                                                    pcVar10 = (code *)0x0;
                                                  }
                                                  else {
                                                    *(longlong *)pcVar24 = *(longlong *)pcVar24 + -1
                                                    ;
                                                    if (*(longlong *)pcVar24 == 0) {
                                                      _Py_Dealloc(pcVar24);
                                                    }
                                                    plVar12 = local_140;
                                                    local_158 = (code *)0x0;
                                                    local_128 = pcVar17;
                                                    if (*(code **)(local_140[1] + 0x90) ==
                                                        (code *)0x0) {
                                                      pcVar24 = (code *)PyObject_GetAttr(local_140,
                                                                                         *(
                                                  undefined8 *)(PTR_DAT_1801e5048 + 0x4040));
                                                  }
                                                  else {
                                                    pcVar24 = (code *)(**(code **)(local_140[1] +
                                                                                  0x90))();
                                                  }
                                                  if (pcVar24 == (code *)0x0) {
                                                    iVar21 = 0x13ca;
                                                    iVar7 = 0x29825;
                                                  }
                                                  else {
                                                    local_170 = (code *)PyDict_New();
                                                    if (local_170 == (code *)0x0) {
                                                      iVar21 = 0x13cb;
                                                      iVar7 = 0x2982f;
                                                    }
                                                    else {
                                                      iVar7 = PyDict_SetItem(local_170,
                                                                             *(undefined8 *)
                                                                              (PTR_DAT_1801e5048 +
                                                                              0x3c08),local_188);
                                                      if (iVar7 < 0) {
                                                        iVar21 = 0x13cb;
                                                        iVar7 = 0x29831;
                                                      }
                                                      else {
                                                        pcVar11 = *(code **)(plVar12[1] + 0x90);
                                                        if (pcVar11 == (code *)0x0) {
                                                          plVar26 = (longlong *)
                                                                    PyObject_GetAttr(plVar12);
                                                        }
                                                        else {
                                                          plVar26 = (longlong *)(*pcVar11)();
                                                        }
                                                        if (plVar26 == (longlong *)0x0) {
                                                          iVar21 = 0x13cc;
                                                          iVar7 = 0x2983a;
                                                        }
                                                        else {
                                                          plVar12 = (longlong *)0x0;
                                                          lVar20 = 0;
                                                          if (((code *)plVar26[1] ==
                                                               PyMethod_Type_exref) &&
                                                             (plVar12 = (longlong *)plVar26[3],
                                                             plVar12 != (longlong *)0x0)) {
                                                            plVar22 = (longlong *)plVar26[2];
                                                            *plVar12 = *plVar12 + 1;
                                                            *plVar22 = *plVar22 + 1;
                                                            *plVar26 = *plVar26 + -1;
                                                            if (*plVar26 == 0) {
                                                              _Py_Dealloc();
                                                            }
                                                            lVar20 = 1;
                                                            plVar26 = plVar22;
                                                          }
                                                          local_88 = plVar12;
                                                          local_80 = pcVar17;
                                                          pcVar10 = (code *)FUN_1801bbf50((longlong)
                                                                                          plVar26,&
                                                  local_80 + -lVar20,(ulonglong)((int)lVar20 + 1));
                                                  if ((plVar12 != (longlong *)0x0) &&
                                                     (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
                                                    _Py_Dealloc(plVar12);
                                                  }
                                                  if (pcVar10 == (code *)0x0) {
                                                    iVar21 = 0x13cc;
                                                    iVar7 = 0x2984e;
                                                  }
                                                  else {
                                                    *plVar26 = *plVar26 + -1;
                                                    if (*plVar26 == 0) {
                                                      _Py_Dealloc(plVar26);
                                                    }
                                                    pcVar11 = local_170;
                                                    plVar26 = (longlong *)0x0;
                                                    iVar7 = PyDict_SetItem(local_170,
                                                                           *(undefined8 *)
                                                                            (PTR_DAT_1801e5048 +
                                                                            0x3c00),pcVar10);
                                                    if (iVar7 < 0) {
                                                      iVar21 = 0x13cb;
                                                      iVar7 = 0x29852;
                                                    }
                                                    else {
                                                      *(longlong *)pcVar10 =
                                                           *(longlong *)pcVar10 + -1;
                                                      if (*(longlong *)pcVar10 == 0) {
                                                        _Py_Dealloc();
                                                      }
                                                      plVar12 = (longlong *)0x0;
                                                      uVar5 = 0;
                                                      if ((*(code **)(pcVar24 + 8) ==
                                                           PyMethod_Type_exref) &&
                                                         (plVar12 = *(longlong **)(pcVar24 + 0x18),
                                                         uVar5 = 0, plVar12 != (longlong *)0x0)) {
                                                        pcVar17 = *(code **)(pcVar24 + 0x10);
                                                        *plVar12 = *plVar12 + 1;
                                                        *(longlong *)pcVar17 =
                                                             *(longlong *)pcVar17 + 1;
                                                        *(longlong *)pcVar24 =
                                                             *(longlong *)pcVar24 + -1;
                                                        if (*(longlong *)pcVar24 == 0) {
                                                          _Py_Dealloc(pcVar24);
                                                        }
                                                        uVar5 = 1;
                                                        pcVar24 = pcVar17;
                                                      }
                                                      local_58[0] = local_148;
                                                      local_58[1] = pcVar11;
                                                      local_60 = plVar12;
                                                      pcVar13 = (code *)FUN_1801bbf50((longlong)
                                                                                      pcVar24,
                                                  local_58 + -(ulonglong)uVar5,
                                                  (ulonglong)(uVar5 + 2));
                                                  local_158 = pcVar13;
                                                  if ((plVar12 != (longlong *)0x0) &&
                                                     (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
                                                    _Py_Dealloc(plVar12);
                                                  }
                                                  pcVar10 = (code *)0x0;
                                                  *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
                                                  if (*(longlong *)pcVar11 == 0) {
                                                    _Py_Dealloc(pcVar11);
                                                  }
                                                  local_170 = (code *)0x0;
                                                  if (pcVar13 == (code *)0x0) {
                                                    iVar21 = 0x13ca;
                                                    iVar7 = 0x29867;
                                                    pcVar13 = pcVar9;
                                                  }
                                                  else {
                                                    *(longlong *)pcVar24 = *(longlong *)pcVar24 + -1
                                                    ;
                                                    if (*(longlong *)pcVar24 == 0) {
                                                      _Py_Dealloc(pcVar24);
                                                    }
                                                    pcVar24 = (code *)0x0;
                                                    *(longlong *)local_168 =
                                                         *(longlong *)local_168 + -1;
                                                    if (*(longlong *)local_168 == 0) {
                                                      _Py_Dealloc(local_168);
                                                    }
                                                    pcVar17 = (code *)PyDict_New();
                                                    local_158 = pcVar17;
                                                    if (pcVar17 == (code *)0x0) {
                                                      iVar7 = 0x2987e;
                                                    }
                                                    else {
                                                      iVar7 = PyDict_SetItem(pcVar17,*(undefined8 *)
                                                                                      (
                                                  PTR_DAT_1801e5048 + 0x43f8),
                                                  *(undefined8 *)(PTR_DAT_1801e5048 + 0x45b8));
                                                  pcVar11 = local_188;
                                                  if (iVar7 < 0) {
                                                    iVar7 = 0x29880;
                                                  }
                                                  else {
                                                    iVar7 = PyDict_SetItem(pcVar17,*(undefined8 *)
                                                                                    (
                                                  PTR_DAT_1801e5048 + 0x4760),local_188);
                                                  if (iVar7 < 0) {
                                                    iVar7 = 0x29889;
                                                  }
                                                  else {
                                                    iVar7 = PyDict_SetItem(pcVar17,*(undefined8 *)
                                                                                    (
                                                  PTR_DAT_1801e5048 + 0x4638),local_128);
                                                  if (iVar7 < 0) {
                                                    iVar7 = 0x29892;
                                                  }
                                                  else {
                                                    iVar7 = PyDict_SetItem(pcVar17,*(undefined8 *)
                                                                                    (
                                                  PTR_DAT_1801e5048 + 0x3b50),pcVar13);
                                                  if (-1 < iVar7) {
                                                    local_178 = local_180;
                                                    local_150 = pcVar11;
                                                    pcVar9 = pcVar13;
                                                    goto LAB_180144363;
                                                  }
                                                  iVar7 = 0x2989b;
                                                  }
                                                  }
                                                  }
                                                  }
                                                  iVar21 = 0x13cf;
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
                                                  local_178 = local_180;
                                                  local_150 = local_188;
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
    }
  }
LAB_180143e91:
  puVar23 = PTR_s_packed__build_temp__main_py_1801cc288;
  if ((pcVar24 != (code *)0x0) &&
     (*(longlong *)pcVar24 = *(longlong *)pcVar24 + -1, *(longlong *)pcVar24 == 0)) {
    _Py_Dealloc(pcVar24);
  }
  pcVar11 = (code *)0x0;
  local_188 = (code *)0x0;
  if ((plVar26 != (longlong *)0x0) && (*plVar26 = *plVar26 + -1, *plVar26 == 0)) {
    _Py_Dealloc(plVar26);
  }
  if ((local_158 != (code *)0x0) &&
     (*(longlong *)local_158 = *(longlong *)local_158 + -1, *(longlong *)local_158 == 0)) {
    _Py_Dealloc();
  }
  local_160 = (code *)0x0;
  if ((local_170 != (code *)0x0) &&
     (*(longlong *)local_170 = *(longlong *)local_170 + -1, *(longlong *)local_170 == 0)) {
    _Py_Dealloc();
  }
  local_140 = (longlong *)0x0;
  if ((pcVar10 != (code *)0x0) &&
     (*(longlong *)pcVar10 = *(longlong *)pcVar10 + -1, *(longlong *)pcVar10 == 0)) {
    _Py_Dealloc(pcVar10);
  }
  lVar20 = local_138;
  puVar1 = *(undefined **)PyExc_Exception_exref;
  puVar2 = *(undefined **)(local_138 + 0x58);
  pcVar9 = pcVar13;
  if (puVar2 == puVar1) {
LAB_180143f5c:
    FUN_1801c1020("main.Api.generate_ip_agent_publish_meta",iVar7,iVar21,puVar23);
    uVar14 = FUN_1801bc330(lVar20,&local_160,&local_188,&local_140);
    pcVar11 = local_188;
    if ((int)uVar14 < 0) {
      iVar21 = 0x13d4;
      iVar7 = 0x298ba;
      puVar23 = PTR_s_packed__build_temp__main_py_1801cc288;
      plVar26 = local_140;
    }
    else {
      *(longlong *)local_188 = *(longlong *)local_188 + 1;
      pcVar24 = (code *)PyDict_New();
      puVar23 = PTR_s_packed__build_temp__main_py_1801cc288;
      local_158 = pcVar24;
      if (pcVar24 == (code *)0x0) {
        iVar7 = 0x298ca;
        local_188 = pcVar24;
        local_180 = pcVar24;
        local_170 = pcVar24;
        lVar16 = _PyThreadState_UncheckedGet();
      }
      else {
        if (*(code **)(pcVar11 + 8) == PyUnicode_Type_exref) {
          *(longlong *)pcVar11 = *(longlong *)pcVar11 + 1;
          pcVar17 = pcVar11;
        }
        else {
          pcVar17 = (code *)PyObject_Str(pcVar11);
        }
        puVar23 = PTR_s_packed__build_temp__main_py_1801cc288;
        if (pcVar17 == (code *)0x0) {
          iVar7 = 0x298cc;
          local_188 = pcVar17;
          local_180 = pcVar17;
          local_170 = pcVar17;
          lVar16 = _PyThreadState_UncheckedGet();
        }
        else {
          pcVar25 = (code *)PyUnicode_Concat(*(undefined8 *)(PTR_DAT_1801e5048 + 0x16d0),pcVar17);
          puVar23 = PTR_s_packed__build_temp__main_py_1801cc288;
          if (pcVar25 == (code *)0x0) {
            iVar7 = 0x298ce;
            local_188 = pcVar25;
            local_180 = pcVar25;
            local_170 = pcVar25;
            lVar16 = _PyThreadState_UncheckedGet();
            *(longlong *)pcVar17 = *(longlong *)pcVar17 + -1;
            lVar20 = *(longlong *)pcVar17;
          }
          else {
            *(longlong *)pcVar17 = *(longlong *)pcVar17 + -1;
            if (*(longlong *)pcVar17 == 0) {
              _Py_Dealloc(pcVar17);
            }
            iVar7 = PyDict_SetItem(pcVar24,*(undefined8 *)(PTR_DAT_1801e5048 + 0x25f0),pcVar25);
            puVar23 = PTR_s_packed__build_temp__main_py_1801cc288;
            if (-1 < iVar7) {
              *(longlong *)pcVar25 = *(longlong *)pcVar25 + -1;
              if (*(longlong *)pcVar25 == 0) {
                _Py_Dealloc(pcVar25);
              }
              *(longlong *)local_160 = *(longlong *)local_160 + -1;
              if (*(longlong *)local_160 == 0) {
                _Py_Dealloc();
              }
              *local_140 = *local_140 + -1;
              if (*local_140 == 0) {
                _Py_Dealloc();
              }
              *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
              if (*(longlong *)pcVar11 == 0) {
                _Py_Dealloc(pcVar11);
              }
              *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
              if (*(longlong *)pcVar11 == 0) {
                _Py_Dealloc(pcVar11);
              }
              FUN_1801bc0e0(lVar20,local_110,local_118,local_120);
              goto LAB_18014437e;
            }
            local_188 = (code *)0x0;
            iVar7 = 0x298d1;
            local_170 = (code *)0x0;
            local_180 = (code *)0x0;
            lVar16 = _PyThreadState_UncheckedGet();
            *(longlong *)pcVar25 = *(longlong *)pcVar25 + -1;
            lVar20 = *(longlong *)pcVar25;
            pcVar17 = pcVar25;
          }
          if (lVar20 == 0) {
            _Py_Dealloc(pcVar17);
          }
        }
        *(longlong *)local_158 = *(longlong *)local_158 + -1;
        if (*(longlong *)local_158 == 0) {
          _Py_Dealloc();
        }
      }
      puVar4 = *(undefined8 **)(lVar16 + 0x90);
      local_158 = (code *)puVar4[2];
      uVar14 = *puVar4;
      uVar3 = puVar4[1];
      *puVar4 = 0;
      puVar4[1] = 0;
      puVar4[2] = 0;
      uVar18 = FUN_1801bc330(lVar16,&local_188,&local_170,&local_180);
      if ((int)uVar18 < 0) {
        local_168 = *(code **)(lVar16 + 0x58);
        local_148 = *(code **)(lVar16 + 0x60);
        local_188 = *(code **)(lVar16 + 0x68);
        *(undefined8 *)(lVar16 + 0x58) = 0;
        *(undefined8 *)(lVar16 + 0x60) = 0;
        *(undefined8 *)(lVar16 + 0x68) = 0;
      }
      else {
        local_168 = local_188;
        local_148 = local_170;
        local_188 = local_180;
      }
      *(longlong *)pcVar11 = *(longlong *)pcVar11 + -1;
      if (*(longlong *)pcVar11 == 0) {
        _Py_Dealloc(pcVar11);
      }
      FUN_1801bc0e0(lVar16,uVar14,uVar3,local_158);
      plVar26 = *(longlong **)(lVar16 + 0x58);
      plVar12 = *(longlong **)(lVar16 + 0x60);
      plVar22 = *(longlong **)(lVar16 + 0x68);
      *(code **)(lVar16 + 0x58) = local_168;
      *(code **)(lVar16 + 0x60) = local_148;
      *(code **)(lVar16 + 0x68) = local_188;
      if ((plVar26 != (longlong *)0x0) && (*plVar26 = *plVar26 + -1, *plVar26 == 0)) {
        _Py_Dealloc();
      }
      if ((plVar12 != (longlong *)0x0) && (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
        _Py_Dealloc(plVar12);
      }
      if ((plVar22 != (longlong *)0x0) && (*plVar22 = *plVar22 + -1, *plVar22 == 0)) {
        _Py_Dealloc(plVar22);
      }
      iVar21 = 0x13d5;
      lVar20 = local_138;
      plVar26 = local_140;
    }
  }
  else {
    plVar26 = (longlong *)0x0;
    if (puVar2 != (undefined *)0x0) {
      if ((*(uint *)(*(longlong *)(puVar1 + 8) + 0xa8) & 0x4000000) == 0) {
        uVar15 = FUN_1801bdde0(puVar2,puVar1);
        iVar6 = (int)uVar15;
      }
      else {
        uVar14 = FUN_1801bb510(puVar2,(longlong)puVar1);
        iVar6 = (int)uVar14;
      }
      if (iVar6 != 0) goto LAB_180143f5c;
    }
  }
  puVar4 = *(undefined8 **)(lVar20 + 0x90);
  plVar12 = (longlong *)*puVar4;
  local_168 = (code *)puVar4[2];
  plVar22 = (longlong *)puVar4[1];
  *puVar4 = local_110;
  puVar4[1] = local_118;
  puVar4[2] = local_120;
  if ((plVar12 != (longlong *)0x0) && (*plVar12 = *plVar12 + -1, *plVar12 == 0)) {
    _Py_Dealloc(plVar12);
  }
  if ((plVar22 != (longlong *)0x0) && (*plVar22 = *plVar22 + -1, *plVar22 == 0)) {
    _Py_Dealloc(plVar22);
  }
  if ((local_168 != (code *)0x0) &&
     (*(longlong *)local_168 = *(longlong *)local_168 + -1, *(longlong *)local_168 == 0)) {
    _Py_Dealloc();
  }
  if ((local_160 != (code *)0x0) &&
     (*(longlong *)local_160 = *(longlong *)local_160 + -1, *(longlong *)local_160 == 0)) {
    _Py_Dealloc();
  }
  if ((plVar26 != (longlong *)0x0) && (*plVar26 = *plVar26 + -1, *plVar26 == 0)) {
    _Py_Dealloc(plVar26);
  }
  if ((pcVar11 != (code *)0x0) &&
     (*(longlong *)pcVar11 = *(longlong *)pcVar11 + -1, *(longlong *)pcVar11 == 0)) {
    _Py_Dealloc(pcVar11);
  }
  FUN_1801c1020("main.Api.generate_ip_agent_publish_meta",iVar7,iVar21,puVar23);
  pcVar24 = (code *)0x0;
LAB_18014437e:
  if ((pcVar9 != (code *)0x0) &&
     (*(longlong *)pcVar9 = *(longlong *)pcVar9 + -1, *(longlong *)pcVar9 == 0)) {
    _Py_Dealloc(pcVar9);
  }
  if ((local_178 != (code *)0x0) &&
     (*(longlong *)local_178 = *(longlong *)local_178 + -1, *(longlong *)local_178 == 0)) {
    _Py_Dealloc();
  }
  if ((local_130 != (code *)0x0) &&
     (*(longlong *)local_130 = *(longlong *)local_130 + -1, *(longlong *)local_130 == 0)) {
    _Py_Dealloc();
  }
  if ((local_150 != (code *)0x0) &&
     (*(longlong *)local_150 = *(longlong *)local_150 + -1, *(longlong *)local_150 == 0)) {
    _Py_Dealloc();
  }
  if ((local_128 != (code *)0x0) &&
     (*(longlong *)local_128 = *(longlong *)local_128 + -1, *(longlong *)local_128 == 0)) {
    _Py_Dealloc(local_128);
  }
  return pcVar24;
}

