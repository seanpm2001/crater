/* Copyright (C) 2014-2015 Ben Kurtovic <ben.kurtovic@gmail.com>
   Released under the terms of the MIT License. See LICENSE for details. */

#include <signal.h>
#include <stdbool.h>
#include <unistd.h>

#include "iomanager.h"
#include "logging.h"

static volatile bool caught_signal;

/*
    Signal handler for SIGINT.
*/
static void handle_sigint(int sig)
{
    (void) sig;  // We don't care
    caught_signal = true;
}

/*
    Emulate a Game Gear. Handle I/O with the host computer.

    Block until emulation is finished.
*/
void iomanager_emulate(GameGear *gg)
{
    caught_signal = false;
    signal(SIGINT, handle_sigint);

    DEBUG("IOManager powering GameGear")
    gamegear_power(gg, true);

    // TODO: use SDL events
    while (!caught_signal) {
        if (gamegear_simulate(gg)) {
            ERROR("caught exception: %s", gamegear_get_exception(gg))
#ifdef DEBUG_MODE
            z80_dump_registers(&gg->cpu);
#endif
            break;
        }
        usleep(1000 * 1000 / 60);
    }

    if (caught_signal) {
        WARN("caught signal, stopping...")
#ifdef DEBUG_MODE
        z80_dump_registers(&gg->cpu);
#endif
    }

    DEBUG("IOManager unpowering GameGear")
    gamegear_power(gg, false);

    signal(SIGINT, SIG_DFL);
}
