#!/usr/bin/env python
# -*- coding: utf-8  -*-

# Copyright (C) 2014-2015 Ben Kurtovic <ben.kurtovic@gmail.com>
# Released under the terms of the MIT License. See LICENSE for details.

"""
This script generates 'src/assembler/instructions.inc.c' from
'src/assembler/instructions.yml'. It should be run automatically by make
when the latter is modified, but can also be run manually.
"""

from __future__ import print_function

from itertools import product
import re
import time

SOURCE = "src/assembler/instructions.yml"
DEST = "src/assembler/instructions.inc.c"

ENCODING = "utf8"
TAB = " " * 4

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required (https://pypi.python.org/pypi/PyYAML)\n"
          "If you don't want to rebuild {0}, do:\n`make -t {0}`".format(DEST))
    exit(1)

re_date = re.compile(r"^(\s*@AUTOGEN_DATE\s*)(.*?)$", re.M)
re_inst = re.compile(
    r"(/\* @AUTOGEN_INST_BLOCK_START \*/\n*)(.*?)"
    r"(\n*/\* @AUTOGEN_INST_BLOCK_END \*/)", re.S)
re_lookup = re.compile(
    r"(/\* @AUTOGEN_LOOKUP_BLOCK_START \*/\n*)(.*?)"
    r"(\n*/\* @AUTOGEN_LOOKUP_BLOCK_END \*/)", re.S)

