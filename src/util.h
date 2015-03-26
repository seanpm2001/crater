/* Copyright (C) 2014-2015 Ben Kurtovic <ben.kurtovic@gmail.com>
   Released under the terms of the MIT License. See LICENSE for details. */

#pragma once

#include <stdint.h>

/* Functions */

uint8_t bcd_decode(uint8_t);
uint64_t get_time_ns();