class Instruction(object):
    """
    Represent a single ASM instruction mnemonic.
    """
    ARG_TYPES = {
        "register": "AT_REGISTER",
        "immediate": "AT_IMMEDIATE",
        "indirect": "AT_INDIRECT",
        "indexed": "AT_INDEXED",
        "condition": "AT_CONDITION",
        "port": "AT_PORT"
    }
    ARG_EXTRA = {
        "indexed": ["AT_INDIRECT"]
    }

    def __init__(self, name, data):
        self._name = name
        self._data = data

    def _get_arg_parse_mask(self, num):
        """
        Return the appropriate mask to parse_args() for the num-th argument.
        """
        types = set()
        optional = False
        for case in self._data["cases"]:
            if num < len(case["type"]):
                atype = case["type"][num]
                types.add(self.ARG_TYPES[atype])
                if atype in self.ARG_EXTRA:
                    types.update(self.ARG_EXTRA[atype])
            else:
                optional = True

        if not types:
            return "AT_NONE"
        if optional:
            types.add("AT_OPTIONAL")
        return "|".join(types)

    def _handle_return(self, ret, indent=1):
        """
        Return code to handle an instruction return statement.
        """
        data = ", ".join("0x%02X" % byte if isinstance(byte, int) else byte
                         for byte in ret)
        return TAB * indent + "INST_RETURN({0}, {1})".format(len(ret), data)

    def _build_case_type_check(self, args):
        """
        Return the test part of an if statement for an instruction case.
        """
        conds = ["INST_TYPE({0}) == {1}".format(i, self.ARG_TYPES[cond])
                 for i, cond in enumerate(args)]
        return "INST_NARGS == {0} && {1}".format(len(args), " && ".join(conds))

    def _build_register_check(self, num, cond):
        """
        Return an expression to check for a particular register value.
        """
        return "INST_REG({0}) == REG_{1}".format(num, cond.upper())

    def _build_immediate_check(self, num, cond):
        """
        Return an expression to check for a particular immediate value.
        """
        return "INST_IMM({0}).mask & IMM_{1}".format(num, cond.upper())

    def _build_indirect_check(self, num, cond):
        """
        Return an expression to check for a particular indirect value.
        """
        # TODO
        return cond

    def _build_indexed_check(self, num, cond):
        """
        Return an expression to check for a particular indexed value.
        """
        # TODO
        return cond

    def _build_condition_check(self, num, cond):
        """
        Return an expression to check for a particular condition value.
        """
        return "INST_COND({0}) == COND_{1}".format(num, cond.upper())

    def _build_port_check(self, num, cond):
        """
        Return an expression to check for a particular port value.
        """
        # TODO
        return cond

    _SUBCASE_LOOKUP_TABLE = {
        "register": _build_register_check,
        "immediate": _build_immediate_check,
        "indirect": _build_indirect_check,
        "indexed": _build_indexed_check,
        "condition": _build_condition_check,
        "port": _build_port_check
    }

    def _build_subcase_check(self, types, conds):
        """
        Return the test part of an if statement for an instruction subcase.
        """
        return " && ".join(self._SUBCASE_LOOKUP_TABLE[types[i]](self, i, cond)
                           for i, cond in enumerate(conds) if cond != "_")

    def _iter_permutations(self, types, conds):
        """
        Iterate over all permutations of the given subcase conditions.
        """
        def split(typ, cond):
            if "|" in cond:
                sets = [split(typ, c) for c in cond.split("|")]
                return {choice for s in sets for choice in s}
            if typ == "register" and cond == "ih":
                return {"ixh", "iyh"}
            if typ == "register" and cond == "il":
                return {"ixl", "iyl"}
            return {cond}

        return product(*(split(types[i], cond)
                         for i, cond in enumerate(conds)))

    def _adapt_return(self, types, conds, ret):
        """
        Return a modified byte list to accomodate for prefixes and immediates.
        """
        for i, cond in enumerate(conds):
            if types[i] == "register" and cond.startswith("ix"):
                ret = ["INST_IX_PREFIX"] + ret
            elif types[i] == "register" and cond.startswith("iy"):
                ret = ["INST_IY_PREFIX"] + ret
        return ret

    def _handle_case(self, case):
        """
        Return code to handle an instruction case.
        """
        lines = []
        cond = self._build_case_type_check(case["type"])
        lines.append(TAB + "if ({0}) {{".format(cond))

        for subcase in case["cases"]:
            for perm in self._iter_permutations(case["type"], subcase["cond"]):
                cond = self._build_subcase_check(case["type"], perm)
                ret = self._adapt_return(case["type"], perm, subcase["return"])
                lines.append(TAB * 2 + "if ({0})".format(cond))
                lines.append(self._handle_return(ret, 3))

        lines.append(TAB * 2 + "INST_ERROR(ARG_VALUE)")
        lines.append(TAB + "}")
        return lines

    def render(self):
        """
        Convert data for an individual instruction into a C parse function.
        """
        lines = []

        if self._data["args"]:
            lines.append("{tab}INST_TAKES_ARGS(\n{tab2}{0}, \n{tab2}{1}, "
                         "\n{tab2}{2}\n{tab})".format(
                self._get_arg_parse_mask(0), self._get_arg_parse_mask(1),
                self._get_arg_parse_mask(2), tab=TAB, tab2=TAB * 2))
        else:
            lines.append(TAB + "INST_TAKES_NO_ARGS")

        if "return" in self._data:
            lines.append(self._handle_return(self._data["return"]))
        elif "cases" in self._data:
            for case in self._data["cases"]:
                lines.extend(self._handle_case(case))
            lines.append(TAB + "INST_ERROR(ARG_TYPE)")
        else:
            msg = "Missing return or case block for {0} instruction"
            raise RuntimeError(msg.format(self._name))

        contents = "\n".join(lines)
        return "INST_FUNC({0})\n{{\n{1}\n}}".format(self._name, contents)


def build_inst_block(data):
    """
    Return the instruction parser block, given instruction data.
    """
    return "\n\n".join(
        Instruction(k, v).render() for k, v in sorted(data.items()))

def build_lookup_block(data):
    """
    Return the instruction lookup block, given instruction data.
    """
    macro = TAB + "HANDLE({0})"
    return "\n".join(macro.format(inst) for inst in sorted(data.keys()))

def process(template, data):
    """
    Return C code generated from a source template and instruction data.
    """
    inst_block = build_inst_block(data)
    lookup_block = build_lookup_block(data)
    date = time.asctime(time.gmtime())

    result = re_date.sub(r"\1{0} UTC".format(date), template)
    result = re_inst.sub(r"\1{0}\3".format(inst_block), result)
    result = re_lookup.sub(r"\1{0}\3".format(lookup_block), result)
    return result

def main():
    """
    Main script entry point.
    """
    with open(SOURCE, "r") as fp:
        text = fp.read().decode(ENCODING)
    with open(DEST, "r") as fp:
        template = fp.read().decode(ENCODING)

    data = yaml.load(text)
    result = process(template, data)

    # with open(DEST, "w") as fp:
    #     fp.write(result.encode(ENCODING))
    print(result)  # TODO: remove me!

if __name__ == "__main__":
    main()
